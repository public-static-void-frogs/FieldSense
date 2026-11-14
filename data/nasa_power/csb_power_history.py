#!/usr/bin/env python3
"""Extend the NASA POWER daily weather BACK to 2000 for the cells already in your weather_daily.parquet.

Builds on csb_power_weather.py (same folder): it re-uses its request / parse_response / year_chunks, so
parameters, units, community and fill-value handling are identical to what produced your 2018+ data.

Why a separate script: `csb_power_weather.py fetch` skips every cell that already has a file, so running it
again with --start 20000101 in the same --out does nothing. This script instead
  1. takes the cells from --power itself: the distinct cell_id of weather_daily.parquet (or the files in cells/),
     optionally restricted by --cells (a file with a cell_id column, e.g. power/cells.parquet),
  2. reads each cell's EXISTING weather from --power (weather_daily.parquet, or cells/<id>.parquet),
  3. fetches only the missing period: --start (default 20000101) .. first existing day + overlap,
  4. compares the overlap with the existing values (detects a changed POWER version / community / units),
  5. stitches  new (< first existing day) + existing  and writes
        weather_daily_<y0>_<y1>.parquet   same schema as weather_daily.parquet (all parameters, elevation_m)
        power_history_<y0>_<y1>.parquet   cell_id,date,tmin_c,tmax_c,pr_mm   <- for m3_window_forecaster.py --history
        fetch_report.csv                  per cell: span, missing days, overlap difference, status
It writes CELLS, not fields: all fields in a cell share the weather. Field -> weather = field_cell_map JOIN cell_id.

Steps are resumable: fetched pre-2018 pieces are kept in <out>/cells_pre/ and skipped on re-run (--force to redo).

Examples
  python csb_power_history.py --power ./power --out ./power_2000
  python csb_power_history.py --power ./power --out ./power_2000 --limit-cells 3          # test run
  python csb_power_history.py --power ./power --cells my_cells.csv --out ./power_2000     # only some cells
  python csb_power_history.py --power ./power --out ./power_2000 --overlap-days 0         # no overlap check

Going further back (chain runs): the output of one run is the "existing" data of the next
  python csb_power_history.py --power ./power      --out ./power_2000                       # 2000-2025
  python csb_power_history.py --power ./power_2000 --out ./power_1981 --start 19810101      # 1981-2025 (POWER starts 1981-01-01)

Deps: pip install pandas pyarrow numpy requests
"""
import argparse
import json
import shutil
import sys
import time
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from csb_power_weather import request, parse_response, year_chunks, DEFAULT_PARAMS, MAX_PARAMS  # noqa: E402

M3_COLS = {"T2M_MIN": "tmin_c", "T2M_MAX": "tmax_c", "PRECTOTCORR": "pr_mm"}
NON_PARAM = {"cell_id", "date", "elevation_m"}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def make_session():
    import requests
    return requests.Session()


# ------------------------------------------------------------------ cells
WEATHER_FILE = None          # set in main(): the parquet holding the EXISTING weather


def find_weather_file(power, explicit=None):
    """--weather-file, else weather_daily.parquet, else the newest weather_daily_*.parquet (output of a previous run)."""
    if explicit:
        f = Path(explicit)
        f = f if f.is_absolute() or f.exists() else Path(power) / explicit
        if not f.exists():
            sys.exit(f"--weather-file not found: {explicit}")
        return f
    f = Path(power) / "weather_daily.parquet"
    if f.exists():
        return f
    cand = sorted(Path(power).glob("weather_daily_*.parquet"), key=lambda p: p.name)
    return cand[-1] if cand else None


def cells_from_power(power):
    """Distinct cell_id of weather_daily.parquet (reads that one column only), else the files in cells/."""
    wd = WEATHER_FILE
    if wd is not None:
        col = pq.read_table(wd, columns=["cell_id"]).column("cell_id")
        return sorted(set(col.to_pylist()))
    files = sorted((Path(power) / "cells").glob("*.parquet"))
    if not files:
        sys.exit(f"no weather_daily*.parquet and no cells/*.parquet in {power}")
    return [f.stem for f in files]


def cells_from_file(path):
    df = pd.read_parquet(path) if str(path).endswith(".parquet") else pd.read_csv(path)
    col = next((c for c in ("cell_id", "power_cell_id") if c in df.columns), None)
    if col is None:
        sys.exit(f"--cells needs a cell_id column; found {list(df.columns)}")
    return sorted(df[col].astype(str).unique())


def parse_cell(cid):
    """'<lat>_<lon>' (e.g. '+42.0_-093.750' as written by csb_power_weather.cell_id) -> (lon, lat)."""
    la, lo = cid.split("_")
    return float(lo), float(la)


