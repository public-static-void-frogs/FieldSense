"""Collapse field_dataset to one row per county x year x crop.

The label in field_dataset is the NASS county yield, so the county-year is the real unit of analysis.
Field-level inputs are turned into area-weighted county features, including the neighbour shares that
are empty in the source table (computed here from the field_* history flags, 2019-2025 only).

Usage: python 01_county_panel.py --dataset path/to/field_dataset --out county_panel.csv
"""
import argparse

import duckdb

# CDL classes grouped for the "what else is around" shares
HAY_PASTURE = (36, 37, 62, 176)                     # alfalfa, other hay, pasture/grass, grassland/pasture
NON_AG = (111, 121, 122, 123, 124, 131, 141, 142, 143, 152, 190, 195)  # water, developed, barren, forest, shrub, wetland

SQL = """
CREATE VIEW fd AS
SELECT * EXCLUDE (drought_dm), CAST(drought_dm AS DOUBLE) AS drought_dm
FROM read_parquet('{dataset}/year=*/part.parquet', union_by_name = true);

-- the table has one row per candidate crop; keep one row per field-year for field-level features
CREATE VIEW f AS
SELECT DISTINCT CSBID, year, county_fips, area_acres, power_cell_id, imerg_cell_id,
       field_cdl_prev1, field_cdl_prev2, field_corn_prev1, field_soy_prev1,
       field_corn_to_soy_prev2, field_soy_to_corn_prev2,
       power_t2m_prev_season_mean, power_tmin_prev_season_mean, power_tmax_prev_season_mean,
       power_cold_days_prev_season, power_hot_days_prev_season, power_precip_prev_season_sum,
       power_dry_days_prev_season, power_solar_prev_season,
       imerg_precip_prev_season_sum, imerg_dry_spell_prev_season,
       drought_dm, drought_valid_date
FROM fd;

CREATE TABLE county AS
SELECT county_fips, year,
       count(*) AS n_fields,
       sum(area_acres) AS area_acres,
       -- area-weighted previous-summer weather (a county can span several POWER/IMERG cells)
       {weather},
       -- April drought snapshot: null class means "not in drought" (USDM draws only D0+)
       CASE WHEN bool_or(drought_valid_date IS NOT NULL) THEN
         sum(area_acres * coalesce(drought_dm, -1)) / sum(area_acres) END AS drought_class_april,
       CASE WHEN bool_or(drought_valid_date IS NOT NULL) THEN
         sum(area_acres * (coalesce(drought_dm, -1) >= 1)::INT) / sum(area_acres) END AS drought_d1plus_share_april,
       -- neighbour shares from the field histories (null before CSB covers t-1 / t-2)
       sum(area_acres * field_corn_prev1) / sum(CASE WHEN field_corn_prev1 IS NOT NULL THEN area_acres END) AS corn_share_prev1,
       sum(area_acres * field_soy_prev1) / sum(CASE WHEN field_soy_prev1 IS NOT NULL THEN area_acres END) AS soy_share_prev1,
       sum(area_acres * field_corn_to_soy_prev2) / sum(CASE WHEN field_corn_to_soy_prev2 IS NOT NULL THEN area_acres END) AS corn_to_soy_share_prev2,
       sum(area_acres * field_soy_to_corn_prev2) / sum(CASE WHEN field_soy_to_corn_prev2 IS NOT NULL THEN area_acres END) AS soy_to_corn_share_prev2,
       sum(area_acres * (field_cdl_prev1 = 1 AND field_cdl_prev2 = 1)::INT)
         / sum(CASE WHEN field_cdl_prev1 IS NOT NULL AND field_cdl_prev2 IS NOT NULL THEN area_acres END) AS corn_corn_share_prev2,
       sum(area_acres * (field_cdl_prev1 IN {hay})::INT) / sum(CASE WHEN field_cdl_prev1 IS NOT NULL THEN area_acres END) AS hay_pasture_share_prev1,
       sum(area_acres * (field_cdl_prev1 IN {nonag})::INT) / sum(CASE WHEN field_cdl_prev1 IS NOT NULL THEN area_acres END) AS nonag_share_prev1
FROM f
GROUP BY ALL;

CREATE TABLE target AS
SELECT county_fips, any_value(county_name) AS county_name, year, crop,
       any_value(yield_bu_acre) AS yield_bu_acre,
       any_value(yield_lag1_bu_acre) AS yield_lag1,
       any_value(yield_mean_prev3_bu_acre) AS yield_mean_prev3,
       any_value(yield_prev3_count) AS yield_prev3_count,
       count(DISTINCT yield_bu_acre) AS n_distinct_yield
FROM fd
GROUP BY county_fips, year, crop;
"""

WEATHER = ["power_t2m_prev_season_mean", "power_tmin_prev_season_mean", "power_tmax_prev_season_mean",
           "power_cold_days_prev_season", "power_hot_days_prev_season", "power_precip_prev_season_sum",
           "power_dry_days_prev_season", "power_solar_prev_season",
           "imerg_precip_prev_season_sum", "imerg_dry_spell_prev_season"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True, help="folder holding year=YYYY/part.parquet")
    ap.add_argument("--out", required=True, help="output CSV")
    args = ap.parse_args()

    weather = ",\n       ".join(
        f"sum(area_acres * {c}) / sum(CASE WHEN {c} IS NOT NULL THEN area_acres END) AS {c}" for c in WEATHER)
    con = duckdb.connect()
    con.execute(SQL.format(dataset=args.dataset, weather=weather, hay=HAY_PASTURE, nonag=NON_AG))
    # the label must be one value per county x year x crop, or this whole panel is wrong
    assert con.execute("SELECT max(n_distinct_yield) FROM target").fetchone()[0] == 1
    panel = con.execute("""
        SELECT t.* EXCLUDE (n_distinct_yield), c.* EXCLUDE (county_fips, year)
        FROM target t JOIN county c USING (county_fips, year)
        ORDER BY crop, county_fips, year""").df()
    panel.to_csv(args.out, index=False)
    print(f"{len(panel)} rows, {panel.county_fips.nunique()} counties, years {panel.year.min()}-{panel.year.max()}")
    print(panel.groupby("crop").size().to_string())


if __name__ == "__main__":
    main()
