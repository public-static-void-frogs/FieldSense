#!/usr/bin/env python3
"""Build cmip6_deltas_<year>.parquet for m3_window_forecaster.py (--deltas) from NASA NEX-GDDP-CMIP6.

NEX-GDDP-CMIP6 = bias-corrected, downscaled daily tasmin / tasmax / pr, 0.25 deg, public AWS bucket 'nex-gddp-cmip6' (no key needed).
For every model x scenario and every POWER cell (nearest 0.25 deg grid point):
    baseline  = monthly means over the 'historical' run   (default 1985-2014)
    future    = monthly means over the SSP run           (default 2030-2049, centred on 2040)
    d_tmin_c  = future - baseline   (deg C, by calendar month)
    d_tmax_c  = future - baseline
    pr_ratio  = future / baseline   (ratio of MEAN DAILY RATE, so 360-/365-day model calendars do not matter)
Output columns: cell_id, model, scenario, month, d_tmin_c, d_tmax_c, pr_ratio  (+ base_years, fut_years)  = what M3's --deltas reads.

Steps (resumable; one small part file per model x scenario x year in <out>/parts/):
  python m3_collect_cmip6.py --power ./power_dir --out ./cmip6 --models ACCESS-CM2 CanESM5 MRI-ESM2-0 NorESM2-MM \
         --scenarios ssp245 ssp585 [--baseline 1985-2014] [--future 2030-2049] [--year-step 1] [--mode download|stream]
  --power : folder with cells.parquet or weather_daily*.parquet (the same cells as the --history file)
  --mode download (default): each yearly NetCDF (~0.2-0.5 GB per variable) is downloaded to --cache, subset, deleted (--keep-files keeps it)
  --mode stream : HTTP range requests with fsspec/h5netcdf (needs: pip install fsspec aiohttp h5netcdf). Fast only if the
                  files are chunked spatially; otherwise it transfers the whole file anyway - then use download.
Volume: per model ~ (baseline years + 2 x future years) x 3 variables files; --year-step 2 uses every 2nd year and halves it
(monthly means of 10 yr are noisier, precipitation especially). Start with 2 models to check the numbers, then add more.
Check <out>/cmip6_report.csv (annual mean warming / precipitation ratio per model-scenario) before using the table.

File discovery uses the bucket listing, so variant (r1i1p1f1 ...), grid (gn/gr/gr1) and version suffix (_v1.1/_v2.0) need not be given.
NOT tested against the live bucket by the author (no network there); tested with mocked listing and NetCDFs.
Deps: pandas pyarrow numpy xarray netCDF4 requests
"""
import argparse
import datetime as dt
import re
import sys
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

BUCKET = "https://nex-gddp-cmip6.s3.us-west-2.amazonaws.com"
PREFIX = "NEX-GDDP-CMIP6"
VARS = ("tasmin", "tasmax", "pr")
FNAME = re.compile(r"^(tasmin|tasmax|pr)_day_.+_(\d{4})(?:_v[\d.]+)?\.nc$")
DEFAULT_MODELS = ["ACCESS-CM2", "CanESM5", "MRI-ESM2-0", "NorESM2-MM"]


