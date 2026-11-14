# `2025.zip`: daily field panel for the 2025 season

Analysis of `2025.zip` (259 MB; 288 MB unpacked), run on 2 Nov 2026. Every number below comes from a query on the full file, from a live NASA POWER API check made the same day, or from the USDM county statistics cached for [`field_dataset.md`](field_dataset.md) section 9. The archive was unpacked outside the repository and should stay out of git.

**In one paragraph.** It is the **daily companion of `field_dataset` for one season**. There is one row per CSB field and day, for 1 April–31 October 2025: 628,672 fields × 214 days = 134,535,808 rows, in 99 county files. The fields and their static columns are the same as in `field_dataset`, and both crops' yields sit in wide columns. On top of that it adds:

- 12 daily NASA POWER variables;
- 5 daily IMERG variables;
- a daily U.S. Drought Monitor class.

**Verdict.**

| Part | Status |
|---|---|
| POWER | Matches the API exactly |
| Summer 2025 aggregates | Equal the backfill in `field_dataset.md` section 9, so this file supplies the inputs for 2026 predictions that `field_dataset` lacks |
| IMERG | October is missing |
| Drought | Needs decoding: a field outside drought keeps its last drought class |
| Neighbour shares | Still empty |
| Weather storage | Every value is repeated for every field in its cell |

## 1. Files and rows

- **Layout:** `2025/{county_fips}.parquet`, one file per Iowa county (`19001` … `19197`), 1.6–5.1 MB each. There is no key-value metadata, so the IMERG product and version are not recorded.
- **Rows:** 628,672 fields × 214 days. Every field has all 214 days, and there are no duplicate field-days.
- **Fields:** the same 628,672 `CSBID` as `field_dataset`. That table keeps only the 484,923 fields in counties with a 2025 yield; this file also keeps the other 143,749.
- **Static columns are constant over days** for every field.

## 2. Columns

| Column | Null % of rows | Meaning (verified where marked) |
|---|---|---|
| `CSBID`, `county_fips`, `county_name`, `centroid_*`, `area_acres`, `min_lon` … `max_lat`, `power_cell_id`, `imerg_cell_id` | 0 | As in `field_dataset`: **identical values** on all 484,923 shared fields (verified). The bounds are still synthetic squares |
| `date`, `year`, `doy` | 0 | 2025-04-01 … 2025-10-31; `doy` 91–304, consistent with `date` |
| `yield_bu_acre_corn`, `yield_bu_acre_soybeans` | 22.87, 32.00 | NASS county yield 2025, the same values as `field_dataset`. Published for 79 counties (corn) and 73 (soybeans); null elsewhere |
| `yield_lag1_…`, `yield_mean_prev3_…`, `yield_prev3_count_…` (both crops) | 0 | As in `field_dataset`. The soybean lags are also kept for 57,405 fields whose 2025 soybean yield is missing; `field_dataset` dropped those rows |
| `field_cdl_prev1/2`, `field_corn_prev1`, `field_soy_prev1`, `field_corn_to_soy_prev2`, `field_soy_to_corn_prev2` | 0 | Identical to `field_dataset` 2025. `field_prev1_is_candidate_crop` is gone (there is no candidate crop in a wide table) |
| `corn_share_prev1`, `soy_share_prev1`, `corn_to_soy_share_prev2`, `soy_to_corn_share_prev2` | **100** | Still never filled |
| `power_T2M`, `power_T2M_MIN`, `power_T2M_MAX`, `power_T2MDEW` | 0 | Daily mean, min, max and dew point, °C. Ranges: T2M −0.7…33.2; min −6.0…26.8; max 4.1…40.1; dew point −10.1…25.7 (verified) |
| `power_RH2M`, `power_QV2M` | 0 | Relative humidity, % (36–96); specific humidity, g/kg (1.8–21.5) (verified) |
| `power_PRECTOTCORR` | 0 | Precipitation, mm/day; 0–94.7, mean 3.33. **No ×24 inflation** (verified) |
| `power_WS2M`, `power_WS10M`, `power_WD10M` | 0 | Wind speed at 2 m and 10 m, m/s; direction at 10 m, degrees (verified) |
| `power_PS` | 0 | Surface pressure, kPa; 94.2–100.4 (verified) |
| `power_ALLSKY_SFC_SW_DWN` | 0 | Incoming solar, MJ/m²/day; 1.8–30.5, mean 18.5 (verified) |
| `imerg_precipitation` | 14.49 | IMERG daily precipitation, mm/day; 0–90.1. **Null on every day of October** |
| `imerg_randomError` | 14.49 | Rises with precipitation (r = 0.97). 2.76 on dry days, median 3.5, max 20,140. That is not on a mm/day scale, so **check the units** in the GES DISC documentation before use |
| `imerg_probabilityLiquidPrecipitation` | 14.49 | %, mean 99.8 |
| `imerg_precipitation_cnt` | 14.49 | Always 48: the number of half-hour slots per day |
| `imerg_precipitation_cnt_cond` | 14.49 | Presumably the number of half-hours with precipitation (0–48, mean 4.75): a rain-duration proxy |
| `drought_dm` | 0 | **Only 0 or 1** (D0 or D1); see section 4 before using it |
| `drought_valid_date` | 0 | Date of the **last USDM map whose polygon covered the field**, used from valid date + 2 days (the release day). Ranges back to 2024-10-29 |
| `drought_map_age_days` | 0 | `date − drought_valid_date`, 2–199 days (verified) |

