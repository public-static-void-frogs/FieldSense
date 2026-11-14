"""Collapse daily field parquet files into one weekly-binned season summary row per field.

Input: one parquet per county per year with daily rows (CSBID, date, gridMET, SMAP, Drought
Monitor, RMA and CDL columns). Output: one parquet per county with one row per CSBID that holds
scalar context plus fixed-length weekly lists starting at day-of-year 91 (1 April).

    python rule_engine/scripts/build_season_summary.py \
        --source data/local/field_daily_2025_ext/2025 --out data/local/season_summary/2025
    python rule_engine/scripts/build_season_summary.py --source ... --county 19015 \
        --sample-csbids 191825000014220,191825000014226 --out rule_engine/tests/fixtures/season_summary/2025
"""

import argparse
from pathlib import Path

import duckdb

WEEK0_DOY = 91
WEEKS = 31

SCALARS = """
    CSBID AS csbid,
    any_value(county_fips) AS county_fips,
    any_value(year) AS year,
    any_value(centroid_lon) AS centroid_lon,
    any_value(centroid_lat) AS centroid_lat,
    any_value(area_acres) AS area_acres,
    any_value(field_cdl_prev1) AS cdl_prev1,
    any_value(field_cdl_prev2) AS cdl_prev2,
    any_value(yield_bu_acre_corn) AS yield_corn_bu_ac,
    any_value(yield_lag1_bu_acre_corn) AS yield_corn_lag1_bu_ac,
    any_value(yield_mean_prev3_bu_acre_corn) AS yield_corn_prev3_bu_ac,
    any_value(yield_bu_acre_soybeans) AS yield_soy_bu_ac,
    any_value(yield_lag1_bu_acre_soybeans) AS yield_soy_lag1_bu_ac,
    any_value(yield_mean_prev3_bu_acre_soybeans) AS yield_soy_prev3_bu_ac,
    any_value(rma_lag1_total_indemnity_usd) AS rma_lag1_total_usd,
    any_value(rma_lag1_drought_share) AS rma_lag1_drought_share,
    any_value(rma_lag1_excess_moisture_indemnity_usd / nullif(rma_lag1_total_indemnity_usd, 0))
        AS rma_lag1_excess_moisture_share,
    any_value(rma_lag1_heat_indemnity_usd / nullif(rma_lag1_total_indemnity_usd, 0))
        AS rma_lag1_heat_share,
    any_value(rma_lag1_freeze_indemnity_usd / nullif(rma_lag1_total_indemnity_usd, 0))
        AS rma_lag1_freeze_share,
    any_value(rma_lag1_hail_indemnity_usd / nullif(rma_lag1_total_indemnity_usd, 0))
        AS rma_lag1_hail_share
"""

# metric name -> (daily expression, weekly aggregate, cast)
WEEKLY = {
    "tmax_max": ("gridmet_tmax_c", "max", "DOUBLE"),
    "tmin_min": ("gridmet_tmin_c", "min", "DOUBLE"),
    "pr_mm": ("gridmet_pr_mm", "sum", "DOUBLE"),
    "eto_mm": ("gridmet_eto_grass_mm", "sum", "DOUBLE"),
    "rz_pctl_min": ("smap_sm_rootzone_pctl", "min", "DOUBLE"),
    "rz_pctl_mean": ("smap_sm_rootzone_pctl", "avg", "DOUBLE"),
    "dm_max": ("drought_dm", "max", "DOUBLE"),
    "eddi_max": ("eddi_04wk", "max", "DOUBLE"),
    "tmax_ge35_days": ("CASE WHEN gridmet_tmax_c >= 35 THEN 1 END", "count", "INTEGER"),
    "tmax_ge30_days": ("CASE WHEN gridmet_tmax_c >= 30 THEN 1 END", "count", "INTEGER"),
    "tmin_le0_days": ("CASE WHEN gridmet_tmin_c <= 0 THEN 1 END", "count", "INTEGER"),
    "tmin_lem2_days": ("CASE WHEN gridmet_tmin_c <= -2 THEN 1 END", "count", "INTEGER"),
    "pr_ge25_days": ("CASE WHEN gridmet_pr_mm >= 25 THEN 1 END", "count", "INTEGER"),
    "rz_lt20_days": ("CASE WHEN smap_sm_rootzone_pctl < 20 THEN 1 END", "count", "INTEGER"),
    "obs_days": ("gridmet_tmax_c", "count", "INTEGER"),
}


def _weekly_sql() -> tuple[str, str]:
    per_week = ",\n".join(
        f"{agg}({expr})::{cast} AS {name}" for name, (expr, agg, cast) in WEEKLY.items()
    )
    lists = ",\n".join(f"list(w.{name} ORDER BY g.week) AS {name}" for name in WEEKLY)
    return per_week, lists


def summary_query(source: str, csbids: list[str] | None) -> str:
    per_week, lists = _weekly_sql()
    where = ""
    if csbids:
        quoted = ", ".join(f"'{c}'" for c in csbids)
        where = f"WHERE CSBID IN ({quoted})"
    return f"""
    WITH daily AS (
        SELECT *, CSBID AS csbid, ((doy - {WEEK0_DOY}) // 7)::INTEGER AS week
        FROM read_parquet('{source}') {where}
    ),
    scalars AS (SELECT {SCALARS} FROM daily GROUP BY CSBID),
    weekly AS (
        SELECT csbid, week, {per_week}
        FROM daily WHERE week >= 0 AND week < {WEEKS} GROUP BY csbid, week
    ),
    grid AS (SELECT s.csbid, r.range::INTEGER AS week FROM scalars s, range({WEEKS}) r),
    series AS (
        SELECT g.csbid, {lists}
        FROM grid g LEFT JOIN weekly w ON w.csbid = g.csbid AND w.week = g.week
        GROUP BY g.csbid
    )
    SELECT s.*, series.* EXCLUDE (csbid)
    FROM scalars s JOIN series USING (csbid) ORDER BY s.csbid
    """


def build(source: Path, out: Path, county: str | None, csbids: list[str] | None) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(source.glob("*.parquet"))
    if county:
        files = [f for f in files if f.stem == county]
    written = []
    con = duckdb.connect()
    for path in files:
        target = out / path.name
        con.execute(f"COPY ({summary_query(str(path), csbids)}) TO '{target}' (FORMAT PARQUET)")
        written.append(target)
        print(f"{path.name}: wrote {target}")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", required=True, type=Path, help="folder of daily parquets")
    parser.add_argument("--out", required=True, type=Path, help="output folder")
    parser.add_argument("--county", help="only this county FIPS (file stem)")
    parser.add_argument("--sample-csbids", help="comma-separated CSBIDs to keep (fixtures)")
    args = parser.parse_args()
    csbids = args.sample_csbids.split(",") if args.sample_csbids else None
    build(args.source, args.out, args.county, csbids)


if __name__ == "__main__":
    main()
