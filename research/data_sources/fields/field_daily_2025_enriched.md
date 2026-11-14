# `field_daily_2025_enriched.zip`: the 2025 daily panel plus SMAP L4

Analysis of `field_daily_2025_enriched.zip` (1.24 GB; 1.28 GB unpacked), run on 4 Nov 2026. Every number below comes from a query on the full file, and the file was compared row by row with `2025.zip` ([`field_daily_2025.md`](field_daily_2025.md)).

**SMAP values were not compared with NSIDC source files** (no Earthdata login). The checks below are internal: grid placement, units, and physical consistency with the POWER, IMERG and USDM columns of the same file. The archive was unpacked outside the repository and should stay out of git.

**Later ground check.** The follow-up ([`field_daily_2025_followup.md`](field_daily_2025_followup.md), section 5) compared SMAP with the ISU Soil Moisture Network: 29 Iowa stations, daily 2025. Median correlation per station:
- 10 cm soil temperature vs `soil_temp_layer1`: **0.963**, bias −1.0 °C;
- 30–60 cm water content vs `sm_rootzone`: **0.73**, against 0.40 for POWER's MERRA-2 root-zone wetness at the same stations.
- Over the growing seasons of 2015–2025 (SMAP history from Crop-CASMA, follow-up section 10), the same stations give 0.68 for SMAP and 0.58 for MERRA-2.

**In one paragraph.** It is `2025.zip` with **16 SMAP Level-4 soil-moisture variables** added on the EASE-Grid 2.0 9 km grid (`smap_cell_id`), and without the four synthetic bound columns. The rows are the same: 628,672 CSB fields × 214 days (1 April–31 October 2025) = 134,535,808. The new variables are:

- soil moisture of three layers, with wetness and percentiles;
- surface and soil temperature;
- snow;
- evapotranspiration, runoff and baseflow;
- leaf area index.

**Verdict.**

| Part | Status |
|---|---|
| Shared columns | Identical to `2025.zip` on every row, so **its problems carry over unchanged**: drought coding, the missing 10 June 2025 drought map, empty IMERG October, empty neighbour shares |
| SMAP attachment | Correct: field centroids fall in their own 9 km cell |
| SMAP values | Behave physically: daily means, rain response, an ET/ET0 crop curve, low percentiles under drought |
| LAI | Looks like a prescribed seasonal curve, not 2025 crop growth |
| Size | 1.2 GB unpacked against 40 MB normalised (`05_normalise_daily.py`, lossless) |

## 1. Files and rows

- **Layout:** `field_daily_2025_enriched/2025/{county_fips}.parquet`, 99 county files, 1.28 GB, written by DuckDB v2.0.0. There is no metadata naming the SMAP product, its version or how it was aggregated to days.
- **Rows:** 628,672 fields × 214 days, no duplicate field-days. All 134,535,808 rows of `2025.zip` are present.
- **Added:** `smap_cell_id` and 16 `smap_*` variables (section 3).
- **Dropped:** `min_lon`, `min_lat`, `max_lon`, `max_lat`. They were estimated squares, not outlines, but code that reads them will break.

## 2. Diff against `2025.zip`

Joined on `CSBID` + `date`:

- 0 rows missing;
- **0 mismatching values in all 47 shared columns:** identifiers, yields, field history, the 12 POWER and 5 IMERG variables, and the drought block.

So everything in [`field_daily_2025.md`](field_daily_2025.md) section 4 still applies:

- **Drought:** a field outside drought keeps its last class. Decode with `drought_map_age_days <= 8`, otherwise −1.
- **IMERG:** empty for all of October; units of `imerg_randomError` are unclear.
- **Neighbour shares:** the four columns are still 100% null.
- **Window:** April–October only, one season.

## 3. The new SMAP columns

Ranges are over the 404,674 SMAP cell-days; fluxes over 21,186 county-days.

