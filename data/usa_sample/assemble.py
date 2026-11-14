"""Join the per-source tables of the USA sample into the rule engine's inputs.

Inputs (all under --root, written by the sibling scripts and the existing source scripts):
    fields.csv                    sampled CSB fields (CSBID, STATEFIPS, CNTYFIPS, CSBACRES, lon/lat)
    cdl_history.parquet           CSBID, CDL2018..CDL2025 (CSB attributes; satellite estimates)
    gridmet/<year>.parquet        daily weather at the field point
    usdm/weekly.parquet           weekly Drought Monitor class at the field point
    yields/nass_yield.parquet     NASS county corn and soybean yields with lags
    rma/rma_col_county_year_all_crops.parquet   RMA cause-of-loss indemnities per county-year
    soil.parquet                  SSURGO soil block per field

Outputs:
    daily/<year>.parquet                    the daily schema build_season_summary.py reads
    season_summary/<year>/<county>.parquet  one row per field, same schema as the Iowa summaries
    fields.jsonl                            engine field records (history, soil block, state)

Not available in this sample: SMAP root-zone moisture and EDDI (columns are present and null).
Drought Monitor: -1 = no drought category that week, 0..4 = D0..D4.

    python data/usa_sample/assemble.py --root data/local/usa_sample --years 2021 2022 2023 2024 2025
"""

import argparse
import json
import sys
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "rule_engine" / "scripts"))
from build_season_summary import summary_query

ACRE_TO_HA = 0.404686
RMA_CAUSES = ("drought", "excess_moisture", "heat", "freeze", "hail")
SOIL_KEYS = (
    "mukey", "map_unit", "csr2", "aws_100cm_mm", "slope_pct", "drainage_class", "hydgrp",
    "nirr_class", "nirr_subclass", "tfact", "sand_pct", "clay_pct", "om_pct", "ph", "caco3_pct",
    "kw", "source",
)  # fmt: skip


