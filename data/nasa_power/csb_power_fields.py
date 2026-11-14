#!/usr/bin/env python3
"""Create a per-field daily weather dataset from csb_power_weather.py output.

For each selected field (or custom point) the script:
  1. snaps its centroid lon/lat to the POWER grid cell (same rule as csb_power_weather.py),
  2. takes that cell's daily weather,
  3. writes rows  field x day  to ONE Parquet file, streaming cell by cell (flat memory).

Every field in a cell gets the SAME weather, because POWER is a ~0.5 x 0.625 deg grid. The output
therefore repeats values: rows = fields x days. For a whole state or country this is huge, so select
a subset (--state/--county/--ids/--points/--limit) or use the two-table layout instead.
A guard stops before writing more than --max-rows rows.

Field selection (use one source)
  --bounds DIR   csb_bounds output (batch_*.parquet with CSBID, centroid_lon, centroid_lat [, STATEFIPS, CNTYFIPS])
                 optional filters: --state 19  --county 19015  --ids ids.txt (one CSBID per line or CSV with CSBID column)  --limit N
  --points CSV   your own points: columns id, lon, lat (also accepts longitude/latitude or centroid_lon/centroid_lat)

Examples
  python csb_power_fields.py --power ./power --bounds ./csb_bounds --county 19015 --out boone_weather.parquet
  python csb_power_fields.py --power ./power --bounds ./csb_bounds --ids my_fields.csv --out my_fields_weather.parquet
  python csb_power_fields.py --power ./power --points pts.csv --out pts_weather.parquet

Needs csb_power_weather.py in the same folder. Deps: pip install pandas pyarrow numpy
"""
import argparse, sys
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from csb_power_weather import cell_centre, cell_id  # noqa: E402


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


def weather_for_cell(power, cid):
    f = Path(power) / "cells" / f"{cid}.parquet"
    if f.exists():
        return pq.read_table(f)
    wd = Path(power) / "weather_daily.parquet"
    if wd.exists():
        t = pq.read_table(wd, filters=[("cell_id", "=", cid)])
        return t if t.num_rows else None
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--power", required=True, help="output dir of csb_power_weather.py (cells/ and/or weather_daily.parquet)")
    p.add_argument("--bounds"); p.add_argument("--points")
    p.add_argument("--state"); p.add_argument("--county"); p.add_argument("--ids"); p.add_argument("--limit", type=int)
    p.add_argument("--out", required=True, help="output .parquet")
    p.add_argument("--max-rows", type=int, default=200_000_000, help="refuse to write more rows than this")
    p.add_argument("--chunk-rows", type=int, default=2_000_000, help="rows built in memory at a time")
    a = p.parse_args()

    fields = load_fields(a)
    lo, la = cell_centre(fields["centroid_lon"].to_numpy(), fields["centroid_lat"].to_numpy())
    fields["cell_id"] = cell_id(lo, la); fields["cell_lon"] = lo; fields["cell_lat"] = la
    cells = fields["cell_id"].value_counts()
    print(f"{len(fields):,} fields in {len(cells):,} cells", flush=True)

    # row estimate from the first available cell
    days = None
    for cid in cells.index:
        t = weather_for_cell(a.power, cid)
        if t is not None:
            days = t.num_rows; break
    if days is None:
        sys.exit("no weather found for any selected cell; run csb_power_weather.py fetch for these cells")
    est = len(fields) * days
    print(f"estimated rows: ~{est:,} ({days:,} days per cell)")
    if est > a.max_rows:
        sys.exit(f"estimate {est:,} exceeds --max-rows {a.max_rows:,}; select fewer fields or raise --max-rows")

    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(out) + ".tmp")
    writer, written, missing = None, 0, []
    for cid, g in fields.groupby("cell_id", sort=True):
        t = weather_for_cell(a.power, cid)
        if t is None:
            missing.append(cid); continue
        w = t.to_pandas().drop(columns=["cell_id"], errors="ignore")
        step = max(1, a.chunk_rows // max(1, len(w)))          # fields per chunk so that rows <= chunk_rows
        for i in range(0, len(g), step):
            gf = g.iloc[i:i + step].reset_index(drop=True)
            n, d = len(gf), len(w)
            res = gf.loc[gf.index.repeat(d)].reset_index(drop=True)
            res = pd.concat([res, pd.concat([w] * n, ignore_index=True)], axis=1)
            res = res.sort_values(["CSBID", "date"], kind="stable")
            tb = pa.Table.from_pandas(res, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(tmp, tb.schema, compression="zstd")
            writer.write_table(tb.cast(writer.schema)); written += len(res)
    if writer is None:
        sys.exit("nothing written: weather missing for all selected cells")
    writer.close(); tmp.rename(out)
    print(f"wrote {out}: {written:,} rows")
    if missing:
        print(f"WARNING: no weather for {len(missing)} cells (fields skipped): {missing[:5]}{' ...' if len(missing) > 5 else ''}")


if __name__ == "__main__":
    main()