| Column | Null % of rows | Range | Meaning |
|---|---|---|---|
| `smap_cell_id` | 0 | 1,891 cells: rows 252–285, columns 892–962 | EASE-Grid 2.0 global 9 km cell, `r{row}c{col}`. One fixed cell per field (verified, section 4) |
| `smap_sm_surface` | 0 | 0.06–0.46, median 0.27 | Surface-layer volumetric soil moisture, m³/m³ |
| `smap_sm_rootzone` | 0 | 0.07–0.45, median 0.31 | Root-zone soil moisture, m³/m³ |
| `smap_sm_profile` | 0 | 0.09–0.46, median 0.32 | Whole-profile soil moisture, m³/m³ |
| `smap_sm_surface_wetness`, `_rootzone_wetness`, `_profile_wetness` | 0 | 0.14–0.91, 0.17–0.96, 0.24–0.94 | The same as a fraction of saturation (0–1) |
| `smap_sm_rootzone_pctl`, `smap_sm_profile_pctl` | 0.60, 0.03 | 0–99.99, median 49.3 and 49.5 | Percentile of soil moisture against its climatology, % |
| `smap_surface_temp` | 0 | 270.3–303.8 | Land surface temperature, **K** |
| `smap_soil_temp_layer1` | 0 | 273.3–302.4 | Top soil-layer temperature, **K** |
| `smap_snow_mass`, `smap_snow_depth` | 0 | 0–24.6 kg/m²; 0–0.137 m | Snow water equivalent and depth. Non-zero only in early April (statewide on 1–6 and 21 April) |
| `smap_land_evapotranspiration_flux` | 0 | 0.17–10.8 mm/day, mean 3.37 | Actual evapotranspiration, **kg m⁻² s⁻¹** (× 86,400 = mm/day) |
| `smap_overland_runoff_flux` | 0 | 0–70.5 mm/day | Surface runoff, kg m⁻² s⁻¹; tiny negative values occur |
| `smap_baseflow_flux` | 0 | ≈ 0 (1.1 mm over April–October) | Baseflow, kg m⁻² s⁻¹ |
| `smap_leaf_area_index` | 0 | 0.10–4.70, median 1.00 | Leaf area index, m²/m². See section 4: probably not 2025 vegetation |

The names match the SMAP L4 global 3-hourly 9 km geophysical product (SPL4SMGP). The file does not record the version.

## 4. How it was checked

**One value per cell-day.**

- 404,674 cell-days = 1,891 cells × 214 days, with a single value combination in each.
- 332 field rows per cell-day on average.
- Every field keeps one SMAP cell for the whole season.

**Grid placement.** Field centroids were projected to EASE-2 (EPSG:6933, 9,008.055 m cells): 628,659 of 628,672 fall in their own `smap_cell_id`, and the other 13 are one cell away.

**Daily means, not snapshots.** County-day SMAP temperatures against POWER:

| SMAP variable | vs POWER T2M | vs Tmin | vs Tmax |
|---|---|---|---|
| Surface temperature | r = 0.985, mean diff −0.32 °C | +5.23 °C | −6.06 °C |
| Top soil layer | r = 0.963, mean diff −0.79 °C | | |

A snapshot taken at one hour of the day would sit near Tmin or Tmax.

**Rain response.** Day-to-day change in surface soil moisture against rain, county-days April–September:

| Rain source | Same day | Previous day |
|---|---|---|
| IMERG | r = 0.64 | r = 0.01 |
| POWER | r = 0.58 | r = 0.31 |

Part of POWER's rain lands a day before the rise in soil moisture, while IMERG's does not. The products cut their days at different hours, so match SMAP with IMERG for day-level work.

**Evapotranspiration against FAO-56 ET0.** ET0 was computed from the POWER columns (Penman–Monteith, daily). County-day means by month:

| Month | SMAP ET, mm/day | ET0, mm/day | ET / ET0 | LAI | Root-zone SM, m³/m³ | Root-zone percentile | Soil layer 1, °C | IMERG, mm/day | POWER rain, mm/day | Runoff, mm/day |
|---|---|---|---|---|---|---|---|---|---|---|
| Apr | 2.27 | 3.18 | 0.71 | 0.37 | 0.332 | 37.3 | 8.9 | 3.55 | 2.93 | 0.66 |
| May | 3.17 | 4.33 | 0.73 | 0.64 | 0.327 | 33.8 | 14.7 | 3.01 | 2.03 | 0.45 |
| Jun | 4.64 | 4.73 | 0.98 | 1.21 | 0.325 | 46.8 | 21.0 | 5.02 | 5.92 | 1.17 |
| Jul | 5.26 | 4.59 | 1.15 | 2.40 | 0.326 | 69.6 | 23.2 | 6.86 | 7.00 | 1.59 |
| Aug | 4.34 | 3.87 | 1.12 | 2.53 | 0.313 | 79.3 | 21.4 | 2.92 | 2.78 | 0.54 |
| Sep | 2.45 | 3.44 | 0.71 | 1.24 | 0.276 | 57.8 | 19.6 | 1.76 | 1.52 | 0.15 |
| Oct | 1.41 | 2.79 | 0.51 | 0.41 | 0.267 | 41.0 | 14.3 | – | 1.60 | 0.15 |

- **The ratio follows a crop-coefficient curve:** it peaks at 1.15 in July and drops after harvest.
- **Over April–October, per county:** SMAP ET 720 mm, ET0 824 mm, POWER rain 727 mm, runoff 144 mm, baseflow 1 mm. Rain minus ET and runoff is −137 mm, consistent with the root zone drying from 0.332 to 0.267 m³/m³.

**Percentiles against the drought map.** County-days with a root-zone percentile, by the share of field area under a current D0+ USDM map (decoded as in `field_daily_2025.md`):

| Current-map D0+ share | County-days | Mean percentile | Median |
|---|---|---|---|
| None | 10,230 | 66.8 | 68.4 |
| Up to 50% | 2,880 | 45.3 | 43.7 |
| Over 50% | 8,069 | 36.5 | 34.8 |

The correlation between the percentile and the D0+ share is r = −0.53 (r = −0.25 with the D1 share).

**LAI behaves like a prescribed curve.**

- 77% of its day-to-day steps are linear within 0.001, and 21% exactly.
- It peaks on 1 or 8 August in 1,492 of 1,891 cells.
- Real 2025 crops would not peak on the same two dates across the state. A climatological vegetation input, as the L4 land model uses, would. **This is inferred from the data, not confirmed against the product documentation.**

**Soil temperature at planting.** County-mean top-layer temperature first holds ≥ 10 °C for five days in a row from **27 April** in the median county (range 9 April–4 May).

## 5. First look at yields (one year, descriptive only)

Correlation across counties between the 2025 yield anomaly (yield / previous 3-year mean) and July–August conditions:

| July–August value | Corn (n = 79) | Soybeans (n = 73) |
|---|---|---|
| Root-zone percentile | 0.06 | −0.39 |
| Root-zone soil moisture | 0.05 | −0.35 |
| SMAP ET (sum) | 0.18 | −0.25 |
| IMERG rain (sum) | −0.22 | −0.22 |
| POWER rain (sum) | −0.15 | −0.34 |
| Hot days ≥ 32 °C | −0.02 | 0.28 |
| ET0 − SMAP ET | −0.10 | 0.33 |

- **2025 was a wet summer.** The county mean of the July–August root-zone percentile was 74.5 (range 35–99), so water did not limit yields, and no positive soil-moisture signal is expected.
- **Corn shows nothing.**
- **Soybeans did slightly worse in wetter counties,** but in a single year that pattern follows geography and is not evidence of an effect.
- **A real test needs dry seasons.** SMAP L4 starts in 2015, so at most 11 seasons (2015–2025) can be built, and none of them is the 2012 drought.

## 6. Problems and traps

1. **Every problem of `2025.zip` is still here** (section 2).
2. **Redundancy is now 1.2 GB.**
   - SMAP holds 404,674 cell-days, each repeated for ~332 fields.
   - Normalised, the content takes ~57 MB: fields 32 MB, SMAP 21 MB, IMERG 3.2 MB, POWER 0.5 MB.
