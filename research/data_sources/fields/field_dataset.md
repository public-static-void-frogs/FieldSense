# `field_dataset`: what it holds and what it is good for

Analysis of `field_dataset.7z` (675 MB; ≈1.0 GB unpacked), run on 1 Nov 2026. Every number below comes from a query on the full dataset or from a live NASA POWER API check made the same day. The archive was unpacked outside the repository and should stay out of git.

**In one paragraph.** It is a training table for a county-yield model in **Iowa only**. The table has one row per CSB field, year and candidate crop (CORN or SOYBEANS), 1990–2025: 43,609,473 rows over 628,672 fields. The target `yield_bu_acre` is the **NASS county yield**, so every field in a county carries the same label. The features are:

- the field's crop in the two previous years (from CSB);
- NASA POWER and IMERG aggregates for **May–September of the previous year**;
- one U.S. Drought Monitor snapshot from **early April** of the target year.

**Coverage gaps.** Features exist only for 2019–2025. All rows from 1990–2017 (80% of the table) carry the target and its lags but no features, and four planned "neighbour share" columns are empty everywhere.

**Follow-up (sections 8–11).**

- The neighbour shares were rebuilt (section 8).
- The features were backfilled to 1991 and checked against the dataset (section 9).
- A county-yield baseline was run (section 10). **No pre-season input beats a per-county yield trend.** The delivered previous-summer weather makes predictions worse.


## 1. Files and rows

Hive-partitioned Parquet written by DuckDB v2.0.0: `field_dataset/year=YYYY/part.parquet`, one file per year.

| Years | Rows per year | Note |
|---|---|---|
| 1990–2014, 2016 | 1,257,344 (= 628,672 fields × 2 crops) | Target and yield lags only |
| 2015, 2017 | 1,220,112; 1,206,837 | Some county corn yields missing, so those fields have a soybean row only |
| 2018 | 1,195,277 | Field history t−1 and weather still missing |
| 2019–2025 | 878,629–1,230,891 | All features present (except the empty neighbour shares) |
| 2026 | 0 | Empty file, schema only |

- **Fields:** 628,672 distinct `CSBID`, all from the CSB 2025 edition (`19` + `1825` + sequence), state 19 (Iowa), all 99 counties.
- **Bounding box:** −96.64…−90.16° lon, 40.38…43.50° lat.
- **The same field set is repeated for every year back to 1990,** although CSB polygons exist only for 2018–2025. Before 2018 a field row is just a copy of its county's yield.
- **Two schema versions:** `drought_dm` is `int8` in 1990–2017 and in 2026, and `double` in 2018–2025. Read with `union_by_name=true` and cast it.

## 2. Columns

Null shares are per era of rows.