The variable set matches the GPM IMERG daily product (V07 names). The Early, Late and Final runs share the same names, and the file does not say which one this is.

## 3. How it was checked

**POWER against the live API.** Three cells were requested from the AG community, daily, 2025-04-01 … 2025-10-31: `+42.0_-93.750` (central), `+43.0_-95.625` (north-west) and `+40.5_-91.250` (south-east).

- All 12 variables match the file **exactly** (max abs diff 0) on all 214 days.
- Sources: MERRA2 and SYN1DEG. The GEOS-IT period starts on 1 Oct 2026, so the ×24 precipitation bug cannot apply to 2025.

**Weather is per cell, not per field.**

| Source | Distinct cell-days | Rows per cell-day | Values within a cell-day |
|---|---|---|---|
| POWER | 14,552 (68 cells × 214 days) | 9,245 on average | One distinct combination |
| IMERG | 359,734 (1,681 cells × 214 days) | 374 on average | One distinct combination |

**Summer 2025 equals the backfill.** May–September 2025 aggregates were recomputed with the `field_dataset` definitions (section 3 there) for all 68 cells. They equal the `power_seasons.csv` written by `02_backfill_power.py`: day counts are identical, and the rest differ by at most 5e-13.

**Static columns against `field_dataset` 2025:** 0 mismatches over 484,923 fields and 20 columns. The only difference is the soybean lags noted above.

**Drought against the USDM county statistics** (categorical percent area, weekly) for 3,069 county × map-days. Each comparison uses the first day a map is in use (valid date + 2).

| Comparison | r | Mean abs diff |
|---|---|---|
| Field area holding the current map vs USDM D0+ area | 0.941 | 0.032 |
| Current-map D1 area vs USDM D1+ | 0.964 | 0.007 |

On 1,371 county-days where USDM shows no drought at all, the file still flags D1 on 0.1% of the field area on average (max 4.1%).

**IMERG against POWER** (April–September). Each IMERG cell is compared with the POWER cell of its fields. 532 IMERG cells have fields in two POWER cells; for those, one of the two is used.

| Month | Apr | May | Jun | Jul | Aug | Sep | Apr–Sep |
|---|---|---|---|---|---|---|---|
| IMERG, mm/day | 3.51 | 3.00 | 5.01 | 6.81 | 2.95 | 1.76 | |
| POWER, mm/day | 2.91 | 2.03 | 5.89 | 6.96 | 2.81 | 1.51 | |
| IMERG / POWER | 1.21 | 1.48 | 0.85 | 0.98 | 1.05 | 1.17 | **1.04** |

- **Days with ≥ 1 mm:** IMERG 32.3%, POWER 37.5%. POWER drizzles more, as the US pilot in `research/weather_climate.md` §6.3 found.
- **Daily correlation:** IMERG cell vs its POWER cell r = 0.65.
- **IMERG adds spatial detail.** Within one POWER cell, IMERG May–September sums vary by a median of 54 mm around a median of 590 mm.