3. **Product, version and daily aggregation are not recorded.** That the values are daily means is inferred from the temperatures (section 4).
4. **LAI is probably not this season's crop.** Do not use it as a growth or yield signal.
5. **The units are raw:** temperatures in K and fluxes in kg m⁻² s⁻¹. Convert before use.
6. **Percentile gaps:**
   - 2,539 cell-days in 129 cells on 146 dates, scattered;
   - no cell misses more than 39% of days;
   - the other SMAP variables have no nulls.
7. **Still not field level.** 9 km cells hold ~332 fields each. That is finer than POWER (~50 km) and close to IMERG (0.1°).
8. **No SMAP before 2015,** so the 1991–2025 county panel of `field_dataset.md` cannot get soil-moisture features.

## 7. What it is useful for

| Use (Sivozmina) | Columns | Verdict |
|---|---|---|
| **m6, m7 water** | `sm_rootzone`, ET, runoff, plus ET0 from the POWER columns | **The best new input:** daily actual ET and root-zone moisture at 9 km, with a water balance that roughly closes |
| **M3 windows** | `soil_temp_layer1` (planting at ≥ 10 °C), `sm_surface` (field workability), snow | **Useful:** the planting soil-temperature window opened on 27 April in the median county |
| In-season drought | `sm_rootzone_pctl`, `sm_profile_pctl` | **A daily alternative to the weekly USDM map,** and it agrees with it (section 4) |
| m11 in-season features | July–August root-zone percentile, ET deficit | No signal in wet 2025. Worth testing over 2015–2025 with forward chaining |
| M2 confounders | Soil moisture, ET | A better cell-level water confounder than POWER rain |
| Crop growth | `leaf_area_index` | **No:** use observed LAI or NDVI (MODIS, HLS) instead |

## 8. Recommendations

1. **Normalise:** one table each for fields, POWER cell-days, IMERG cell-days and SMAP cell-days. That is ~57 MB instead of 1.2 GB. Done: `05_normalise_daily.py` writes 40 MB (zstd) and proves the panel rebuilds from it exactly.
2. **Write the SMAP product, version and daily aggregation rule** into the Parquet metadata.
3. **Fix the carried-over problems:** the drought coding, IMERG October and the four share columns (`field_daily_2025.md` section 7).
4. **Convert units at build time** (°C, mm/day), or put the units in the column names.
5. **Rename the LAI column** (for example `smap_lai_climatology`) or drop it. Take observed LAI from MODIS or HLS.
6. **For in-season features,** build the same SMAP table for 2015–2024 and test July–August soil moisture by forward chaining. The 2025 cross-section cannot answer this. The follow-up ran the test with POWER's MERRA-2 soil wetness and the water ledger over 1990–2025 (section 9 there); the SMAP backfill is in section 10.

## 9. Reading it

```python
import duckdb
con = duckdb.connect()
con.execute("CREATE VIEW d AS SELECT * FROM read_parquet('field_daily_2025_enriched/2025/*.parquet')")

# SMAP once per 9 km cell-day (404,674 rows), with units converted
smap = con.execute("""
SELECT smap_cell_id, date, any_value(COLUMNS(lambda c: c LIKE 'smap_%' AND c <> 'smap_cell_id'))
FROM d GROUP BY ALL""").df()
for c in ("smap_surface_temp", "smap_soil_temp_layer1"):
    smap[c] -= 273.15                                    # K -> degC
for c in ("smap_land_evapotranspiration_flux", "smap_overland_runoff_flux", "smap_baseflow_flux"):
    smap[c] *= 86400                                     # kg m-2 s-1 -> mm/day

# the field-to-cell lookup that joins it back
fields = con.execute("""
SELECT DISTINCT CSBID, county_fips, area_acres, power_cell_id, imerg_cell_id, smap_cell_id FROM d""").df()
```
