#!/usr/bin/env python3
"""GPM IMERG V07 daily precipitation for the field coordinates in csb_bounds output (Parquet).

Product: IMERG Final Run daily, GES DISC collection GPM_3IMERGDF V07 (0.1 deg, daily, NetCDF4, ~1998-01 onward,
latency ~3.5 months). Variables (per GES DISC page): precipitation [mm/day], randomError [mm/day],
probabilityLiquidPrecipitation [%], precipitation_cnt / precipitation_cnt_cond [count of half-hours],
MWprecipitation [mm/day] (+ _cnt), randomError_cnt. Pick ONE stream/version for a consistent series.
(Early/Late streams are separate collections; their short names below are from memory, so check them.)

Two-table output, as in the other csb_* scripts (fields in one 0.1 deg cell get identical values):
  field_cell_map.parquet   CSBID -> cell_id
  cells.parquet            cell_id, cell_lat, cell_lon, n_fields, i, j
  imerg_daily.parquet      cell_id, date, <variables>        (one row per cell per day)

Steps (resumable)
  plan     read csb_bounds, snap centroids to the 0.1 deg grid, write cells.parquet + field_cell_map.parquet
  extract  per day: find/download the global daily file, read only the planned cells, write <out>/daily/YYYYMMDD.parquet,
           delete the downloaded file unless --keep-files
  merge    stream the daily parts into imerg_daily.parquet

Grid assumption: cell centres at lat = -89.95 + 0.1*i, lon = -179.95 + 0.1*j (global 1800 x 3600). The extractor
checks this against lat/lon in every file and stops if it does not match.

Access: NASA Earthdata Login (EARTHDATA_USERNAME / EARTHDATA_PASSWORD env vars, or interactive prompt) via the
`earthaccess` package. Files already present in --cache (name containing 'IMERG.YYYYMMDD') are used without any download.
You can also fetch files yourself from GES DISC and drop them there.

Examples
  python csb_imerg.py plan    --bounds ./csb_bounds --out ./imerg --county 19015
  python csb_imerg.py extract --out ./imerg --start 2018-01-01 --end 2025-12-31 --cache ./imerg_files
  python csb_imerg.py merge   --out ./imerg

Not tested against the live service (blocked in the build sandbox); tested on synthetic NetCDF files.
Deps: pip install pandas pyarrow numpy xarray netCDF4 earthaccess
"""
import argparse, datetime as dt, os, re, sys
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

STREAMS = {"final": "GPM_3IMERGDF", "late": "GPM_3IMERGDL", "early": "GPM_3IMERGDE"}   # late/early names: verify
DEFAULT_VARS = ["precipitation", "randomError", "probabilityLiquidPrecipitation",
                "precipitation_cnt", "precipitation_cnt_cond"]
NLAT, NLON = 1800, 3600


def grid_index(lon, lat):
    i = np.clip(np.round((np.asarray(lat, "float64") + 89.95) / 0.1).astype(int), 0, NLAT - 1)
    j = np.clip(np.round((np.asarray(lon, "float64") + 179.95) / 0.1).astype(int), 0, NLON - 1)
    return i, j


def cell_lat_lon(i, j):
    return np.round(-89.95 + 0.1 * i, 2), np.round(-179.95 + 0.1 * j, 2)


# ------------------------------------------------------------------ field selection (duplicated on purpose)
def load_fields(a):
    if a.points:
        p = pd.read_csv(a.points)
        low = {c.lower(): c for c in p.columns}
        pick = lambda *names: next((low[n] for n in names if n in low), None)
        ic, lo, la = pick("id", "csbid"), pick("lon", "longitude", "centroid_lon"), pick("lat", "latitude", "centroid_lat")
        if not (ic and lo and la):
            sys.exit(f"--points CSV needs id, lon, lat columns; found {list(p.columns)}")
        return pd.DataFrame({"CSBID": p[ic].astype(str), "centroid_lon": p[lo].astype(float), "centroid_lat": p[la].astype(float)})
    if not a.bounds:
        sys.exit("give --bounds DIR or --points CSV")
    ids = None
    if a.ids:
        raw = Path(a.ids).read_text().splitlines()
        if raw and "CSBID" in raw[0].split(","):
            col = raw[0].split(",").index("CSBID")
            ids = {ln.split(",")[col].strip() for ln in raw[1:] if ln.strip()}
        else:
            ids = {ln.split(",")[0].strip() for ln in raw if ln.strip()}
    files = sorted(Path(a.bounds).glob("batch_*.parquet"))
    if not files:
        sys.exit(f"no batch_*.parquet in {a.bounds}")
    parts, n = [], 0
    for f in files:
        have = set(pq.read_schema(f).names)
        cols = ["CSBID", "centroid_lon", "centroid_lat"] + [c for c in ("STATEFIPS", "CNTYFIPS") if c in have and (a.state or a.county)]
        df = pd.read_parquet(f, columns=cols)
        if a.state:
            df = df[df["STATEFIPS"] == str(a.state).zfill(2)]
        if a.county:
            df = df[df["CNTYFIPS"] == str(a.county).zfill(5)]
        if ids is not None:
            df = df[df["CSBID"].isin(ids)]
        if a.limit:
            df = df.head(a.limit - n)
        if len(df):
            parts.append(df[["CSBID", "centroid_lon", "centroid_lat"]]); n += len(df)
        if a.limit and n >= a.limit:
            break
    if not parts:
        sys.exit("no fields matched the selection")
    return pd.concat(parts, ignore_index=True)