## 4. Problems and traps

1. **Drought: a stale class means "no drought".**
   - **How it is coded:** each field carries the class of the last map whose polygon covered it. USDM draws polygons only for D0+, so a field that leaves drought keeps its old class, and `drought_dm = 0` then reads as "abnormally dry".
   - **How much it affects:** 60.9% of rows carry a map older than the current one (age > 8 days). These fields are not in drought. Of those stale rows, 0.8% are flagged D1 and the rest D0.
   - **The fix:** `class = drought_dm if drought_map_age_days <= 8 else −1`. With it, 60.9% of rows decode as no drought, 32.0% as D0 and 7.2% as D1.
   - **Missing maps are not missing.** The maps of 12, 19 and 26 August 2025 never appear because Iowa had no D0+ at all on those dates.
   - **One map is really missing: 10 June 2025.** No row carries it, so on 12–18 June every field decodes as no drought. USDM had 521,841 of the 628,672 fields in drought that week (439,648 D0, 82,193 D1). Found when the drought was rebuilt from the weekly USDM shapefiles, which reproduce the other 31 maps of the season exactly ([`field_daily_2025_followup.md`](field_daily_2025_followup.md) section 3).
   - **No D2+ is expected:** Iowa had no D2+ from 25 March 2025.
2. **IMERG October is missing:** 31 days, all cells, 14.49% of rows.
   - IMERG Final has a latency of about 3.5 months, so October 2025 should be available by now.
   - The product and version are not recorded in the file.
3. **`imerg_randomError` units are unclear** (see the column table). Do not use it as mm/day.
4. **The four neighbour-share columns are still empty.** `01_county_panel.py` computes them (`field_dataset.md` section 8).
5. **Huge redundancy.**
   - POWER holds 14,552 cell-days and IMERG 359,734 cell-days, each repeated for every field in the cell.
   - Normalised, the same content needs about 36 MB of Parquet: fields 32 MB, IMERG 3.2 MB, POWER 0.5 MB. The unpacked file is 288 MB, and the drought block needs a table of its own.
6. **The window is 1 April–31 October.**
   - Winter is missing.
   - A last spring frost before 1 April is invisible.
   - The first fall frost is censored: only 34 of 68 cells had one by 31 October.
   - Frost-window work (M3) needs at least March and November; RothC needs the whole year.
7. **One season only.** Nothing that depends on the weather of the year can be trained on it. It is a test season and a template for a multi-year daily panel.
8. **"Field" weather is cell weather.**
   - POWER is ~50 km.
   - IMERG is 0.1°.
   - The field bounds are synthetic squares.
9. **Different shape from `field_dataset`.** Yields are wide here (one column per crop) and long there (one row per candidate crop). Join on `CSBID`, not on `CSBID` + crop.
10. **No ET0.** All FAO-56 Penman–Monteith inputs are present, so it can be computed: Tmax and Tmin, dew point or RH, WS2M, solar and pressure.

## 5. The 2025 season in this file

Statewide means over the 68 POWER cells; precipitation and day counts per cell:

| Month | Tmax, °C | Tmin, °C | RH, % | Precipitation, mm | Days ≥ 32 °C | Frost days (Tmin ≤ 0) | Solar, MJ/m²/day |
|---|---|---|---|---|---|---|---|
| Apr | 16.7 | 3.8 | 68.9 | 85.4 | 0.00 | 6.46 | 17.5 |
| May | 22.4 | 9.4 | 66.5 | 63.5 | 0.18 | 0 | 21.3 |
| Jun | 28.1 | 17.4 | 75.2 | 173.7 | 4.15 | 0 | 21.3 |
| Jul | 29.0 | 19.8 | 80.3 | 209.7 | 3.50 | 0 | 22.3 |
| Aug | 27.0 | 17.0 | 77.6 | 87.6 | 1.35 | 0 | 19.6 |
| Sep | 26.2 | 14.1 | 70.4 | 45.5 | 2.47 | 0 | 16.2 |
| Oct | 20.0 | 8.4 | 67.8 | 47.7 | 0.26 | 1.12 | 11.4 |

