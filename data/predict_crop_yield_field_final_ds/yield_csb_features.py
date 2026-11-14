#!/usr/bin/env python3
"""Step 2 - crop-rotation features per county and target year from CSB/CDL (out-of-core, DuckDB).

Input : <work>/attrs/batch_*.parquet from csb_pipeline.py ingest (CSBID, STATEFIPS, CNTYFIPS, CSBACRES, CDL<yyyy>)
Output: <out>/csb_county_year.parquet, one row per county x target year t:
  county_fips, year,
  corn_share_prev1, soy_share_prev1                 CDL{t-1}: acres of corn (1) / soybeans (5) over acres with a KNOWN crop in t-1
  corn_to_soy_share_prev2, soy_to_corn_share_prev2  CDL{t-2} -> CDL{t-1}: corn->soy / soy->corn acres over acres with BOTH years known
  (QA) known_acres_prev1, known_acres_prev2

"Known" = CDL code present and > 0 (0 = background / no data). Weights are CSBACRES. A year t is produced only when the needed
CDL columns exist in the data (CSB 2025 edition: CDL2018-2025 -> prev1 from t=2019, prev2 from t=2020; --years limits the list).

Caveats
  * CSB polygon boundaries are built from the whole 2018-2025 history, so the set of polygons carries a mild look-ahead for older t;
    the crop codes used are only those of t-1 and t-2.
  * CDL for year t-1 is published in January-February of year t; do not assume it exists on 1 January.
  * Shares describe the CSB polygons (cropland-like land), not the county's total area.

County key is always the 5-digit state+county FIPS. --state all | 19 | 19,20 (default all).
Example: python yield_csb_features.py --attrs ./csb_work/attrs --out ./yield_work
Deps: pip install duckdb pandas pyarrow
"""
import argparse, re, sys
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq

CORN, SOY = 1, 5


def state_cond(state, col="STATEFIPS"):
    """SQL predicate for --state: 'all', one FIPS ('19') or a comma list ('19,20')"""
    s = str(state).strip().lower()
    if s in ("all", "*", ""):
        return "TRUE"
    return f"lpad(CAST({col} AS VARCHAR), 2, '0') IN (" + ",".join(f"'{x.strip().zfill(2)}'" for x in s.split(",")) + ")"


CKEY = ("CASE WHEN length(CAST(CNTYFIPS AS VARCHAR)) <= 3 THEN lpad(CAST(STATEFIPS AS VARCHAR), 2, '0') || lpad(CAST(CNTYFIPS AS VARCHAR), 3, '0') "
        "ELSE lpad(CAST(CNTYFIPS AS VARCHAR), 5, '0') END")      # 5-digit state+county key (so counties of different states never collide)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--attrs", required=True, help="<work>/attrs from csb_pipeline.py ingest")
    p.add_argument("--out", required=True)
    p.add_argument("--state", default="all", help="all | FIPS | FIPS,FIPS (default all)")
    p.add_argument("--years", type=int, nargs="*", help="target years t (default: every t the data allows)")
    p.add_argument("--memory", default="2GB")
    a = p.parse_args()
    import duckdb
    files = sorted(Path(a.attrs).glob("batch_*.parquet"))
    if not files:
        sys.exit("no batches in --attrs")
    cdl = sorted(int(c[3:]) for c in pq.read_schema(files[0]).names if re.fullmatch(r"CDL\d{4}", c))
    if not cdl:
        sys.exit("no CDLyyyy columns")
    print("CDL years in data:", cdl)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{a.memory}'")
    con.execute(f"PRAGMA temp_directory='{(Path(a.out) / '_duckdb_spill').as_posix()}'")
    src = (Path(a.attrs) / "batch_*.parquet").as_posix()
    con.execute(f"CREATE VIEW f AS SELECT {CKEY} AS CNTYFIPS, CSBACRES, {', '.join(f'CDL{y}' for y in cdl)} "
                f"FROM read_parquet('{src}') WHERE {state_cond(a.state)}")
    targets = a.years or list(range(min(cdl) + 1, max(cdl) + 2))
    parts = []
    for t in targets:
        p1, p2 = t - 1, t - 2
        if p1 not in cdl:
            continue
        k1 = f"CDL{p1} > 0"
        sel = [f"CNTYFIPS AS county_fips", f"{t} AS year",
               f"coalesce(sum(CASE WHEN CDL{p1} = {CORN} THEN CSBACRES END), 0) / nullif(sum(CASE WHEN {k1} THEN CSBACRES END), 0) AS corn_share_prev1",
               f"coalesce(sum(CASE WHEN CDL{p1} = {SOY} THEN CSBACRES END), 0) / nullif(sum(CASE WHEN {k1} THEN CSBACRES END), 0) AS soy_share_prev1",
               f"sum(CASE WHEN {k1} THEN CSBACRES END) AS known_acres_prev1"]
        if p2 in cdl:
            k2 = f"CDL{p1} > 0 AND CDL{p2} > 0"
            sel += [f"coalesce(sum(CASE WHEN CDL{p2} = {CORN} AND CDL{p1} = {SOY} THEN CSBACRES END), 0) / nullif(sum(CASE WHEN {k2} THEN CSBACRES END), 0) AS corn_to_soy_share_prev2",
                    f"coalesce(sum(CASE WHEN CDL{p2} = {SOY} AND CDL{p1} = {CORN} THEN CSBACRES END), 0) / nullif(sum(CASE WHEN {k2} THEN CSBACRES END), 0) AS soy_to_corn_share_prev2",
                    f"sum(CASE WHEN {k2} THEN CSBACRES END) AS known_acres_prev2"]
        else:
            sel += ["NULL::DOUBLE AS corn_to_soy_share_prev2", "NULL::DOUBLE AS soy_to_corn_share_prev2", "NULL::DOUBLE AS known_acres_prev2"]
        d = con.execute(f"SELECT {', '.join(sel)} FROM f GROUP BY CNTYFIPS").df()
        parts.append(d)
        print(f"  t={t}: {len(d)} counties", flush=True)
    if not parts:
        sys.exit("no target year could be built")
    r = pd.concat(parts, ignore_index=True)
    fn = Path(a.out) / "csb_county_year.parquet"
    r.to_parquet(fn, compression="zstd", index=False)
    print("wrote", fn, f"({len(r)} rows)")


if __name__ == "__main__":
    main()