# ------------------------------------------------------------------ plan
def cmd_plan(a):
    f = load_fields(a)
    i, j = grid_index(f["centroid_lon"].to_numpy(), f["centroid_lat"].to_numpy())
    clat, clon = cell_lat_lon(i, j)
    f["cell_id"] = [f"{la:+.2f}_{lo:+.2f}" for la, lo in zip(clat, clon)]
    f["i"], f["j"], f["cell_lat"], f["cell_lon"] = i, j, clat, clon
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    cells = f.groupby(["cell_id", "cell_lat", "cell_lon", "i", "j"]).size().rename("n_fields").reset_index()
    f[["CSBID", "cell_id"]].to_parquet(out / "field_cell_map.parquet", compression="zstd", index=False)
    cells.to_parquet(out / "cells.parquet", compression="zstd", index=False)
    print(f"{len(f):,} fields -> {len(cells):,} IMERG 0.1-degree cells")


# ------------------------------------------------------------------ extract
def day_of(path):
    m = re.search(r"IMERG\.(\d{8})", Path(path).name)
    return dt.datetime.strptime(m.group(1), "%Y%m%d").date() if m else None


def local_files(cache):
    d = {}
    for p in Path(cache).glob("*"):
        if p.suffix.lower() in (".nc4", ".nc", ".hdf5", ".h5") and day_of(p):
            d[day_of(p)] = p
    return d


_LOGGED_IN = False


def ea_login():
    global _LOGGED_IN
    if _LOGGED_IN:
        return
    import earthaccess
    if os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD"):
        earthaccess.login(strategy="environment")
    else:
        earthaccess.login(strategy="interactive")
    _LOGGED_IN = True


def download_days(a, days):
    """Search + download the daily files for these days (a small window) with earthaccess; returns {day: path}."""
    import earthaccess
    ea_login()
    days = sorted(days)
    lo, hi = days[0], days[-1]
    res = earthaccess.search_data(short_name=STREAMS[a.stream], version=a.version,
                                  temporal=(lo.isoformat(), (hi + dt.timedelta(days=1)).isoformat()))
    want = set(days)
    sel = []
    for g in res:
        try:
            d = day_of(g.data_links()[0])
        except Exception:
            d = None
        if d is None or d in want:
            sel.append(g)
    print(f"search {lo}..{hi}: {len(res)} granules found, {len(sel)} wanted", flush=True)
    if not sel:
        print(f"  no granules for {lo}..{hi} (data not published yet, or wrong stream/version)", file=sys.stderr)
        return {}
    try:
        paths = earthaccess.download(sel, str(a.cache))
    except Exception as e:
        if type(e).__name__ == "EulaNotAccepted":
            sys.exit("Earthdata account has not approved the GES DISC application (EULA).\n"
                     "Log in at https://urs.earthdata.nasa.gov -> Applications -> Authorized Apps -> "
                     "Approve More Applications -> 'NASA GESDISC DATA ARCHIVE', approve it, then re-run this command.\n"
                     f"Details: {e}")
        raise
    got = {}
    for p in paths:
        d = day_of(p)
        if d:
            got[d] = Path(p)
    return got


def extract_day(path, cells, variables, i_idx, j_idx):
    import xarray as xr
    ds = xr.open_dataset(path)                                    # decodes fill values to NaN
    try:
        lat, lon = ds["lat"].values, ds["lon"].values
        if len(lat) != NLAT or len(lon) != NLON or abs(lat[0] + 89.95) > 0.01 or abs(lon[0] + 179.95) > 0.01 or lat[1] < lat[0]:
            raise ValueError(f"unexpected grid in {path}: lat {lat[0]}..{lat[-1]} ({len(lat)}), lon {lon[0]}..{lon[-1]} ({len(lon)})")
        out = {"cell_id": cells["cell_id"].to_numpy()}
        pi, pj = xr.DataArray(i_idx, dims="cell"), xr.DataArray(j_idx, dims="cell")
        for v in variables:
            if v not in ds:
                continue
            da = ds[v]
            if "time" in da.dims:
                da = da.isel(time=0)
            out[v] = da.isel(lat=pi, lon=pj).values.astype("float32")      # dims by name, so [time,lon,lat] order is fine
        missing = [v for v in variables if v not in ds]
        return pd.DataFrame(out), missing
    finally:
        ds.close()