# ------------------------------------------------------------------ existing data
def existing_for_cell(power, cid, columns=None):
    """Existing weather of one cell: weather_daily.parquet (filtered read) first, else cells/<id>.parquet."""
    wd = WEATHER_FILE
    t = None
    if wd is not None:
        t = pq.read_table(wd, columns=columns, filters=[("cell_id", "=", cid)])
        if t.num_rows == 0:
            t = None
    if t is None:
        f = Path(power) / "cells" / f"{cid}.parquet"
        if not f.exists():
            return None
        t = pq.read_table(f, columns=columns)
    df = t.to_pandas()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").drop_duplicates("date").reset_index(drop=True)


def detect_params(power, cells):
    for cid in cells:
        ex = existing_for_cell(power, cid)
        if ex is not None:
            return [c for c in ex.columns if c not in NON_PARAM]
    return None


# ------------------------------------------------------------------ fetch the missing period
def fetch_pre(cid, a, params):
    dst = Path(a.out) / "cells_pre" / f"{cid}.parquet"
    if dst.exists() and not a.force:
        return "cached", None
    lon, lat = parse_cell(cid)
    ex = existing_for_cell(a.power, cid, columns=["cell_id", "date"])
    if ex is None:
        return "NO EXISTING DATA", None
    end = ex["date"].min() + pd.Timedelta(days=max(a.overlap_days, 1) - 1)
    sess = make_session()
    parts, elev, units = [], None, {}
    for s0, e0 in year_chunks(a.start, end.strftime("%Y%m%d"), a.chunk_years):
        js = request(sess, lon, lat, s0, e0, params, a.community, a.time_standard)
        df, el, un = parse_response(js, params)
        parts.append(df)
        elev = el if el is not None else elev
        units = un or units
        time.sleep(a.pause)
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated()]
    df.insert(0, "cell_id", cid)
    df["elevation_m"] = elev
    tmp = Path(str(dst) + ".tmp")
    df.reset_index().to_parquet(tmp, compression="zstd", index=False)
    tmp.rename(dst)
    return "fetched", units


