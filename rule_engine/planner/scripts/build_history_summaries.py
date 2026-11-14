"""Season summaries for years before the national sample starts (2021).

Same output schema and layout as data/usa_sample/assemble.py, so SeasonSummaryStore reads both.
Differences: CDL columns that do not exist (the CSB attributes start in 2018) become NULL, and
nothing in the sample folder is rewritten.

    python rule_engine/planner/scripts/build_history_summaries.py \
        --sample data/local/usa_sample --work data/local/planner --years 2015 2016 2017 2018 2019 2020

Inputs under --work: gridmet/<year>.parquet, usdm/weekly_*.parquet,
rma*/rma_col_county_year_all_crops.parquet, yields/nass_yield.parquet (years before 2015).
From --sample: fields.csv, cdl_history.parquet, yields/nass_yield.parquet.
Output: <work>/season_summary/<year>/<county>.parquet.
SMAP root-zone moisture and EDDI are not joined (null), as in the national sample.

The sources start at different times, and a year before a source starts gets NULL for it:
gridMET weather 1979, county yields before that, RMA cause of loss 1989 (so the lag-1 loss
columns start in 1990), the Drought Monitor 2000.

    bash rule_engine/planner/scripts/fetch_gridmet_history.sh 1981 2014
    python rule_engine/planner/scripts/build_history_summaries.py \
        --sample data/local/usa_sample --work data/local/planner --years $(seq 1981 2014)
"""

import argparse
import sys
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "rule_engine" / "scripts"))
from build_season_summary import summary_query  # noqa: E402

RMA_CAUSES = ("drought", "excess_moisture", "heat", "freeze", "hail")


def files(paths: list[Path]) -> str:
    """A DuckDB list literal of parquet paths."""
    return "[" + ", ".join(f"'{p}'" for p in paths) + "]"