def cmd_extract(a):
    out = Path(a.out)
    cells = pd.read_parquet(out / "cells.parquet")
    i_idx, j_idx = cells["i"].to_numpy(), cells["j"].to_numpy()
    (out / "daily").mkdir(exist_ok=True)
    Path(a.cache).mkdir(parents=True, exist_ok=True)
    s, e = dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end)
    days = [s + dt.timedelta(days=k) for k in range((e - s).days + 1)]
    todo = [d for d in days if not (out / "daily" / f"{d:%Y%m%d}.parquet").exists()]
    print(f"{len(todo)} of {len(days)} days to extract; {len(cells):,} cells", flush=True)
    ok = skipped = 0
    for c0 in range(0, len(todo), a.window):                  # window of days: download -> extract -> delete
        chunk = todo[c0:c0 + a.window]
        files = local_files(a.cache)
        need = [d for d in chunk if d not in files]
        downloaded = set()
        if need and not a.no_download:
            got = download_days(a, need)
            files.update(got); downloaded = set(got.values())
        for d in chunk:
            p = files.get(d)
            if p is None:
                skipped += 1; print(f"{d}: no file (not published yet or download failed)", file=sys.stderr); continue
            df, miss = extract_day(p, cells, a.variables, i_idx, j_idx)
            if miss and ok == 0:
                print(f"WARNING: variables not in file, skipped: {miss}", file=sys.stderr)
            df.insert(1, "date", pd.Timestamp(d))
            dst = out / "daily" / f"{d:%Y%m%d}.parquet"
            tmp = Path(str(dst) + ".tmp"); df.to_parquet(tmp, compression="zstd", index=False); tmp.rename(dst)
            ok += 1
            if p in downloaded and not a.keep_files:          # only delete what this run downloaded
                p.unlink(missing_ok=True)
        print(f"{min(c0 + a.window, len(todo))}/{len(todo)} days processed", flush=True)
    print(f"extract finished: {ok} days written, {skipped} days missing. Re-run to retry missing days.")


def cmd_merge(a):
    import pyarrow as pa
    out = Path(a.out)
    parts = sorted((out / "daily").glob("*.parquet"))
    if not parts:
        sys.exit("no daily parts; run extract first")
    dst = out / "imerg_daily.parquet"
    w, n = None, 0
    for f in parts:
        t = pq.read_table(f)
        w = w or pq.ParquetWriter(dst, t.schema, compression="zstd")
        w.write_table(t.cast(w.schema)); n += t.num_rows
    w.close()
    print(f"wrote {dst}: {n:,} rows from {len(parts)} days")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    pl = sp.add_parser("plan")
    pl.add_argument("--bounds"); pl.add_argument("--points"); pl.add_argument("--state"); pl.add_argument("--county")
    pl.add_argument("--ids"); pl.add_argument("--limit", type=int); pl.add_argument("--out", required=True)
    pl.set_defaults(fn=cmd_plan)
    ex = sp.add_parser("extract")
    ex.add_argument("--out", required=True)
    ex.add_argument("--start", required=True, help="YYYY-MM-DD")
    ex.add_argument("--end", help="YYYY-MM-DD (default: today minus 120 days for final; today minus 3 days otherwise)")
    ex.add_argument("--stream", choices=list(STREAMS), default="final")
    ex.add_argument("--version", default="07")
    ex.add_argument("--variables", nargs="+", default=DEFAULT_VARS)
    ex.add_argument("--cache", default="./imerg_files")
    ex.add_argument("--window", type=int, default=31, help="days downloaded, extracted and deleted per round")
    ex.add_argument("--no-download", action="store_true", help="use only files already in --cache")
    ex.add_argument("--keep-files", action="store_true", help="keep downloaded files (global daily files are large)")
    ex.set_defaults(fn=cmd_extract)
    me = sp.add_parser("merge"); me.add_argument("--out", required=True); me.set_defaults(fn=cmd_merge)
    a = p.parse_args()
    if a.cmd == "extract" and not a.end:
        a.end = (dt.date.today() - dt.timedelta(days=120 if a.stream == "final" else 3)).isoformat()
    a.fn(a)


if __name__ == "__main__":
    main()