| Column | Type | Null % 1990–2017 / 2018–2025 | Meaning (verified where marked) |
|---|---|---|---|
| `CSBID` | string | 0 / 0 | CSB field ID, 2025 edition |
| `county_fips`, `county_name` | string | 0 / 0 | County (99 Iowa counties) |
| `centroid_lon`, `centroid_lat` | double | 0 / 0 | Field centroid, WGS84 |
| `area_acres` | double | 0 / 0 | Field area; median 15.2 ac, 10–90% 3.7–107 ac |
| `min_lon` … `max_lat` | double | 0 / 0 | **Estimated square** around the centroid with the field's area (median ≈ 250 m side), not the real outline; see `NASS_CSB_with_bounds.md` |
| `power_cell_id` | string | 0 / 0 | POWER cell centre, e.g. `+42.0_-93.750` (0.5° × 0.625°). 68 cells; median 9,988 fields per cell |
| `imerg_cell_id` | string | 0 / 0 | IMERG cell centre, e.g. `+42.55_-91.15` (0.1°). 1,681 cells; median 370 fields per cell |
| `crop` | string | 0 / 0 | Candidate crop of the row: `CORN` or `SOYBEANS` |
| `year` | int | 0 / 0 | Target year t |
| `yield_bu_acre` | double | 0 / 0 | **Target. NASS county yield** for this crop in year t: exactly one value per county × year × crop (6,887 such groups) |
| `yield_lag1_bu_acre` | double | 3.6* / 0 | County yield in t−1 (verified: equals the previous year's target) |
| `yield_mean_prev3_bu_acre` | double | 3.6* / 0 | Mean county yield over t−3…t−1 |
| `baseline_prev3_mean_bu_acre` | double | 3.6* / 0 | **Duplicate:** identical to `yield_mean_prev3_bu_acre` in 100% of rows |
| `yield_prev3_count` | int8 | 0 / 0 | Number of years behind the 3-year mean (0–3) |
| `field_cdl_prev1`, `field_cdl_prev2` | int16 | 100 / 14.1, 26.7 | Field's CDL class in t−1 and t−2, from CSB. Missing where CSB has no year (t−1 < 2018) |
| `field_corn_prev1`, `field_soy_prev1` | int8 | 100 / 14.1 | 1 if t−1 was corn or soybeans |
| `field_corn_to_soy_prev2`, `field_soy_to_corn_prev2` | int8 | 100 / 26.7 | 1 if t−2 → t−1 was corn → soy (or soy → corn) |
| `field_prev1_is_candidate_crop` | int8 | 100 / 14.1 | 1 if the t−1 crop equals the row's candidate crop, i.e. **continuous cropping** (verified on 2024 rows) |
| `corn_share_prev1`, `soy_share_prev1`, `corn_to_soy_share_prev2`, `soy_to_corn_share_prev2` | double | **100 / 100** | Planned area shares (presumably county or neighbourhood). **Never filled** |
| `power_t2m_prev_season_mean`, `power_tmin_…`, `power_tmax_…` | double | 100 / 14.1 | Mean daily T2M, T2M_MIN, T2M_MAX over **1 May–30 Sep of t−1**, °C (verified, section 3) |
| `power_hot_days_prev_season` | int64 | 100 / 14.1 | Days with T2M_MAX **≥ 32 °C** in that window (verified) |
| `power_cold_days_prev_season` | int64 | 100 / 14.1 | Days with T2M_MIN ≤ 0 °C (or ≤ −2 °C; both give 0 in summer, so the threshold cannot be told apart) |
| `power_precip_prev_season_sum` | double | 100 / 14.1 | Sum of PRECTOTCORR, mm (verified) |
| `power_dry_days_prev_season` | int64 | 100 / 14.1 | Days with PRECTOTCORR **< 1 mm** (verified) |
| `power_solar_prev_season` | double | 100 / 14.1 | Sum of ALLSKY_SFC_SW_DWN, **MJ/m² per season** (≈ 3,000–3,200; verified) |
| `imerg_precip_prev_season_sum` | double | 100 / 14.1 | IMERG precipitation sum, presumably the same window. Not verified against GES DISC; IMERG/POWER ratio by year 1.01–1.17 |
| `imerg_dry_spell_prev_season` | int64 | 100 / 14.1 | Presumably the longest dry spell in days (10–17 on average); definition not verified |
| `drought_dm` | int8/double | 100 / 59.7 | USDM class 0–4 (D0–D4) at the field centroid. **Null means "not in drought"**, not missing: USDM only draws polygons for D0+ |
| `drought_valid_date` | date | 100 / 0 | One map per year, the **second week of April of year t** (2018-04-10 … 2025-04-08) |

\* Null only in 1990 (no t−1 inside the table).

## 3. How the weather features were checked

For cell `+42.0_-93.750` (central Iowa), daily POWER AG data were pulled from the API and aggregated:

- **The 2023 rows match POWER over 1 May–30 Sep 2022 exactly:** T2M 21.83 °C, T2M_MIN 15.66, T2M_MAX 28.20, precipitation 401.1 mm, 101 dry days, 35 hot days, solar 3,204.27 MJ/m².
- **The 2024 rows match May–Sep 2023 the same way:** 333.3 mm, 109 dry days, 33 hot days, 3,150.63 MJ/m².
- **No other window matched:** April–September, May–October or June–August of either year.

So the source is NASA POWER (MERRA-2 era, no GEOS-IT days, so the ×24 precipitation bug does not apply), and every weather feature of year t describes **the previous summer**. Weather values are identical for every field in a POWER cell and year. On average ~4 counties share one POWER cell-year.

## 4. Problems and traps

1. **The label is county-level, so the real sample is small.**
   - The 43.6 M rows hold 6,887 distinct targets (county × year × crop).
   - Only **603 corn and 564 soybean targets** have features (2019–2025).
   - Field-level features cannot explain differences in a label that is constant across the county. A model trained on field rows mostly learns county composition.
   - A random row split puts the same county-year on both sides and leaks the answer.
2. **1990–2017 rows are featureless.** The weather inputs exist for those years: POWER from 1981, IMERG from June 2000, USDM from 2000. Filling them in would add the 2012 drought and the 1993 flood years (1993 county corn yields fell to 41–106 bu/ac).
3. **The four neighbour-share columns are empty.**
   - They describe what the surrounding area grew. They are direct inputs to the county-yield model (m11 in the proposal lists "CSB crop and transition shares").
   - M2 itself compares neighbours through their own field histories (the `field_*` columns). There the shares serve only as landscape context: pest pressure, local practice.
   - They can be computed from this table for 2019–2025 (area-weighted by county). For earlier years, NASS county acreage gives the corn and soy shares, but not the transitions.
4. **Missing county yields drop rows.** NASS withheld or did not publish some county yields, so some field-years have only one candidate row. Examples: in 2021 the soybean row is missing for 83,184 fields; in 2024 the soybean row for 76,247 and the corn row for 38,494.
5. **Non-crop fields get crop targets.** Among 2019–2025 field-years, t−1 was:

   | CDL class (t−1) | Field-years |
   |---|---|
   | 176 grassland/pasture | 581,522 |
   | 36 alfalfa | 171,442 |
   | 37 other hay | 38,950 |
   | 121 developed | 29,560 |
   | 141 forest | 11,667 |
   | 195 wetland | 9,789 |

   They still carry corn and soybean county yields as targets. Filter them, or keep the class as a feature.
6. **Drought coding.**
   - Null means "no drought". Encode it as −1 (or 0 = D0 means abnormally dry, so keep a separate "none").
   - The column type differs between partitions.
   - It is a single pre-season snapshot, not summer drought.
7. **Duplicate column:** `baseline_prev3_mean_bu_acre` = `yield_mean_prev3_bu_acre`.
8. **Weather is coarse and biased.**
   - 68 POWER cells for the whole state (~50 km). IMERG at 0.1° is the finer rain source.
   - The US pilot in `research/weather_climate.md` §6.3 found that POWER counts ~30% too many wet days, so `power_dry_days` is biased low.
   - The same pilot found POWER Tmin ~1 °C too warm at Iowa and Plains stations.
   - Hot-day counts at ≥ 32 °C are sensitive to Tmax errors: daily Tmax RMSE was 2.1 °C.
9. **Nothing to predict 2026 with.** The 2026 partition is empty, and the 2025 summer weather that would feed it is not in the table. The 2025 rows hold summer 2024.
10. **No field geometry.** The bounding boxes are synthetic squares, so HLS or ECOSTRESS per-field extraction cannot use them as field outlines.

## 5. What it is useful for

| Use | Columns | Verdict |
|---|---|---|
| **m11: expected county yield range** (Sivozmina §4.5) | Target, yield lags, POWER and IMERG season aggregates, drought snapshot | **Main use.** Build it at county-year level. With 2019–2025 only it is thin; backfilling to 1990 makes it workable |
| Yield trend and baseline | `yield_bu_acre` 1990–2025 by county, lags | Usable now: 36 years of county yields for 99 counties |
| **M2 treatments** (continuous crop T1, corn ↔ soy alternation) | `field_cdl_prev1/2`, `field_*_prev*` flags, `field_prev1_is_candidate_crop` | Usable, but only two years back. CSB itself has 2018–2025, so read the CSB sequence directly for T2/T3/T5 |
| **M2 outcomes** | None | Missing: no field-level outcome. The county yield works only as the Y4 county check |
| M2 confounders | `power_*`, `imerg_*`, `drought_dm`, `area_acres` | Partial: weather at cell level, no soil, no irrigation |
| M3 windows (frost, sowing, heat) | None | Not usable: seasonal sums, not daily series |
| m6, m7 water | None | Not usable: no humidity, wind or daily values |
| Neighbour context ("what the county grows") | `corn_share_prev1`, etc. | Planned but empty; easy to compute from CSB |

## 6. Recommendations, in order

1. **Validate by year.** Use leave-one-year-out (or blocked by year and county), never random rows. Or aggregate to one row per county × year × crop and weight by field count.
2. **Backfill features for 1990–2018.**
   - POWER May–Sep weather for the 68 cells (one API call per cell).
   - IMERG from 2000.
   - The April USDM snapshot from 2000.

   This multiplies the usable targets by about five and brings in the 2012 drought. Done for POWER, USDM and CDL; IMERG is still open. See section 9.
3. **Fill the neighbour shares** from CSB: the county or 10 km share of corn, soy and transitions in t−1 and t−2. Done at county level in section 8.
4. **Clean up.**
   - Unify the `drought_dm` type and encode "no drought".
   - Drop the duplicate baseline column.
   - Filter, or flag, fields whose t−1 class is pasture, hay, forest, wetland or developed.
5. **Add 2026 prediction rows** with summer-2025 weather and the April-2026 drought map. The summer-2025 weather is now in `2025.zip`, which matches the definitions exactly; see [`field_daily_2025.md`](field_daily_2025.md).
6. **For field-level questions, replace the label.** Use a field-scale yield proxy, such as SCYM in Earth Engine for US maize and soy, or HLS greenness as in M2 Y1. County yields stay as the check.
7. **Optionally swap the weather source** for Iowa: gridMET (4 km, includes ET0) matched station rain and frost far better than POWER in the US pilot.

## 7. Reading it

```python
import duckdb
con = duckdb.connect()
con.execute("""
CREATE VIEW fd AS
SELECT * EXCLUDE (drought_dm), CAST(drought_dm AS DOUBLE) AS drought_dm
FROM read_parquet('field_dataset/year=*/part.parquet', union_by_name = true)
""")
# one row per county x year x crop (the real sample)
county = con.execute("""
SELECT county_fips, year, crop,
       any_value(yield_bu_acre) AS yield_bu_acre,
       any_value(yield_lag1_bu_acre) AS lag1,
       any_value(power_hot_days_prev_season) AS hot_days_prev_summer,   -- one POWER cell per county is an approximation
       avg(coalesce(drought_dm, -1)) AS drought_april,
       count(*) AS n_fields
FROM fd
WHERE year >= 2019
GROUP BY ALL
""").df()
```

## 8. County panel and neighbour shares

Sections 8–11 come from the scripts in [`ml/field-prediction-model/analysis/`](../../../ml/field-prediction-model/analysis/README.md), run on 1–2 Nov 2026. `01_county_panel.py` collapses the table to one row per county × year × crop:

- **6,887 rows:** corn 3,460, soybeans 3,427; 99 counties; 1990–2025.
- **Field inputs become area-weighted county means.** Weather is weighted too, because a county can span several POWER cells.
- **The four empty share columns are rebuilt** from the `field_*` history flags, and three shares are added: continuous corn, hay/pasture and non-agricultural land in t−1.

The core of the share SQL (`f` holds one row per field-year, because the table repeats each field for both candidate crops):

```sql
SELECT county_fips, year,
  sum(area_acres * field_corn_prev1)
    / sum(CASE WHEN field_corn_prev1 IS NOT NULL THEN area_acres END)          AS corn_share_prev1,
  sum(area_acres * field_soy_prev1)
    / sum(CASE WHEN field_soy_prev1 IS NOT NULL THEN area_acres END)           AS soy_share_prev1,
  sum(area_acres * field_corn_to_soy_prev2)
    / sum(CASE WHEN field_corn_to_soy_prev2 IS NOT NULL THEN area_acres END)   AS corn_to_soy_share_prev2,
  sum(area_acres * field_soy_to_corn_prev2)
    / sum(CASE WHEN field_soy_to_corn_prev2 IS NOT NULL THEN area_acres END)   AS soy_to_corn_share_prev2,
  sum(area_acres * (field_cdl_prev1 = 1 AND field_cdl_prev2 = 1)::INT)
    / sum(CASE WHEN field_cdl_prev1 IS NOT NULL AND field_cdl_prev2 IS NOT NULL
               THEN area_acres END)                                            AS corn_corn_share_prev2,
  sum(area_acres * (field_cdl_prev1 IN (36, 37, 62, 176))::INT)
    / sum(CASE WHEN field_cdl_prev1 IS NOT NULL THEN area_acres END)           AS hay_pasture_share_prev1
FROM f
GROUP BY county_fips, year;
```

The denominator is every CSB field in the county with a known t−1 class, pasture and hay included. So corn + soy comes to about 0.93, not 1.

**County means by target year** (counties with a published corn yield):

| Year | Counties | Corn t−1 | Soy t−1 | Corn → soy | Soy → corn | Corn–corn | Hay/pasture t−1 | Non-ag t−1 |
|---|---|---|---|---|---|---|---|---|
| 2019 | 88 | 0.533 | 0.405 | – | – | – | 0.054 | 0.005 |
| 2020 | 95 | 0.532 | 0.370 | 0.354 | 0.376 | 0.148 | 0.072 | 0.003 |
| 2021 | 84 | 0.546 | 0.382 | 0.362 | 0.359 | 0.172 | 0.064 | 0.003 |
| 2022 | 97 | 0.513 | 0.410 | 0.395 | 0.367 | 0.139 | 0.071 | 0.002 |
| 2023 | 87 | 0.516 | 0.409 | 0.394 | 0.393 | 0.118 | 0.070 | 0.002 |
| 2024 | 73 | 0.528 | 0.396 | 0.385 | 0.392 | 0.130 | 0.070 | 0.002 |
| 2025 | 79 | 0.520 | 0.406 | 0.391 | 0.384 | 0.127 | 0.066 | 0.002 |

Transitions need t−2, so they start in 2020: CSB begins in 2018. The 2018 rows have no shares, because t−1 = 2017 is outside CSB.

**The shares differ more between counties than between years.** Across the 73 counties of 2024:

| Share | Range | Median |
|---|---|---|
| Corn t−1 | 0.29–0.70 | 0.53 |
| Continuous corn | 0.01–0.45 | 0.11 |
| Hay/pasture t−1 | 0.008–0.455 | 0.04 |

The extremes:

- **Decatur (19053, south):** corn 0.29, hay/pasture 0.46, continuous corn 0.01.
- **Delaware (19055, north-east):** corn 0.70, continuous corn 0.42.
- **Dubuque (19061):** continuous corn 0.45.

**April drought from the dataset,** mean over county rows:

| Year | Area-weighted class (−1 = none) | D1+ area share |
|---|---|---|
| 2019 | −1.00 | 0.00 |
| 2020 | −1.00 | 0.00 |
| 2021 | −0.36 | 0.13 |
| 2022 | −0.13 | 0.24 |
| 2023 | 0.11 | 0.31 |
| 2024 | 0.94 | 0.66 |
| 2025 | 0.02 | 0.25 |

## 9. Backfill to 1990

`02_backfill_power.py` and `03_backfill_context.py` refill the missing years from keyless public services. Each refilled source was checked against the years where the dataset already has values.

| Feature group | Source | Target years filled | Check against the dataset |
|---|---|---|---|
| Previous-summer weather, 8 POWER features | POWER daily API, community AG; one request per cell for 1989-01-01 … 2025-09-30; 68 cells → 2,516 cell-seasons (1989–2025) | 1990–2025 | 469 cell-seasons present in both: day counts identical; temperatures within 3e-14 °C; precipitation within 8e-13 mm; solar within 3e-12 MJ/m². **Exact.** The script stops if this check fails |
| April drought | USDM county statistics API, categorical percent area, first map on or after 7 April | 2000–2025: 2,574 county-years | Map dates equal `drought_valid_date` for 2018–2025. County class vs the dataset's area-weighted centroid class: r = 1.000, max abs diff 0.16 class. D1+ share r = 1.000 |
| Crop mix t−1 | CropScape CDL county statistics | CDL 2000–2024 → targets 2001–2025 | corn / (corn + soy) vs the CSB-based value: r = 0.998, mean diff 0.000, n = 603 county-years |
| Transition shares | Not backfilled | 2020–2025 only | Would need a per-year CDL raster overlay |
| IMERG | Not backfilled | 2019–2025 only | Needs an Earthdata login; all models below run without it |

**Usable targets grow almost sixfold.**

| Crop | Dataset features (2019–2025) | Lag + previous-summer weather (1991–2025) | + April drought + CDL mix (2001–2025) |
|---|---|---|---|
| Corn | 603 | 3,361 | 2,365 |
| Soybeans | 564 | 3,328 | 2,332 |

1990 cannot be used: it has no t−1 yield inside the table.

**Things learned while backfilling:**

- **POWER precipitation.** Requests end on 2025-09-30, and the script asserts no GEOS-IT source in the response. A request that reaches GEOS-IT days returns precipitation ×24 (`research/weather_climate.md`).
- **Early CDL is a different product.**
  - County files hold at most 10–17 classes in 2000–2005, against 30–47 in 2024.
  - Three county files for 2000 are empty, and six counties have no corn/soy value for 2000.
  - Shares of "all agricultural land" therefore drift between years. Only corn / (corn + soy) compares across the whole period: its yearly mean stays within 0.52–0.62.
- **An April drought map misses summer droughts.** April D1+ share, mean over counties:

  | 2000 | 2003 | 2012 | 2013 | 2024 |
  |---|---|---|---|---|
  | 1.00 | 0.65 | 0.30 | 0.69 | 0.68 |

  2012 was the worst corn year since 2000: the county mean yield fell to 0.78 of the previous 3-year mean. That drought built up after planting, so the April snapshot sees less of it than of 2013 or 2024. The worst years of the whole period:

  | Crop | Worst year | Second worst |
  |---|---|---|
  | Corn | 1993: 0.60 | 2012: 0.78 |
  | Soybeans | 2003: 0.72 | 1993: 0.75 |

## 10. Baseline results: what each feature group adds

`04_m11_baseline.py` predicts the county yield of year t as **county trend + model(residual)**:

- **Trend:** a per-county linear fit on the training years only.
- **Model:** ridge (`alpha=1`, standardised features) or gradient boosting (scikit-learn `HistGradientBoostingRegressor`, fixed settings, no tuning).
- **Validation is by year:**
  - **Leave-one-year-out (LOYO):** the trend may use later years.
  - **Forward chaining:** train on years before t only. This is the honest number for a planner.
- **Reference:** the 3-year mean (`yield_mean_prev3`).
- Full tables are in `results.csv` and `per_year_rmse.csv`.

### E1: 1991–2025, previous-summer weather only

RMSE in bu/ac; "ridge / boosting" where two models ran. Corn n = 3,361 (LOYO) and 2,965 (forward); soybeans 3,328 and 2,932.

| Inputs | Corn LOYO | Corn forward | Soy LOYO | Soy forward |
|---|---|---|---|---|
| 3-year mean (reference) | 23.5 | 21.1 | 6.75 | 6.43 |
| **Trend only** | **20.9** | **20.0** | **5.92** | **6.14** |
| + yield lags | 21.3 / 23.2 | 22.2 / 23.4 | 6.05 / 6.20 | 6.63 / 7.10 |
| + previous-summer weather | 23.7 / 25.0 | 24.8 / 25.2 | 6.30 / 6.45 | 7.62 / 6.77 |
| *Oracle: same-summer weather + lags* | *22.1 / 19.2* | *22.7 / 19.1* | *6.00 / 6.39* | *6.82 / 7.36* |

### E2: 2001–2025, with the April drought map and the CDL crop mix

Corn n = 2,371 (LOYO) and 1,975 (forward); soybeans 2,338 and 1,942.

| Inputs | Corn LOYO | Corn forward | Soy LOYO | Soy forward |
|---|---|---|---|---|
| 3-year mean (reference) | 22.3 | 22.7 | 6.82 | 6.33 |
| **Trend only** | **19.9** | 23.3 | **5.90** | **5.99** |
| + yield lags | 19.5 / 20.8 | 23.2 / 23.4 | 6.05 / 6.39 | 6.71 / 7.41 |
| + previous-summer weather | 21.6 / 23.4 | 24.9 / 26.3 | 6.47 / 6.50 | 8.75 / 7.48 |
| + April drought (USDM) | 21.9 / 23.4 | 25.2 / 25.9 | 6.27 / 6.32 | 9.08 / 7.43 |
| + CDL corn fraction t−1 | 22.0 / 23.7 | 25.1 / 25.9 | 6.29 / 6.64 | 8.08 / 7.26 |
| *Oracle: same-summer weather + lags* | *21.5 / 19.4* | *24.6 / 22.0* | *6.35 / 6.54* | *6.95 / 7.62* |

### E3: 2020–2025, the table as delivered

This run uses the dataset's own drought column and the CSB neighbour shares from section 8. LOYO only: six years are too few to train forward. Corn n = 514, soybeans n = 482.

| Inputs | Corn | Soy |
|---|---|---|
| 3-year mean (reference) | 20.1 | 5.91 |
| Trend only | 18.5 | **5.89** |
| + yield lags | 18.1 / 19.0 | 6.12 / 6.70 |
| + previous-summer weather | 18.7 / 19.6 | 6.57 / 6.59 |
| + April drought (dataset) | 18.8 / 19.2 | 6.68 / 6.62 |
| + CSB neighbour shares | **17.5** / 18.2 | 6.25 / 6.42 |

### What the tables say

1. **Nothing known before planting beats the county trend.**
   - The trend's RMSE is about 13% of the mean yield for corn (20.9 of 162.7 bu/ac) and about 12% for soybeans (5.9 of 49.1).
   - That beats the 3-year mean by 11–12% under LOYO and by 5% forward (E1).
   - Every pre-season feature group leaves the error **larger** than trend only, in both CV schemes and with both models. The exceptions are small and appear only under LOYO: corn lags with ridge in E2 (19.5 vs 19.9) and the E3 shares (item 5).
2. **Previous-summer weather, the core of the delivered table, has no measurable skill.**
   - Adding it raises the corn error from 21.3 to 23.7 bu/ac (E1 LOYO, ridge).
   - Forward chaining shows the same.
   - Yield anomalies hardly carry over from one year to the next, so last year's summer and last year's yield add noise.
3. **Even this summer's weather helps little in this form.** The oracle uses May–Sep weather of the target year itself.
   - **Corn with boosting:** best case 19.2 vs 20.9 for trend only, an 8% gain.
   - **Ridge:** no gain.
   - **Soybeans:** no gain.
   - **Why:** season means wash out the few critical weeks. Yield is decided by heat and water stress around July–August, and a May–Sep mean on a 50 km grid dilutes it. This is a ceiling for season-aggregate features, not for weather in general.
4. **Disaster years dominate the error,** and no input set fixes them. Per-year LOYO RMSE in bu/ac; trend and ridge only:

   | Inputs | Corn 1993 | Corn 2012 | Corn 2020 | Corn 2023 | Soy 1993 | Soy 2012 | Soy 2020 | Soy 2023 |
   |---|---|---|---|---|---|---|---|---|
   | Trend only | 55.4 | 48.7 | 26.5 | 16.9 | 11.8 | 8.6 | 4.7 | 5.2 |
   | + previous-summer weather | 60.7 | 50.8 | 29.4 | 16.1 | 13.5 | 10.1 | 7.1 | 5.3 |
   | Oracle, same summer (ridge) | 48.3 | 58.3 | 27.2 | 20.3 | 8.4 | 6.9 | 5.2 | 5.6 |

   The ridge oracle is worse than the trend for corn in 2012. A season mean does not capture a July flash drought.
5. **The CSB neighbour shares help corn in E3 (18.5 → 17.5), but the whole gain comes from 2020.**
   - **2020** (the year of the August derecho): 27.5 → 21.2.
   - **2021–2025:** 15.9–16.9 with shares against 14.6–17.0 for trend only, so better in two years and worse in three.
   - **Soybeans:** the shares do not beat the trend.
   - With six years, this is a hint to test, not a result.
6. **April drought and the CDL crop mix add nothing** for corn: each moves the error by 0.4 bu/ac or less, in either direction. For soybeans under LOYO, adding the drought map recovers part of what the weather columns cost (6.47 → 6.27), but it stays worse than the trend. Under forward chaining the gain is gone for ridge (8.75 → 9.08) and negligible for boosting (7.48 → 7.43).

### Permutation importance measures memorisation here

The gradient-boosting corn model on all E2 inputs, scored on its own training data:

| Rank | Feature | Importance |
|---|---|---|
| 1 | Previous-summer cold days | 0.30 |
| 2 | Previous-summer Tmin | 0.27 |
| 3 | Previous-summer Tmax | 0.22 |
| 4 | Previous-summer solar | 0.21 |
| 5 | Previous-summer precipitation | 0.20 |
| 6 | Previous-summer dry days | 0.19 |
| 7 | 3-year mean ratio | 0.16 |
| 8 | Previous-summer hot days | 0.13 |
| 9 | Lag-1 ratio | 0.13 |
| 10 | CDL corn fraction | 0.06 |
| 11 | April USDM class | 0.05 |
| 12 | Previous-summer T2M | 0.04 |
| 13 | April D1+ share | 0.004 |

The features the model leans on most are the ones that make held-out errors worse. Every county in a year shares nearly the same weather, so these columns act as a year identifier: the model memorises each year's anomaly. Read importance only on held-out years.

### Leakage demo

The same model and inputs on 300,000 sampled corn field rows (2019–2025): location, area, field history, three POWER features.

| Split | Test rows | RMSE, bu/ac |
|---|---|---|
| Random 80/20 field rows | 60,134 | **3.2** |
| Hold out 2024 | 35,900 | **16.4** |

The random split looks five times better than it is, because the same county-year label sits on both sides of the split.

### Limits of these runs

- Hyperparameters were fixed, not tuned (ridge α = 1; one boosting setting).
- The trend is linear per county.
- IMERG is not used.
- Iowa only: 35 weather years at most. With one state, the effective sample for learning weather effects is the number of **years**, not county-years.

## 11. Recommendations for whoever takes m11

1. **Ship m11 v0 as trend plus an empirical range.**
   - **Expected yield:** the county linear trend, falling back to the 3-year mean where the history is short.
   - **Range:** quantiles of the held-out residuals per crop. Compute them with forward chaining.
   - **Asymmetry:** disaster years miss by about 50 bu/ac for corn, so the lower tail of the range must be much longer than the upper one.
2. **Do not use the delivered previous-summer weather as a yield predictor.** If it stays in the table, document that it showed no skill (section 10, item 2).
3. **For an in-season update, build critical-period features from daily data:**
   - degree-days above ~29–30 °C;
   - July–August precipitation and VPD;
   - gridMET or Daymet (4 km) rather than POWER, which `research/weather_climate.md` §6.3 also favours.

   Test them with forward chaining. The oracle in section 10 shows that season means will not get there.
4. **Get more independent weather-years before fitting weather effects.**
   - Add the neighbouring Corn Belt states (Illinois, Indiana, Nebraska, Minnesota). NASS county yields and POWER/gridMET are available for all of them. `02` and `03` take their cells and counties from `field_dataset` today; pointing them at another county list is a small change.
   - Use strong shrinkage or a year random effect, because the year is the unit that varies.
5. **Validate by year and report per-year errors** for 1993, 2012 and 2020. Never split field rows at random: 3.2 vs 16.4 bu/ac.
6. **Keep the neighbour shares in the panel** (section 8; cheap to compute), but test them properly before relying on them:
   - extend the transitions back over the years with good CDL coverage, using a per-year CDL raster overlay;
   - rerun the E3 ablation over many more years.
7. **Keep m11 at county level.** The label cannot say anything about individual fields. M2's field-level questions need a field-scale outcome (section 6, item 6).