# ------------------------------------------------------------------ stitch
def stitch(cid, a, params):
    """Return (combined DataFrame, overlap stats dict)."""
    pre = pd.read_parquet(Path(a.out) / "cells_pre" / f"{cid}.parquet")
    pre["date"] = pd.to_datetime(pre["date"])
    stats = {}
    ex = existing_for_cell(a.power, cid)
    first_ex = ex["date"].min()
    if a.overlap_days > 0:
        m = pre[pre["date"] >= first_ex].merge(ex, on="date", suffixes=("_new", "_old"))
        for p in params:
            d = (m[f"{p}_new"] - m[f"{p}_old"]).abs()
            if d.notna().any():
                stats[f"overlap_mae_{p}"] = float(d.mean())
                stats[f"overlap_max_{p}"] = float(d.max())
        stats["overlap_days"] = int(len(m))
    new = pre[pre["date"] < first_ex]                              # keep YOUR existing values from first_ex on
    out = pd.concat([new, ex], ignore_index=True).sort_values("date").drop_duplicates("date")
    full = pd.date_range(out["date"].min(), out["date"].max())
    out = out.set_index("date").reindex(full)                       # gaps stay NaN (never interpolated)
    out.index.name = "date"
    out["cell_id"] = cid
    out["elevation_m"] = out["elevation_m"].ffill().bfill()
    out = out.reset_index()[["cell_id", "date"] + params + ["elevation_m"]]
    return out, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--power", required=True, help="output dir of csb_power_weather.py: weather_daily.parquet "
                                                   "(or cells/) with the existing 2018+ weather. Cells are taken from it.")
    ap.add_argument("--weather-file", help="parquet with the existing weather (default: weather_daily.parquet, else the newest "
                                           "weather_daily_*.parquet in --power, i.e. the output of an earlier run)")
    ap.add_argument("--cells", help="optional: parquet/csv with a cell_id column to restrict the cells (e.g. power/cells.parquet)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", default="20000101", help="YYYYMMDD")
    ap.add_argument("--overlap-days", type=int, default=30, help="days refetched on top of the existing data to compare (0 = off)")
    ap.add_argument("--parameters", nargs="+", help="default: the parameters found in the existing cell files")
    ap.add_argument("--community", default="AG")
    ap.add_argument("--time-standard", choices=["utc", "lst"])
    ap.add_argument("--chunk-years", type=int, default=10, help="years per request (long ranges can fail; 0 = one request)")
    ap.add_argument("--workers", type=int, default=4, help="NASA asks for no more than 5 concurrent requests")
    ap.add_argument("--pause", type=float, default=0.2)
    ap.add_argument("--limit-cells", type=int)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.workers > 5:
        sys.exit("NASA asks for at most 5 concurrent requests")
    out = Path(a.out)
    (out / "cells_pre").mkdir(parents=True, exist_ok=True)

    global WEATHER_FILE
    WEATHER_FILE = find_weather_file(a.power, a.weather_file)
    log(f"existing weather: {WEATHER_FILE if WEATHER_FILE else (Path(a.power) / 'cells')}")
    cells = cells_from_power(a.power)
    if a.cells:
        keep = set(cells_from_file(a.cells))
        cells = [c for c in cells if c in keep]
        if not cells:
            sys.exit("--cells shares no cell_id with --power")
    if a.limit_cells:
        cells = cells[: a.limit_cells]
    params = a.parameters or detect_params(a.power, cells) or DEFAULT_PARAMS
    if len(params) > MAX_PARAMS:
        sys.exit(f"POWER allows at most {MAX_PARAMS} parameters per request")
    missing_core = [p for p in M3_COLS if p not in params]
    if missing_core:
        sys.exit(f"parameters lack {missing_core} (needed by M3); pass --parameters or check --power")
    log(f"{len(cells)} cells from {a.power}; start {a.start}; parameters {params}")

    status, units_any = {}, {}
    with ThreadPoolExecutor(a.workers) as ex_:
        futs = {ex_.submit(fetch_pre, c, a, params): c for c in cells}
        for i, fu in enumerate(as_completed(futs), 1):
            c = futs[fu]
            try:
                st, un = fu.result()
                status[c] = st
                units_any = un or units_any
            except Exception as e:
                status[c] = "FAILED: " + str(e)[:160]
                print(f"FAILED {c}: {e}", file=sys.stderr, flush=True)
            if i % 25 == 0 or i == len(cells):
                log(f"  {i}/{len(cells)} cells")
    ok = [c for c in cells if not status[c].startswith(("FAILED", "NO EXISTING"))]
    if not ok:
        sys.exit("no cell fetched; nothing to merge")

    # --- stitch + stream out
    w_all = w_m3 = None
    report, y0, y1 = [], None, None
    tmp_all, tmp_m3 = out / "_all.tmp", out / "_m3.tmp"
    for c in ok:
        df, stats = stitch(c, a, params)
        t = pa.Table.from_pandas(df, preserve_index=False)
        w_all = w_all or pq.ParquetWriter(tmp_all, t.schema, compression="zstd")
        w_all.write_table(t.cast(w_all.schema))
        m3 = df[["cell_id", "date"] + list(M3_COLS)].rename(columns=M3_COLS)
        t3 = pa.Table.from_pandas(m3, preserve_index=False)
        w_m3 = w_m3 or pq.ParquetWriter(tmp_m3, t3.schema, compression="zstd")
        w_m3.write_table(t3.cast(w_m3.schema))
        y0 = min(y0, df["date"].min().year) if y0 else df["date"].min().year
        y1 = max(y1, df["date"].max().year) if y1 else df["date"].max().year
        report.append(dict(cell_id=c, first_date=df["date"].min().date(), last_date=df["date"].max().date(),
                           n_days=len(df), status=status[c],
                           **{f"missing_{v}": int(df[k].isna().sum()) for k, v in M3_COLS.items()}, **stats))
    w_all.close(); w_m3.close()
    f_all, f_m3 = out / f"weather_daily_{y0}_{y1}.parquet", out / f"power_history_{y0}_{y1}.parquet"
    tmp_all.rename(f_all); tmp_m3.rename(f_m3)
    for c in cells:
        if c not in ok:
            report.append(dict(cell_id=c, status=status[c]))
    rep = pd.DataFrame(report)
    rep.to_csv(out / "fetch_report.csv", index=False)
    if (Path(a.power) / "units.json").exists():
        shutil.copy(Path(a.power) / "units.json", out / "units.json")
    elif units_any:
        (out / "units.json").write_text(json.dumps(units_any, indent=2))

    log(f"wrote {f_all.name} and {f_m3.name}: {len(ok)} cells, {y0}-{y1}")
    last_full = dt.date(dt.date.today().year - 1, 12, 31)
    short = rep[rep.get("last_date", pd.Series(dtype=object)).notna() & (pd.to_datetime(rep.get("last_date")) < pd.Timestamp(last_full))] \
        if "last_date" in rep else rep.iloc[0:0]
    if len(short):
        log(f"NOTE: {len(short)} cells end before {last_full} (last year incomplete) - M3 uses whole years; refetch the "
            f"existing period up to {last_full} with csb_power_weather.py if you need it")
    mae = [c for c in rep.columns if c.startswith("overlap_mae_")]
    if mae:
        log("overlap check (new request vs your existing values; ~0 expected):")
        print(rep[mae].describe().loc[["mean", "max"]].round(4).to_string())
        bad = rep[(rep.get("overlap_max_T2M_MAX", 0) > 0.5) | (rep.get("overlap_max_PRECTOTCORR", 0) > 1.0)]
        if len(bad):
            log(f"WARNING: {len(bad)} cells differ by >0.5 C / >1 mm in the overlap - POWER data version, community or "
                f"time standard may differ from your existing fetch. Use the same settings before trusting the join.")
    failed = [c for c in cells if c not in ok]
    if failed:
        log(f"WARNING: {len(failed)} cells FAILED; re-run the same command (finished cells are skipped): {failed[:5]}")
    log("done")


if __name__ == "__main__":
    main()