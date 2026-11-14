#!/usr/bin/env python3
"""Build a NASA POWER daily weather dataset (Parquet) for the fields in csb_bounds output.

Why cells, not fields
  POWER meteorology is a grid of about 0.5 deg lat x 0.625 deg lon (solar: 1 deg). Fields inside one cell get
  identical values, and NASA asks users not to repeat requests for the same grid location. So the script:
    1. snaps every field centroid to its POWER grid cell (plan),
    2. requests each distinct cell ONCE (fetch),
    3. writes TWO tables instead of one huge one (merge):
         field_cell_map.parquet  CSBID -> cell_id            (one row per field)
         weather_daily.parquet   cell_id, date, <parameters>  (one row per cell per day)
       Join them on cell_id when you need weather per field. A fully expanded table
       (16 M fields x thousands of days) would be tens of billions of rows.

Steps (all resumable; finished cells are skipped)
  plan   read csb_bounds batches, write cells.parquet + field_cell_map.parquet  (no network)
  fetch  call the POWER daily point API for each cell, one small Parquet per cell in <out>/cells/
  merge  stream the per-cell files into weather_daily.parquet, write units.json

Examples
  python csb_power_weather.py plan  --bounds ./csb_bounds --out ./power --state 19
  python csb_power_weather.py fetch --out ./power --start 20180101 --end 20251231 --workers 4
  python csb_power_weather.py merge --out ./power

Use fields later:
  m = pd.read_parquet("power/field_cell_map.parquet"); w = pd.read_parquet("power/weather_daily.parquet")
  fw = m[m.CSBID == "..."].merge(w, on="cell_id")

Deps: pip install pandas pyarrow numpy requests
"""
import argparse, json, sys, time, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import numpy as np
import pandas as pd

API = "https://power.larc.nasa.gov/api/temporal/daily/point"
LAT_STEP, LON_STEP = 0.5, 0.625             # POWER meteorology grid (MERRA-2 based). ASSUMED cell centres: lat = k*0.5, lon = -180 + k*0.625
DEFAULT_PARAMS = ["T2M", "T2M_MIN", "T2M_MAX", "T2MDEW", "RH2M", "QV2M", "PRECTOTCORR",
                  "WS2M", "WS10M", "WD10M", "PS", "ALLSKY_SFC_SW_DWN"]
MAX_PARAMS = 20                              # per POWER docs


def cell_centre(lon, lat):
    la = np.round(np.asarray(lat, "float64") / LAT_STEP) * LAT_STEP
    lo = -180.0 + np.round((np.asarray(lon, "float64") + 180.0) / LON_STEP) * LON_STEP
    return lo, la


def cell_id(lo, la):
    return np.char.add(np.char.add(np.char.mod("%+.1f", la), "_"), np.char.mod("%+.3f", lo))


# ------------------------------------------------------------------ plan
def cmd_plan(a):
    files = sorted(Path(a.bounds).glob("batch_*.parquet"))
    if not files:
        sys.exit(f"no batch_*.parquet in {a.bounds} (output of csb_bounds.py)")
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    maps, total = [], 0
    for f in files:
        cols = ["CSBID", "centroid_lon", "centroid_lat"]
        if a.state or a.county:
            import pyarrow.parquet as pq
            have = set(pq.read_schema(f).names)
            cols += [c for c in ("STATEFIPS", "CNTYFIPS") if c in have]
        df = pd.read_parquet(f, columns=cols)
        if a.state:
            df = df[df["STATEFIPS"] == str(a.state).zfill(2)]
        if a.county:
            df = df[df["CNTYFIPS"] == str(a.county).zfill(5)]
        if df.empty:
            continue
        lo, la = cell_centre(df["centroid_lon"].to_numpy(), df["centroid_lat"].to_numpy())
        m = pd.DataFrame({"CSBID": df["CSBID"].to_numpy(), "cell_id": cell_id(lo, la),
                          "cell_lon": lo, "cell_lat": la})
        maps.append(m); total += len(m)
    if not maps:
        sys.exit("no fields matched the filter")
    fm = pd.concat(maps, ignore_index=True)
    cells = (fm.groupby(["cell_id", "cell_lon", "cell_lat"]).size().rename("n_fields").reset_index())
    fm[["CSBID", "cell_id"]].to_parquet(out / "field_cell_map.parquet", compression="zstd", index=False)
    cells.to_parquet(out / "cells.parquet", compression="zstd", index=False)
    print(f"{total:,} fields -> {len(cells):,} distinct POWER cells (requests needed: {len(cells):,} x chunks)")
    print("wrote cells.parquet, field_cell_map.parquet")


# ------------------------------------------------------------------ fetch
def parse_response(js, params, fill=-999.0):
    """POWER daily JSON -> (DataFrame indexed by date, elevation, units dict)."""
    prop = js["properties"]["parameter"]
    hdr = js.get("header", {}) or {}
    fv = hdr.get("fill_value", fill)
    df = pd.DataFrame({p: pd.Series(prop[p]) for p in params if p in prop})
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df = df.astype("float64").where(lambda x: x != float(fv))       # fill value -> NaN
    df.index.name = "date"
    coords = (js.get("geometry", {}) or {}).get("coordinates", [])
    elev = coords[2] if len(coords) > 2 else None
    units = {k: {"units": v.get("units"), "longname": v.get("longname")}
             for k, v in (js.get("parameters", {}) or {}).items() if isinstance(v, dict)}
    return df, elev, units