def daily_query(
    sample: Path,
    work: Path,
    year: int,
    cdl_columns: set[str],
    usdm: list[Path],
    rma_files: list[Path],
    yields: list[Path],
) -> str:
    def cdl(offset: int) -> str:
        name = f"CDL{year - offset}"
        return f"try_cast({name} AS SMALLINT)" if name in cdl_columns else "NULL::SMALLINT"

    rma = ",\n".join(f"r.rma_{c}_indemnity_usd AS rma_lag1_{c}_indemnity_usd" for c in RMA_CAUSES)
    return f"""
    WITH f AS (
        SELECT CSBID, lpad(STATEFIPS::VARCHAR, 2, '0') || lpad(CNTYFIPS::VARCHAR, 3, '0') AS county_fips,
               centroid_lon, centroid_lat, CSBACRES AS area_acres
        FROM read_csv('{sample}/fields.csv',
                      types={{'CSBID': 'VARCHAR', 'STATEFIPS': 'VARCHAR', 'CNTYFIPS': 'VARCHAR'}})
    ),
    cdl AS (
        SELECT CSBID, {cdl(1)} AS field_cdl_prev1, {cdl(2)} AS field_cdl_prev2
        FROM read_parquet('{sample}/cdl_history.parquet')
    ),
    y AS (
        SELECT county_fips,
            max(yield_bu_acre) FILTER (crop = 'CORN') AS yield_bu_acre_corn,
            max(yield_lag1_bu_acre) FILTER (crop = 'CORN') AS yield_lag1_bu_acre_corn,
            max(yield_mean_prev3_bu_acre) FILTER (crop = 'CORN') AS yield_mean_prev3_bu_acre_corn,
            max(yield_bu_acre) FILTER (crop = 'SOYBEANS') AS yield_bu_acre_soybeans,
            max(yield_lag1_bu_acre) FILTER (crop = 'SOYBEANS') AS yield_lag1_bu_acre_soybeans,
            max(yield_mean_prev3_bu_acre) FILTER (crop = 'SOYBEANS')
                AS yield_mean_prev3_bu_acre_soybeans
        FROM read_parquet({files(yields)}, union_by_name=true)
        WHERE year = {year} GROUP BY county_fips
    ),
    r AS (
        SELECT * FROM read_parquet({files(rma_files)}, union_by_name=true)
        WHERE year = {year - 1}
    ),
    g AS (
        SELECT *, (DATE '{year}-01-01' + (doy - 1)::INTEGER) AS date
        FROM read_parquet('{work}/gridmet/{year}.parquet')
    ),
    dm AS (
        SELECT lpad(CSBID::VARCHAR, 15, '0') AS CSBID,  -- the drought script reads ids as numbers
               valid_date::DATE AS valid_date, coalesce(dm, -1)::DOUBLE AS drought_dm
        FROM read_parquet({files(usdm)}, union_by_name=true)
    )
    SELECT g.CSBID, f.county_fips, {year} AS year, g.doy::BIGINT AS doy, g.date,
        f.centroid_lon, f.centroid_lat, f.area_acres,
        cdl.field_cdl_prev1, cdl.field_cdl_prev2,
        y.* EXCLUDE (county_fips),
        r.rma_total_indemnity_usd AS rma_lag1_total_indemnity_usd,
        r.rma_drought_share AS rma_lag1_drought_share,
        {rma},
        g.gridmet_tmax_c, g.gridmet_tmin_c, g.gridmet_pr_mm, g.gridmet_eto_grass_mm,
        NULL::FLOAT AS smap_sm_rootzone_pctl,
        dm.drought_dm, dm.valid_date AS drought_valid_date,
        NULL::FLOAT AS eddi_04wk
    FROM g JOIN f USING (CSBID)
    LEFT JOIN cdl USING (CSBID)
    LEFT JOIN y USING (county_fips)
    LEFT JOIN r USING (county_fips)
    ASOF LEFT JOIN dm ON dm.CSBID = g.CSBID AND dm.valid_date <= g.date
    """


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sample", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--usdm", type=Path, nargs="+", help="default <work>/usdm/weekly_*.parquet")
    parser.add_argument("--years", type=int, nargs="+", required=True)
    args = parser.parse_args()
    usdm = args.usdm or sorted((args.work / "usdm").glob("weekly_*.parquet"))
    rma_files = sorted(args.work.glob("rma*/rma_col_county_year_all_crops.parquet"))
    yields = [args.sample / "yields" / "nass_yield.parquet"]
    yields += [p for p in [args.work / "yields" / "nass_yield.parquet"] if p.exists()]
    con = duckdb.connect()
    cdl_columns = {
        row[0]
        for row in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{args.sample}/cdl_history.parquet')"
        ).fetchall()
    }
    (args.work / "daily").mkdir(parents=True, exist_ok=True)
    for year in args.years:
        daily = args.work / "daily" / f"{year}.parquet"
        query = daily_query(args.sample, args.work, year, cdl_columns, usdm, rma_files, yields)
        con.execute(f"COPY ({query}) TO '{daily}' (FORMAT PARQUET)")
        out = args.work / "season_summary" / str(year)
        out.mkdir(parents=True, exist_ok=True)
        for old in out.glob("*.parquet"):
            old.unlink()
        con.execute(f"CREATE OR REPLACE TABLE summary AS {summary_query(str(daily), None)}")
        counties = [
            r[0] for r in con.execute("SELECT DISTINCT county_fips FROM summary").fetchall()
        ]
        for county in counties:
            con.execute(
                f"COPY (SELECT * FROM summary WHERE county_fips = '{county}' ORDER BY csbid) "
                f"TO '{out / (county + '.parquet')}' (FORMAT PARQUET)"
            )
        rows, with_yield, with_dm, with_rma = con.execute(
            "SELECT count(*), count(yield_corn_bu_ac), "
            "count(*) FILTER (list_max(dm_max) IS NOT NULL), count(rma_lag1_total_usd) FROM summary"
        ).fetchone()
        daily.unlink()  # the daily table is only an intermediate (about 150 MB per year)
        print(
            f"{year}: {rows:,} fields in {len(counties):,} counties; corn county yield for "
            f"{with_yield:,}; Drought Monitor for {with_dm:,}; RMA lag-1 for {with_rma:,}",
            flush=True,
        )


if __name__ == "__main__":
    main()