def daily_query(root: Path, year: int) -> str:
    rma = ",\n".join(
        f"r.rma_{c}_indemnity_usd AS rma_lag1_{c}_indemnity_usd" for c in RMA_CAUSES
    )
    return f"""
    WITH f AS (
        SELECT CSBID, lpad(STATEFIPS::VARCHAR, 2, '0') || lpad(CNTYFIPS::VARCHAR, 3, '0') AS county_fips,
               centroid_lon, centroid_lat, CSBACRES AS area_acres
        FROM read_csv('{root}/fields.csv', types={{'CSBID': 'VARCHAR', 'STATEFIPS': 'VARCHAR', 'CNTYFIPS': 'VARCHAR'}})
    ),
    cdl AS (
        SELECT CSBID, try_cast(CDL{year - 1} AS SMALLINT) AS field_cdl_prev1,
               try_cast(CDL{year - 2} AS SMALLINT) AS field_cdl_prev2
        FROM read_parquet('{root}/cdl_history.parquet')
    ),
    y AS (
        SELECT county_fips,
            max(yield_bu_acre) FILTER (crop = 'CORN') AS yield_bu_acre_corn,
            max(yield_lag1_bu_acre) FILTER (crop = 'CORN') AS yield_lag1_bu_acre_corn,
            max(yield_mean_prev3_bu_acre) FILTER (crop = 'CORN') AS yield_mean_prev3_bu_acre_corn,
            max(yield_bu_acre) FILTER (crop = 'SOYBEANS') AS yield_bu_acre_soybeans,
            max(yield_lag1_bu_acre) FILTER (crop = 'SOYBEANS') AS yield_lag1_bu_acre_soybeans,
            max(yield_mean_prev3_bu_acre) FILTER (crop = 'SOYBEANS') AS yield_mean_prev3_bu_acre_soybeans
        FROM read_parquet('{root}/yields/nass_yield.parquet') WHERE year = {year} GROUP BY county_fips
    ),
    r AS (
        SELECT * FROM read_parquet('{root}/rma/rma_col_county_year_all_crops.parquet')
        WHERE year = {year - 1}
    ),
    g AS (
        SELECT *, (DATE '{year}-01-01' + (doy - 1)::INTEGER) AS date
        FROM read_parquet('{root}/gridmet/{year}.parquet')
    ),
    dm AS (
        SELECT lpad(CSBID, 15, '0') AS CSBID,  -- the drought script reads ids as numbers
               valid_date::DATE AS valid_date, coalesce(dm, -1)::DOUBLE AS drought_dm
        FROM read_parquet('{root}/usdm/weekly.parquet')
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


def write_fields(con, root: Path) -> int:
    cdl_columns = [
        row[0]
        for row in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{root}/cdl_history.parquet')"
        ).fetchall()
        if row[0].startswith("CDL")
    ]
    rows = con.execute(
        f"""
        SELECT f.CSBID, lpad(f.STATEFIPS::VARCHAR, 2, '0') AS state_fips,
               lpad(f.STATEFIPS::VARCHAR, 2, '0') || lpad(f.CNTYFIPS::VARCHAR, 3, '0') AS county_fips,
               f.CNTY, f.CSBACRES, f.centroid_lon, f.centroid_lat,
               {", ".join("c." + name for name in cdl_columns)},
               {", ".join("s." + key + " AS soil_" + key for key in SOIL_KEYS)}
        FROM read_csv('{root}/fields.csv', types={{'CSBID': 'VARCHAR', 'STATEFIPS': 'VARCHAR', 'CNTYFIPS': 'VARCHAR'}}) f
        LEFT JOIN read_parquet('{root}/cdl_history.parquet') c USING (CSBID)
        LEFT JOIN read_parquet('{root}/soil.parquet') s USING (CSBID)
        ORDER BY f.CSBID
        """
    ).fetchdf()
    with (root / "fields.jsonl").open("w") as handle:
        for row in rows.to_dict("records"):
            props = {
                "CSBID": row["CSBID"],
                "CSBACRES": row["CSBACRES"],
                "CNTY": row["CNTY"],
            }
            for name in cdl_columns:
                if row[name] == row[name] and row[name] is not None:
                    props[name] = int(row[name])
            soil = {
                key: row[f"soil_{key}"]
                for key in SOIL_KEYS
                if row[f"soil_{key}"] is not None
                and row[f"soil_{key}"] == row[f"soil_{key}"]
            }
            record = {
                "id": row["CSBID"],
                "sourceId": row["CSBID"],
                "stateFips": row["state_fips"],
                "countyFips": row["county_fips"],
                "county": row["CNTY"],
                "longitude": row["centroid_lon"],
                "latitude": row["centroid_lat"],
                "area": round(float(row["CSBACRES"]) * ACRE_TO_HA, 3),  # hectares
                "sourceYear": 2025,
                "sourceProperties": props,
            }
            if len(soil) > 1:  # more than the source label
                record["soil"] = soil
            handle.write(json.dumps(record) + "\n")
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--years", type=int, nargs="+", required=True)
    args = parser.parse_args()
    root = args.root
    con = duckdb.connect()
    (root / "daily").mkdir(exist_ok=True)
    for year in args.years:
        daily = root / "daily" / f"{year}.parquet"
        con.execute(f"COPY ({daily_query(root, year)}) TO '{daily}' (FORMAT PARQUET)")
        out = root / "season_summary" / str(year)
        out.mkdir(parents=True, exist_ok=True)
        for old in out.glob("*.parquet"):
            old.unlink()
        con.execute(
            f"CREATE OR REPLACE TABLE summary AS {summary_query(str(daily), None)}"
        )
        counties = [
            r[0]
            for r in con.execute("SELECT DISTINCT county_fips FROM summary").fetchall()
        ]
        for county in counties:
            con.execute(
                f"COPY (SELECT * FROM summary WHERE county_fips = '{county}' ORDER BY csbid) "
                f"TO '{out / (county + '.parquet')}' (FORMAT PARQUET)"
            )
        rows, with_yield, with_dm = con.execute(
            "SELECT count(*), count(yield_corn_bu_ac), count(*) FILTER (list_max(dm_max) IS NOT NULL) "
            "FROM summary"
        ).fetchone()
        print(
            f"{year}: {rows:,} fields in {len(counties):,} counties; corn county yield for "
            f"{with_yield:,}; Drought Monitor for {with_dm:,}",
            flush=True,
        )
    print(f"fields.jsonl: {write_fields(con, root):,} records", flush=True)


if __name__ == "__main__":
    main()
