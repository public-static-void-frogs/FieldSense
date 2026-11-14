#!/usr/bin/env python3
"""Step 4 (optional) - county drought area share from the per-field weekly U.S. Drought Monitor table of csb_drought.py.

Input : --drought  Parquet from `csb_drought.py weekly` (CSBID, valid_date, dm, release_date_est; dm null = no drought class)
        --attrs    <work>/attrs from csb_pipeline.py ingest (CSBID, STATEFIPS, CNTYFIPS, CSBACRES)
Output: <out>/drought_county_year.parquet, one row per county x target year t:
  county_fips, year, drought_area_share, drought_valid_date, (QA) drought_rows_share

For each year t the map used is the LATEST one in the table whose release_date_est <= --asof (default 04-15 of year t), i.e. the latest
map actually present in the file and published by the as-of date. release_date_est is an estimate (valid Tuesday + 2 days), so choose an as-of date
with a few days of slack. drought_area_share = CSBACRES of fields with dm >= --min-dm (default 1 = D1 moderate drought or worse; D0 is
"abnormally dry", not drought) divided by the county's total CSBACRES. A field with no row for that date counts as "not in drought".
`drought_rows_share` = share of the county's acres that have a row on that date; if it is far below 1, the table was built with
--drop-none or for a subset of fields, and the share is relative to ALL fields of the county in --attrs.

--level field : instead of the county share, write the class of EACH field for the chosen map: <out>/drought_field_year/year=<t>.parquet with
  CSBID, year, drought_dm (0-4, null = no drought class or no row), drought_valid_date. Used by yield_fields_assemble.py.

Memory: only the one selected date per year is read from the (possibly huge) drought table.
Example: python yield_drought.py --drought ./drought/ia_weekly.parquet --attrs ./csb_work/attrs --out ./yield_work --years 2019 2020 2021
Deps: pip install duckdb pandas pyarrow
"""
import argparse, sys
from pathlib import Path
import pandas as pd


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
    p.add_argument("--drought", required=True); p.add_argument("--attrs", required=True); p.add_argument("--out", required=True)
    p.add_argument("--state", default="all", help="all | FIPS | FIPS,FIPS (default all)"); p.add_argument("--years", type=int, nargs="+", help="target years (default: all with a map before the as-of date)")
    p.add_argument("--asof", default="04-15", help="MM-DD in year t (default 04-15)")
    p.add_argument("--max-age-days", type=int, default=28, help="skip a year if the chosen map is older than this at the as-of date (stale table)")
    p.add_argument("--min-dm", type=int, default=1, choices=[0, 1, 2, 3, 4])
    p.add_argument("--level", choices=["county", "field"], default="county")
    p.add_argument("--memory", default="2GB")
    a = p.parse_args()
    import duckdb
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{a.memory}'")
    Path(a.out).mkdir(parents=True, exist_ok=True)
    con.execute(f"PRAGMA temp_directory='{(Path(a.out) / '_duckdb_spill').as_posix()}'")
    dr = Path(a.drought).as_posix()
    dr_src = f"read_parquet('{dr}')" if not Path(a.drought).is_dir() else f"read_parquet('{dr}/*.parquet')"
    con.execute(f"""CREATE TABLE tot AS SELECT {CKEY} AS county_fips, sum(CSBACRES) AS acres
        FROM read_parquet('{(Path(a.attrs) / 'batch_*.parquet').as_posix()}') WHERE {state_cond(a.state)} GROUP BY 1""")
    dates = con.execute(f"SELECT DISTINCT CAST(valid_date AS DATE) AS v, CAST(release_date_est AS DATE) AS r FROM {dr_src}").df()
    if dates.empty:
        sys.exit("empty drought table")
    dates["r"] = pd.to_datetime(dates["r"]); dates["v"] = pd.to_datetime(dates["v"])
    years = a.years or sorted(set(dates["r"].dt.year))
    rows = []
    for t in years:
        asof = pd.Timestamp(f"{t}-{a.asof}")
        ok = dates[dates["r"] <= asof]
        ok = ok[ok["r"].dt.year == t] if (ok["r"].dt.year == t).any() else ok.iloc[0:0]   # a map from the previous year is too stale
        if ok.empty:
            print(f"  t={t}: no map released by {asof.date()} in the table; skipped"); continue
        v = ok.sort_values("v")["v"].iloc[-1]
        if (asof - v).days > a.max_age_days:
            print(f"  t={t}: newest map {v.date()} is {(asof - v).days} days older than {asof.date()}; skipped (--max-age-days)"); continue
        if a.level == "field":
            fd = Path(a.out) / "drought_field_year"; fd.mkdir(exist_ok=True)
            tmpf = fd / f"year={t}.parquet.part"
            con.execute(f"""COPY (SELECT f.CSBID, {t} AS year, x.dm AS drought_dm, DATE '{v.date()}' AS drought_valid_date
                FROM read_parquet('{(Path(a.attrs) / 'batch_*.parquet').as_posix()}') f
                LEFT JOIN (SELECT CSBID, max(dm) AS dm FROM {dr_src} WHERE CAST(valid_date AS DATE) = DATE '{v.date()}' GROUP BY CSBID) x USING (CSBID)
                WHERE {state_cond(a.state, 'f.STATEFIPS')}) TO '{tmpf.as_posix()}' (FORMAT PARQUET, COMPRESSION zstd)""")
            tmpf.replace(fd / f"year={t}.parquet"); print(f"  t={t}: map {v.date()} written", flush=True); rows.append(None); continue
        d = con.execute(f"""
            SELECT {CKEY.replace('CNTYFIPS', 'f.CNTYFIPS').replace('STATEFIPS', 'f.STATEFIPS')} AS county_fips,
                   sum(CASE WHEN x.dm >= {a.min_dm} THEN f.CSBACRES END) AS drought_acres,
                   sum(f.CSBACRES) AS present_acres
            FROM read_parquet('{(Path(a.attrs) / 'batch_*.parquet').as_posix()}') f
            JOIN (SELECT CSBID, dm FROM {dr_src} WHERE CAST(valid_date AS DATE) = DATE '{v.date()}') x USING (CSBID)
            WHERE {state_cond(a.state, 'f.STATEFIPS')} GROUP BY 1""").df()
        d = d.merge(con.execute("SELECT * FROM tot").df(), on="county_fips", how="right")
        d["drought_area_share"] = d["drought_acres"].fillna(0) / d["acres"]
        d["drought_rows_share"] = d["present_acres"].fillna(0) / d["acres"]
        d.loc[d["present_acres"].isna(), "drought_area_share"] = float("nan")     # no data for the county at all
        d["year"] = t; d["drought_valid_date"] = v.date().isoformat()
        rows.append(d[["county_fips", "year", "drought_area_share", "drought_valid_date", "drought_rows_share"]])
        print(f"  t={t}: map {v.date()}  median rows share {d['drought_rows_share'].median():.2f}", flush=True)
    if not rows:
        sys.exit("nothing produced")
    if a.level == "field":
        print("wrote", Path(a.out) / "drought_field_year"); return
    r = pd.concat(rows, ignore_index=True)
    fn = Path(a.out) / "drought_county_year.parquet"; r.to_parquet(fn, compression="zstd", index=False)
    print("wrote", fn, f"({len(r)} rows)")


if __name__ == "__main__":
    main()