def log(*a):
    print(dt.datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def years_arg(s):
    a, b = str(s).split("-")
    return list(range(int(a), int(b) + 1))


# ------------------------------------------------------------------ cells
def load_cells(power):
    p = Path(power)
    cand = [p / "cells.parquet", p / "weather_daily.parquet"] + sorted(p.glob("weather_daily_*.parquet"), key=lambda f: f.name, reverse=True)
    f = next((c for c in cand if c.exists()), None)
    if f is None:
        sys.exit(f"no cells.parquet / weather_daily*.parquet in {power}")
    ids = sorted(set(pq.read_table(f, columns=["cell_id"]).column("cell_id").to_pylist()))
    ll = pd.Series(ids).str.split("_", expand=True).astype(float)
    return pd.DataFrame({"cell_id": ids, "lat": ll[0].to_numpy(), "lon": ll[1].to_numpy()})


# ------------------------------------------------------------------ bucket listing
def list_keys(model, scenario):
    """{(var, year): key} for one model x scenario from the S3 listing (ListObjectsV2, paginated)."""
    import requests
    out, token = {}, None
    while True:
        params = {"list-type": "2", "prefix": f"{PREFIX}/{model}/{scenario}/"}
        if token:
            params["continuation-token"] = token
        r = requests.get(BUCKET, params=params, timeout=60)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {"s": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
        q = (lambda t: f"s:{t}") if ns else (lambda t: t)
        for c in root.findall(q("Contents"), ns):
            key = c.find(q("Key"), ns).text
            m = FNAME.match(key.rsplit("/", 1)[-1])
            if m:
                k = (m.group(1), int(m.group(2)))
                if k not in out or key > out[k]:                  # newest version suffix wins
                    out[k] = key
        trunc = root.find(q("IsTruncated"), ns)
        if trunc is not None and trunc.text == "true":
            token = root.find(q("NextContinuationToken"), ns).text
        else:
            return out


# ------------------------------------------------------------------ reading one yearly file
def download(key, dst, retries=4):
    import requests
    dst = Path(dst); part = Path(str(dst) + ".part"); dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return dst
    for t in range(retries):
        try:
            have = part.stat().st_size if part.exists() else 0
            r = requests.get(f"{BUCKET}/{key}", stream=True, timeout=120, headers={"Range": f"bytes={have}-"} if have else {})
            if r.status_code == 416:
                part.rename(dst); return dst
            if r.status_code not in (200, 206):
                raise RuntimeError(f"HTTP {r.status_code}")
            with open(part, "ab" if (have and r.status_code == 206) else "wb") as f:
                for blk in r.iter_content(1 << 20):
                    f.write(blk)
            part.rename(dst); return dst
        except Exception as e:
            log(f"  retry {t + 1}/{retries} {key}: {e}")
    raise RuntimeError(f"could not download {key}")


def monthly_stats(ds, cells):
    """xarray Dataset (one variable, time x lat x lon) -> DataFrame cell_id, month, value (monthly mean of the daily values)."""
    import xarray as xr  # noqa: F401
    v = next(k for k, x in ds.data_vars.items() if x.ndim == 3)
    da = ds[v]
    latn = next(d for d in da.dims if d.lower().startswith("lat")); lonn = next(d for d in da.dims if d.lower().startswith("lon"))
    tn = next(d for d in da.dims if d not in (latn, lonn))
    lat, lon = ds[latn].values, ds[lonn].values
    lonq = np.where(cells["lon"].to_numpy() < 0, cells["lon"].to_numpy() + 360.0, cells["lon"].to_numpy()) if lon.max() > 180 else cells["lon"].to_numpy()
    iy = np.abs(lat[None, :] - cells["lat"].to_numpy()[:, None]).argmin(1)
    ix = np.abs(lon[None, :] - lonq[:, None]).argmin(1)
    y0, y1, x0, x1 = iy.min(), iy.max() + 1, ix.min(), ix.max() + 1
    blk = da.transpose(tn, latn, lonn).isel({latn: slice(y0, y1), lonn: slice(x0, x1)}).values.astype("float64")   # small box only
    arr = blk[:, iy - y0, ix - x0]                                                                                    # (time, cell)
    units = str(da.attrs.get("units", "")).lower()
    if units in ("k", "kelvin"):
        arr = arr - 273.15
    elif "kg" in units:
        arr = arr * 86400.0                                                                                           # kg m-2 s-1 -> mm/day
    months = ds[tn].dt.month.values
    rows = []
    for m in range(1, 13):
        sel = months == m
        if sel.any():
            rows.append(pd.DataFrame({"cell_id": cells["cell_id"].to_numpy(), "month": m, "value": np.nanmean(arr[sel], 0)}))
    return pd.concat(rows, ignore_index=True)


READ_LOCK = threading.Lock()      # HDF5 / netCDF4 are not thread-safe: downloads run in parallel, file reads one at a time


def fetch_file(key, a):
    """download mode: local path of the yearly file (downloaded if needed); stream mode: the key itself. Thread-safe. Replaced in tests."""
    if a.mode == "stream":
        return key
    return download(key, Path(a.cache) / key.rsplit("/", 1)[-1])


def open_local(ref, a):
    """context manager -> xarray Dataset (local file, or HTTP range requests in stream mode); deletes the file afterwards unless --keep-files."""
    import contextlib
    import xarray as xr

    @contextlib.contextmanager
    def cm():
        if a.mode == "stream":
            import fsspec
            f = fsspec.open(f"{BUCKET}/{ref}", "rb", block_size=8 << 20).open()
            try:
                with xr.open_dataset(f, engine="h5netcdf") as ds:
                    yield ds
            finally:
                f.close()
        else:
            try:
                with xr.open_dataset(ref) as ds:
                    yield ds
            finally:
                if not a.keep_files:
                    Path(ref).unlink(missing_ok=True)
    return cm()


def do_year(job, cells, a):
    model, scen, year, keys = job
    part = Path(a.out) / "parts" / f"{model}__{scen}__{year}.parquet"
    if part.exists():
        return part, "cached"
    cols = {}
    for var in VARS:
        ref = fetch_file(keys[var], a)                       # parallel
        with READ_LOCK, open_local(ref, a) as ds:            # serialised
            cols[var] = monthly_stats(ds, cells).rename(columns={"value": var})
    df = cols["tasmin"].merge(cols["tasmax"], on=["cell_id", "month"]).merge(cols["pr"], on=["cell_id", "month"])
    df = df.rename(columns={"pr": "pr_mmday"})
    df.insert(0, "year", year); df.insert(0, "scenario", scen); df.insert(0, "model", model)
    part.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(part) + ".tmp"); df.to_parquet(tmp, index=False); tmp.rename(part)
    return part, "done"


# ------------------------------------------------------------------ assemble
def collect(a, cells):
    base_years = years_arg(a.baseline)[::a.year_step]
    fut_years = years_arg(a.future)[::a.year_step]
    jobs = []
    for model in a.models:
        listing = {}
        for scen in ["historical"] + a.scenarios:
            try:
                listing[scen] = list_keys(model, scen)
            except Exception as e:
                log(f"{model} {scen}: listing failed ({e})"); listing[scen] = {}
        for scen, yrs in [("historical", base_years)] + [(s, fut_years) for s in a.scenarios]:
            lk = listing[scen]
            miss = [y for y in yrs if not all((v, y) in lk for v in VARS)]
            if len(miss) == len(yrs):
                log(f"{model} {scen}: no files for {yrs[0]}-{yrs[-1]} -> skipped"); continue
            if miss:
                log(f"{model} {scen}: years without all 3 variables skipped: {miss}")
            for y in yrs:
                if y not in miss:
                    jobs.append((model, scen, y, {v: lk[(v, y)] for v in VARS}))
    log(f"{len(jobs)} model-scenario-years x 3 variables to read ({a.mode} mode, {a.workers} worker(s))")
    done = 0
    with ThreadPoolExecutor(a.workers) as ex:
        for (part, st), job in zip(ex.map(lambda j: do_year(j, cells, a), jobs), jobs):
            done += 1
            if st == "done" or done % 20 == 0:
                log(f"  [{done}/{len(jobs)}] {job[0]} {job[1]} {job[2]} {st}")


def assemble(a):
    parts = sorted((Path(a.out) / "parts").glob("*.parquet"))
    if not parts:
        sys.exit("no part files")
    d = pd.concat([pd.read_parquet(f) for f in parts], ignore_index=True)
    mon = d.groupby(["model", "scenario", "cell_id", "month"], as_index=False).agg(
        tmin=("tasmin", "mean"), tmax=("tasmax", "mean"), pr=("pr_mmday", "mean"), n=("year", "nunique"))
    hist = mon[mon["scenario"] == "historical"].drop(columns="scenario").rename(columns={"tmin": "tmin0", "tmax": "tmax0", "pr": "pr0", "n": "n0"})
    fut = mon[mon["scenario"] != "historical"]
    m = fut.merge(hist, on=["model", "cell_id", "month"], how="inner")
    if m.empty:
        sys.exit("no model has both a historical and a scenario part - check the report / listing messages")
    out = pd.DataFrame({"cell_id": m["cell_id"], "model": m["model"], "scenario": m["scenario"], "month": m["month"].astype(int),
                        "d_tmin_c": m["tmin"] - m["tmin0"], "d_tmax_c": m["tmax"] - m["tmax0"],
                        "pr_ratio": np.where(m["pr0"] > 1e-6, m["pr"] / m["pr0"].where(m["pr0"] > 1e-6), np.nan),
                        "base_years": m["n0"].astype(int), "fut_years": m["n"].astype(int)})
    out = out.sort_values(["model", "scenario", "cell_id", "month"]).reset_index(drop=True)
    centre = int(round(np.mean(years_arg(a.future)) / 10) * 10)
    f = Path(a.out) / f"cmip6_deltas_{centre}.parquet"
    out.to_parquet(f, index=False)
    rep = out.groupby(["model", "scenario"]).agg(cells=("cell_id", "nunique"), dtmin_c=("d_tmin_c", "mean"), dtmax_c=("d_tmax_c", "mean"),
                                                 pr_ratio=("pr_ratio", "mean"), base_years=("base_years", "min"),
                                                 fut_years=("fut_years", "min")).reset_index()
    rep["flag"] = np.where((rep[["dtmin_c", "dtmax_c"]].abs().max(axis=1) > 8) | (rep["pr_ratio"] < 0.6) | (rep["pr_ratio"] > 1.6), "CHECK", "")
    rep.to_csv(Path(a.out) / "cmip6_report.csv", index=False)
    log(f"wrote {f.name}: {len(out):,} rows, {out['model'].nunique()} models, scenarios {sorted(out['scenario'].unique())}")
    print(rep.round(3).to_string(index=False))
    if (rep["flag"] == "CHECK").any():
        log("  some model-scenarios look implausible (CHECK) - inspect before using")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--power", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--scenarios", nargs="+", default=["ssp245", "ssp585"])
    ap.add_argument("--baseline", default="1985-2014", help="years of the historical run")
    ap.add_argument("--future", default="2030-2049", help="years of the SSP runs (centre = target year)")
    ap.add_argument("--year-step", type=int, default=1, help="2 = every second year (half the data volume)")
    ap.add_argument("--mode", choices=["download", "stream"], default="download")
    ap.add_argument("--cache", default="./cmip6_cache")
    ap.add_argument("--keep-files", action="store_true")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--assemble-only", action="store_true", help="skip downloading, rebuild the table from existing parts")
    a = ap.parse_args()
    Path(a.out).mkdir(parents=True, exist_ok=True)
    if not a.assemble_only:
        cells = load_cells(a.power)
        log(f"{len(cells)} POWER cells; models {a.models}; scenarios {a.scenarios}; baseline {a.baseline}, future {a.future}")
        collect(a, cells)
    assemble(a)


if __name__ == "__main__":
    main()