def request(session, lon, lat, start, end, params, community, tstd, tries=5):
    q = {"parameters": ",".join(params), "community": community, "longitude": f"{lon:.4f}",
         "latitude": f"{lat:.4f}", "start": start, "end": end, "format": "JSON"}
    if tstd:
        q["time-standard"] = tstd
    last = None
    for i in range(tries):
        try:
            r = session.get(API, params=q, timeout=180)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code not in (408, 429, 500, 502, 503, 504):
                break
        except Exception as e:                               # network error / bad JSON
            last = repr(e)
        time.sleep(min(60, 2 ** (i + 1)))
    raise RuntimeError(last)


def year_chunks(start, end, n):
    s, e = dt.datetime.strptime(start, "%Y%m%d").date(), dt.datetime.strptime(end, "%Y%m%d").date()
    if n <= 0:
        return [(start, end)]
    out, y = [], s.year
    while y <= e.year:
        a0 = max(s, dt.date(y, 1, 1)); b0 = min(e, dt.date(y + n - 1, 12, 31))
        out.append((a0.strftime("%Y%m%d"), b0.strftime("%Y%m%d"))); y += n
    return out


def fetch_cell(row, a, params):
    import requests
    dst = Path(a.out) / "cells" / f"{row.cell_id}.parquet"
    if dst.exists():
        return row.cell_id, "skip", None
    s = requests.Session()
    parts, elev, units = [], None, {}
    for (s0, e0) in year_chunks(a.start, a.end, a.chunk_years):
        js = request(s, row.cell_lon, row.cell_lat, s0, e0, params, a.community, a.time_standard)
        df, el, un = parse_response(js, params)
        parts.append(df); elev = el if el is not None else elev; units = un or units
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated()]
    df.insert(0, "cell_id", row.cell_id)
    df["elevation_m"] = elev
    tmp = Path(str(dst) + ".tmp")
    df.reset_index().to_parquet(tmp, compression="zstd", index=False)
    tmp.rename(dst)
    return row.cell_id, "ok", units


def cmd_fetch(a):
    out = Path(a.out)
    cells = pd.read_parquet(out / "cells.parquet")
    (out / "cells").mkdir(exist_ok=True)
    params = a.parameters
    if len(params) > MAX_PARAMS:
        sys.exit(f"POWER allows at most {MAX_PARAMS} parameters per request")
    todo = [r for r in cells.itertuples() if not (out / "cells" / f"{r.cell_id}.parquet").exists()]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(todo):,} cells to fetch ({len(cells) - len(todo):,} already done), workers={a.workers}", flush=True)
    units_saved = (out / "units.json").exists()
    done = failed = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(fetch_cell, r, a, params): r.cell_id for r in todo}
        for fu in as_completed(futs):
            cid = futs[fu]
            try:
                _, st, units = fu.result()
                done += 1
                if units and not units_saved:
                    (out / "units.json").write_text(json.dumps(units, indent=2)); units_saved = True
            except Exception as e:
                failed += 1
                print(f"FAILED {cid}: {e}", file=sys.stderr, flush=True)
            if (done + failed) % 25 == 0:
                print(f"{done + failed}/{len(todo)} (failed {failed})", flush=True)
            time.sleep(a.pause)
    print(f"fetch finished: ok {done}, failed {failed}. Re-run the same command to retry failures.")


# ------------------------------------------------------------------ merge
def cmd_merge(a):
    import pyarrow.parquet as pq
    out = Path(a.out)
    files = sorted((out / "cells").glob("*.parquet"))
    if not files:
        sys.exit("no cell files; run fetch first")
    dst = out / "weather_daily.parquet"
    w, n = None, 0
    for f in files:
        t = pq.read_table(f)
        w = w or pq.ParquetWriter(dst, t.schema, compression="zstd")
        w.write_table(t.cast(w.schema)); n += t.num_rows
    w.close()
    cells = pd.read_parquet(out / "cells.parquet")
    missing = set(cells["cell_id"]) - {f.stem for f in files}
    print(f"wrote {dst}: {n:,} rows from {len(files):,} cells; cells still missing: {len(missing):,}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    pl = sp.add_parser("plan")
    pl.add_argument("--bounds", required=True, help="dir with batch_*.parquet from csb_bounds.py")
    pl.add_argument("--out", required=True)
    pl.add_argument("--state", help="state FIPS filter (needs STATEFIPS kept in csb_bounds output)")
    pl.add_argument("--county", help="county FIPS filter (needs CNTYFIPS kept)")
    pl.set_defaults(fn=cmd_plan)
    fe = sp.add_parser("fetch")
    fe.add_argument("--out", required=True)
    fe.add_argument("--start", default="20180101", help="YYYYMMDD")
    fe.add_argument("--end", default=(dt.date.today() - dt.timedelta(days=7)).strftime("%Y%m%d"), help="YYYYMMDD (default: today-7d; POWER lags real time)")
    fe.add_argument("--parameters", nargs="+", default=DEFAULT_PARAMS)
    fe.add_argument("--community", default="AG", help="AG (agroclimatology), RE or SB; changes units of some parameters")
    fe.add_argument("--time-standard", choices=["utc", "lst"], help="only sent if given; otherwise the server default")
    fe.add_argument("--chunk-years", type=int, default=0, help="0 = one request per cell for the whole range; N = split into N-year requests if long ranges fail")
    fe.add_argument("--workers", type=int, default=4, help="NASA asks for no more than 5 concurrent requests")
    fe.add_argument("--pause", type=float, default=0.2, help="seconds to sleep after each finished request")
    fe.add_argument("--limit", type=int, help="fetch only the first N pending cells (for testing)")
    fe.set_defaults(fn=cmd_fetch)
    me = sp.add_parser("merge"); me.add_argument("--out", required=True); me.set_defaults(fn=cmd_merge)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