- **Rain:** a wet June–July, then a dry August–September.
- **Drought:** USDM D0+ covered 92 counties in late April. It had vanished by 12 August and was back in 81 counties by 28 October.
- **Frost:** the last spring frost fell on 8 April in the median cell (latest 26 April). The first fall frost came on 23 October, in half the cells.
- **Yields:** a very good year.

  | Crop | County mean | Rank 1990–2025 | Ratio to the previous 3-year mean |
  |---|---|---|---|
  | Corn | 209.0 bu/ac | 2nd highest | 1.04 |
  | Soybeans | 63.3 bu/ac | Highest | 1.08 |

## 6. What it is useful for

| Use (Sivozmina) | Columns | Verdict |
|---|---|---|
| **m11: inputs for 2026 predictions** | `power_*` May–Sep 2025 | **Ready.** Aggregates equal the `field_dataset` definitions exactly, which closes `field_dataset.md` section 6, item 5 for weather. The April 2026 drought map still has to be added |
| **M3 windows** (frost, heat, sowing and field work, rain) | Daily T2M_MIN/MAX, PRECTOTCORR, RH2M, WS2M; IMERG | **Usable for 2025** as a worked season. The window is too short for frost and only one year long |
| **m6, m7 water** | All POWER variables | **Usable.** Compute FAO-56 ET0 and a daily water balance with IMERG or POWER rain |
| m11 critical-period features (`field_dataset.md` section 11) | Daily T and rain for July–August | The format is right, but training needs the same panel for 1991–2024 |
| In-season drought tracking | `drought_*` | Usable **after decoding** (section 4, item 1) |
| M2 confounders | Daily weather, drought | Cell level only, as in `field_dataset` |
| Out-of-sample test season | Yields + weather | A good, wet-then-dry year with near-record yields: a hard case for a trend model that would under-predict |

An enriched version with SMAP L4 soil moisture, `field_daily_2025_enriched.zip`, is analysed in [`field_daily_2025_enriched.md`](field_daily_2025_enriched.md). Its shared columns are identical to this file, so everything below still applies to it.

## 7. Recommendations, in order

1. **Normalise before sharing.**
   - Use one fields table, a POWER cell-day table, an IMERG cell-day table, and drought per field-week or per county-week.
   - That is ~36 MB instead of 288 MB, and nothing is lost.
2. **Fix the drought coding.** Write −1 for "no drought" when the field is outside every polygon of the current map, or store the class per county from the USDM county statistics as `03_backfill_context.py` does. Done for 2018–2025, including the missing 10 June map: `07_usdm_field_drought.py` writes the class of every field for every weekly map.
3. **Re-download IMERG for October**, and write the product (Early, Late or Final) and version into the Parquet metadata.
4. **Widen the window** to the full year, or at least March–November.
5. **Build the same daily panel for 1991–2024.**
   - POWER needs one request per cell; the `02_backfill_power.py` cache already holds 5 of the 12 variables back to 1989.
   - IMERG can go back to June 2000.
   - This is what the critical-period yield features need.
6. **Add an ET0 column** (FAO-56 from the POWER inputs). Or take gridMET ET0 × ~0.92 for Iowa (`research/weather_climate.md`).
7. **Fill or drop the four share columns.**

## 8. Reading it

```python
import duckdb
con = duckdb.connect()
con.execute("CREATE VIEW d AS SELECT * FROM read_parquet('2025/*.parquet')")

# weather once per cell-day, not once per field
power = con.execute("""
SELECT power_cell_id, date, any_value(COLUMNS('^power_[A-Z]'))
FROM d GROUP BY ALL ORDER BY ALL""").df()                       # 14,552 rows
imerg = con.execute("""
SELECT imerg_cell_id, date, any_value(COLUMNS(lambda c: c LIKE 'imerg_%' AND c <> 'imerg_cell_id'))
FROM d WHERE month(date) < 10 GROUP BY ALL""").df()             # 307,623 rows (October is empty)

# drought: a map older than the current one means the field is outside every polygon
drought = con.execute("""
SELECT CSBID, date,
       CASE WHEN drought_map_age_days <= 8 THEN drought_dm ELSE -1 END AS usdm_class  -- -1 = no drought
FROM d""").df()
```
