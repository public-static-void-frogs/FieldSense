# Follow-up: what was built from the 2025 daily panels

Work done on 4 Nov 2026 after the analysis of [`field_daily_2025.md`](field_daily_2025.md) and [`field_daily_2025_enriched.md`](field_daily_2025_enriched.md). Scripts 05–14 are in [`ml/field-prediction-model/analysis/`](../../../ml/field-prediction-model/analysis/) (run order in its README). Every number below is copied from their output or from a query on their output files. The data sits in `Field-Shift-NASA-data/`, next to the repo, with its own README. Nothing large is in git.

**In short.**

- **The 2025 panel is now 40 MB instead of 1.2 GB,** and rebuilding it from the tables gives the delivered file back in every column of every row.
- **Drought is rebuilt for every field and every weekly map, 2018–2025.** It reproduces the panel exactly and exposes one missing map: 10 June 2025.
- **M2 has four drought seasons to work with (2020–2023).** Corn after corn against corn after soybeans can be compared within 18–42 counties per season.
- **SMAP L4 root-zone moisture now exists for every day since 31 March 2015,** for all 1,891 panel cells, from a keyless NASS/GMU service. It matches the panel's 2025 values at r = 0.9975.
- **SMAP beats POWER's MERRA-2 at ground stations, but less than one year suggested.** Over 2015–2025 growing seasons on 24 ISU stations the median r is 0.68 against 0.58; in 2025 alone it was 0.73 against 0.40. The county water ledger reaches 0.69. For soil temperature both are good.
- **M3 v0 is built and scored on 2016–2025 using only earlier years:**
  - workable days reach r = 0.79 against NASS;
  - the 50% planting date errs by 4.9 days for corn and 5.7 for soybeans;
  - silking errs by 3.3 days.
- **The FAO-56 water ledger gives m6 and m7 per county for 1984–2026.** It finds the known droughts (1988, 2012, 2003, 2023) and follows SMAP in 2025 (median county r 0.86–0.91).
- **A cereal rye cover rarely leaves the next crop short of water in Iowa:** 3% of county-years against 0.1% for bare soil. The risky winters are the ones after the dry autumns of 1999, 2020 and 1988.
- **m11: soil water at planting does not beat the county trend.** Season water does, by 7–15% for corn, which makes it a scenario variable: in the driest fifth of seasons the corn yield anomaly has a P10 of 0.76.
- **Field greenness and the first M2 estimate** are in [`greenness_m1_m2.md`](greenness_m1_m2.md) (7 Nov): HLS for 50,209 fields in 2021–2025, no continuous-corn drought penalty detected in 2021/2023, a clear soybean rotation effect, and the M1 archive check (use `dataset.zip`, not `dataset (2).zip`).
- **A demo page shows one real field's 2025 season** with every layer: https://claude.ai/artifact/J1Nv1Rwh7s3N6dJHaJq3y2 (private until shared).

## 1. Where the data is

`Field-Shift-NASA-data/` (2.7 GB including the unpacked `field_dataset`) holds:

| Folder | Script | Size |
|---|---|---|
| `field_daily_2025/` | 05 | 40 MB |
| `power/` | 06 | 46 MB |
| `usdm/`, `m2/` | 07 | 176 MB, 60 MB |
| `reference/` | 08 | 0.2 MB |
| `insitu/` | 09 | 3.1 MB |
| `m3/` | 10 | 3.2 MB |
| `water/` | 11 | 145 MB |
| `smap/` | 12 | 96 MB |
| `m11/` | 01–03, 13 | 1.5 MB |
| `demo/` | 14 | 4 MB |
| `raw/` | download caches | ≈ 1.1 GB |

## 2. The 2025 panel, normalised (05)

The panel has 134,535,808 field-days and 66 columns. It splits into six tables:

| Table | Rows | Size |
|---|---|---|
| `fields` | 628,672 | 14.0 MB |
| `county_yields` | 99 | < 0.1 MB |
| `power_cellday` | 14,552 | 0.4 MB |
| `imerg_cellday` | 359,734 | 1.5 MB |
| `smap_cellday` (raw units plus °C and mm/day) | 404,674 | 22.2 MB |
| `drought_field_map` (each field's covering maps) | 8,318,044 | 3.9 MB |

- **Constancy is asserted.** Every table must be constant on its grain, or the script stops.
- **The rebuild is exact.** Joining the tables back gives all 60 non-key columns identical on all 134,535,808 rows. The four `*_share_*` columns are empty and are dropped.
- **The drought rule checks out:**
  - the panel never shows a map before its valid date + 2 days;
  - a field-day carries the last covering map before that, which the rebuild reproduces with an as-of join.

## 3. Drought for every field, 2018–2025, and the M2 study units (07)

**Method.**
- All 418 weekly U.S. Drought Monitor shapefiles, from 2 Jan 2018 to 30 Dec 2025.
- Each field's class is the highest D-level polygon that contains its centroid.
- The CDL history comes from four sources, which never disagree. CDL 2025 is in none of them.

**Validation against the 2025 panel.**
- 31 maps × 628,672 fields = 19,488,832 field-maps, with **0 disagreements**.
- **The panel's one gap is the 10 June 2025 map.** No row carries it, so on 12–18 June every field decodes as no drought. USDM had 521,841 fields in drought that week (439,648 D0, 82,193 D1).
- Against USDM county statistics, the D2+ share over 7,029 county-maps (Jul–Aug 2018–2025) has r = 0.9996 and a mean absolute difference of 0.0021.

**Drought seasons** (the proposal's rule: D2+ in at least 4 of the Jul–Aug maps):

| Season | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|
| Fields | 32,893 | 0 | 87,681 | 193,408 | 89,333 | 220,641 | 0 | 0 |
| Counties | 11 | 0 | 25 | 46 | 30 | 60 | 0 | 0 |

2018 has no previous-year crop in CSB, so **M2 can use 2020–2023**.

**Natural-experiment capacity.** The table gives the number of counties with at least 100 drought fields in both arms.

| Contrast | 2020 | 2021 | 2022 | 2023 |
|---|---|---|---|---|
| Corn after corn vs corn after soybeans (T1) | 21 | 42 | 18 | 42 |
| Soybeans after soybeans vs after corn (T1) | 2 | 6 | 9 | 18 |
| Corn, small grain or hay in history vs not (T3) | – | 12 | 6 | 15 |
| Corn, ≥ 3 crop groups vs 1–2 (T2) | – | – | – | 40 |

- **Continuous corn is the strong contrast.** Continuous soybeans and small grains are thin.
- T2 needs five years of history, so only 2023 has it.
- These are exposures and arms. **The M2 outcomes are not built yet:** field yield proxies such as HLS greenness or ECOSTRESS ESI (proposal Y1–Y3).

## 4. NASA POWER daily, 1981–2026, and ET0 (06)

**Requests.** Two point requests per POWER cell (68 cells), 1 Jan 1981 – 30 Sep 2026, give 1,136,212 cell-days.
- **Weather:** everything the panels use, plus clear-sky solar.
- **MERRA-2 land surface:**
  - soil wetness (top 5 cm, root zone, profile);
  - soil temperatures;
  - snow;
  - the evapotranspiration energy flux.

The requests end on the last MERRA-2 day, so the ×24 rain bug of GEOS-IT days does not apply; the script asserts it.

**ET0 and percentiles.**
- **FAO-56 Penman–Monteith ET0** is computed from these columns. Solar starts in 1984, so ET0 does too; 129 isolated cell-days without solar are interpolated.
- **Wetness percentiles** are computed against each cell's 1991–2020 values within ±15 days of the date.

**The panel's POWER columns are POWER:** the 12 variables match on all 14,552 cell-days of 2025, with a maximum difference of 0.0.

**MERRA-2 against SMAP L4, 2025** (SMAP area-weighted to the POWER cell; 14,552 cell-days):

| POWER | SMAP | r daily | r within a cell (time) | r across cells (same day) | Mean POWER / SMAP |
|---|---|---|---|---|---|
| GWETTOP | surface wetness | 0.64 | 0.82 | 0.48 | 0.57 / 0.55 |
| GWETROOT | root-zone wetness | 0.43 | 0.81 | 0.29 | 0.54 / 0.63 |
| root-zone percentile (vs 1991–2020) | `sm_rootzone_pctl` | 0.82 | 0.88 | 0.64 | 42 / 51 |
| TSOIL1 (2–10 cm) | `soil_temp_layer1` | 0.987 | 0.987 | 0.91 | 18.2 / 17.6 °C |
| TSURF | `surface_temp` | 0.982 | 0.982 | 0.88 | 18.6 / 18.1 °C |

- **Soil temperature** from POWER can stand in for SMAP in any year.
- **Soil moisture** from POWER follows SMAP in time but not in its spatial pattern. Section 5 shows which one is closer to the ground truth.

**`EVPTRNS` is not usable as ET.** Divided by 2.45 MJ/kg it gives 1.56 mm/day against SMAP's 3.34, and less than ET0 in every month (July: 3.07 against SMAP 5.25 and ET0 4.62).

**ET0 against gridMET.** gridMET grass ET0 is a 4 km product calibrated on stations. The comparison uses 6 POWER cell centres over 2001–2025 (54,786 days). The gridMET server stopped answering after 6 of the planned 17 cells; the script now keeps going with the cells it has. One more trap: the THREDDS CSV returns gridMET ET0 in tenths of mm.

| Month | Apr | May | Jun | Jul | Aug | Sep | Oct |
|---|---|---|---|---|---|---|---|
| POWER FAO-56, mm/day | 3.10 | 3.86 | 4.86 | 5.18 | 4.62 | 3.75 | 2.41 |
| gridMET, mm/day | 3.65 | 4.41 | 5.48 | 5.67 | 4.80 | 4.02 | 2.72 |
| Ratio | 0.85 | 0.87 | 0.89 | 0.91 | 0.96 | 0.93 | 0.89 |

- Daily r = 0.939.
- May–Sep sums: r = 0.70, and POWER is **0.914 of gridMET**.
- So m6 built on POWER ET0 is about 9% lower than it would be on gridMET, which matches the ×0.92 noted in `research/weather_climate.md`.

## 5. Ground check: ISU Soil Moisture Network (09)

The network has 29 Iowa stations (Iowa Environmental Mesonet). They record daily soil temperature at 10 cm and water content at 30, 60 and 127 cm, from 2013 or later. All 29 fall inside the panel's SMAP grid and POWER cells.

A station is a point and a SMAP cell is 9 km, so the scores are temporal and computed per station: correlation and unbiased RMSE (the SMAP L4 validation metric). The table gives the median over stations.

| Comparison | Stations | Days | Median r | 10th pct r | Median bias | Median ubRMSE |
|---|---|---|---|---|---|---|
| 10 cm soil T vs SMAP layer 1, 2025 | 24 | 5,093 | **0.963** | 0.950 | −1.0 °C | 1.5 °C |
| 10 cm soil T vs POWER TSOIL1, 2025 | 24 | 8,610 | 0.984 | 0.979 | −1.2 °C | 2.1 °C |
| 10 cm soil T vs POWER TSOIL1, 2013–2025 | 26 | 97,934 | 0.984 | 0.982 | −1.5 °C | 2.0 °C |
| 30–60 cm water vs SMAP root zone, 2025 | 20 | 4,102 | **0.73** | −0.00 | −0.03 m³/m³ | 0.028 |
| 30–60 cm water vs POWER GWETROOT, 2025 | 21 | 7,035 | 0.40 | 0.04 | – | – |
| 30–60 cm water vs POWER GWETROOT, 2013–2025 | 24 | 84,413 | 0.43 | 0.30 | – | – |

(GWETROOT is a wetness fraction, so only its correlation is comparable.)

**The date soil first reaches 10 °C** (5-day mean, per station-year):
- **POWER minus station:** median +1 day, MAE 4.2 days, 80% within a week (248 station-years).
- **SMAP minus station, 2025 only:** median +3 days, MAE 4.0 days (23 stations). Counting from 4 April for both, because SMAP starts on 1 April.

**What this means:**
- For temperature, POWER is as good as SMAP and covers 45 years. M3 uses it.
- For root-zone water, SMAP is better than MERRA-2. The 2025 gap (0.73 against 0.40) is larger than the 2015–2025 growing-season gap (0.68 against 0.58, section 10).
- The low 10th-percentile r shows that a few stations do not resemble their 9 km cell at all, which is normal for point sensors.

## 6. M3 windows (10)

Everything runs per POWER cell and year, 1981–2026. NASS crop reporting districts are field-area-weighted means of their cells. NASS weekly progress by district comes from 1974–2025 via IEM; COOP station data from IEM.

**Each part is scored on 2016–2025 using only earlier years.**

**Workable days.** The model is a logistic in surface wetness (GWETTOP), rain on the day and the two days before, and frozen or snow-covered soil. It is fitted so that district weekly sums match NASS "days suitable for fieldwork", 2001–2015.

| Test 2016–2025 | Weeks | r | RMSE, days/week | RMSE of the district × week climatology |
|---|---|---|---|---|
| Apr–Nov | 3,006 | 0.79 | 1.01 | 1.48 |
| Apr–May | | 0.79 | 1.18 | 1.68 |

In 2025 (216 district-weeks), the weekly mean of SMAP surface wetness alone tracks NASS as closely as the fitted model: r = −0.76 against +0.76. **SMAP surface wetness is a direct workability signal.**

**Planting progress.** From day D0, on days whose 5-day soil temperature (TSOIL1) is at least T, the crop is planted at rate r × workable probability. (D0, T, r) are refitted for each test year on the 15 years before it, because practice moves:
- soybeans reached 50% planted on 18 May on average in 2001–2015 and on 9 May in 2020–2025;
- corn stayed at about 3–5 May.

The first fit, frozen on 2001–2015, was 5.8 days late on soybeans in 2016–2025.

| 50% planted date, test 2016–2025 | District-years | MAE, days | Bias | MAE of the climatological date | r of yearly means |
|---|---|---|---|---|---|
| Corn | 88 | 4.9 | +0.1 | 5.1 | 0.31 |
| Soybeans | 90 | 5.7 | +4.2 | 8.4 | 0.89 |

- **Soybeans have real skill.**
- **Corn barely beats its climatology.** Corn planting in Iowa is fast and early in most years, so there is little to predict.
- **Parameters for current practice** (fitted on 2011–2025): corn from 22 April, soybeans from 25 April, both at TSOIL1 ≥ 6 °C (MERRA-2 runs 1.5 °C cold, so about 7.5 °C at a station).

**Silking and maturity** use growing degree days (10/30 °C) from the 50% planted date. A year's GDD requirement is the median of the 5 years before it.

| Test 2016–2025 | GDD now (2021–2025) | MAE, days | Bias | MAE of the mean interval |
|---|---|---|---|---|
| Corn silking | 791 | **3.3** | −0.2 | 4.9 |
| Corn maturity | 1,582 | 8.3 | −1.2 | 6.3 |

- **Silking works. Maturity does not:** a fixed number of days does better.
- Hybrids lengthened. Planting → maturity took 1,448 GDD in 2000–2004 and 1,584 in 2020–2024, while planting → silking stayed near 750–790.

**Against 117 NWS COOP stations** (long records since 1981, POWER cell containing the station, 5,265 station-years):

| POWER minus station | Bias | MAE | Median station r |
|---|---|---|---|
| Last spring frost (0 °C) | −1.8 days | 6.0 days | 0.59 |
| First autumn frost (0 °C) | **+5.5 days** | 7.1 days | 0.56 |
| Killing frost −2.2 °C, spring / autumn | −0.6 / **+6.0** days | 6.1 / 8.7 | 0.52 / 0.50 |
| Days ≥ 35 °C, Jun–Aug | +1.5 days | 3.2 | 0.79 |
| Days ≥ 32 °C, Jun–Aug | −0.8 days | 8.1 | 0.70 |
| Mean Tmax Jun–Aug | −0.07 °C | | |

- **POWER's grid-cell nights are milder in autumn,** so its autumn frost comes about 6 days late. Correct the autumn frost window by −6 days before showing it.
- At the modelled silking dates, the chance of at least one day ≥ 35 °C is **0.34 in POWER and 0.28 at the stations** (4,095 station-years).

**The windows,** given as the median over cells of each cell's P10 / P50 / P90 over 1991–2025 weather, with current practice and hybrids. The trend is per decade over 1981–2025.

| Event | P10 | P50 | P90 | Trend per decade | Cells with p < 0.05 |
|---|---|---|---|---|---|
| Soil reaches 10 °C | 31 Mar | 14 Apr | 29 Apr | −1.4 days | 0% |
| Corn 50% planted | 3 May | 7 May | 12 May | −0.1 | 0% |
| Soybeans 50% planted | 12 May | 17 May | 23 May | −0.3 | 1% |
| Last spring frost, 0 °C | 13 Apr | 24 Apr | 7 May | −0.2 | 0% |
| Corn silking | 15 Jul | 22 Jul | 30 Jul | −1.7 | 75% |
| Corn maturity | 13 Sep | 25 Sep | 19 Oct | −4.2 | 51% |
| First autumn frost, 0 °C (uncorrected) | 3 Oct | 14 Oct | 29 Oct | **+3.8** | **100%** |
| Workable days 15 Apr – 31 May | 20 | 27 | 33 | +0.5 | 0% |

- The autumn frost-free season has lengthened in every cell.
- A fixed hybrid silks about 1.7 days per decade earlier, because the warming speeds up degree days.

**Risks:**
- **Heat at silking.** The share of seasons with at least one day ≥ 35 °C within a week of silking is 0.37 for usual planting. Planting 10 days earlier or 20 days later also gives 0.37; 10 days later gives 0.40. Shifting planting does not move heat risk in Iowa.
- **Frost.** A killing frost (−2.2 °C) after 10% of the corn is planted happens in 14% of seasons, and frost before maturity in 7%.

## 7. Water ledger: m6 demand and m7 gap (11)

**Method.**
- FAO-56 single-coefficient daily root-zone balance (Allen et al. 1998, eq. 84–86), per county, 1984–2026.
- Coefficients checked against the FAO pages:
  - corn: Kc mid 1.20 and end 0.35, p = 0.55, root zone 1.5 m;
  - soybeans: Kc 1.15 / 0.50, p = 0.50, root zone 1.2 m, stages 20/35/60/25 days.
- Kc ini is set to 0.5 for Iowa's frequent spring rain.
- Water capacity comes from SSURGO county available water storage (08): 0–100 cm mean 179 mm (range 154–206), 0–150 cm mean 261 mm.
- Rain is POWER, with runoff by curve number 75.
- **Calendar:**
  - planting from M3;
  - corn stages by M3's GDD sums;
  - a corn season that has not matured by the first killing frost or 31 October ends there;
  - harvest is the NASS district mean 50% date.
- **The metrics:**
  - m6 = Σ Kc·ET0 from planting to maturity;
  - m7 = m6 − Σ Ks·Kc·ET0, the demand that rain and stored water did not cover.

| County-seasons 1991–2025 | m6, mm | Actual ET, mm | m7, mm | m7 around silking, mm | Season rain, mm | Stress days |
|---|---|---|---|---|---|---|
| Corn P10 / P50 / P90 | 489 / 557 / 628 | 442 / 510 / 566 | 0 / 21 / 150 | 0 / 0 / 61 | 320 / 505 / 734 | 0 / 26 / 65 |
| Soybeans P10 / P50 / P90 | 465 / 561 / 683 | 415 / 483 / 537 | 0 / 61 / 236 | – | 324 / 470 / 665 | 0 / 46 / 84 |

**Worst Iowa-mean years for m7:**
- **Corn:** 1988 (280 mm), 2012 (255), 2003 (145), 2023 (137), 2006 (126), 2013 (123).
- **Soybeans:** 1988 (385), 2012 (354), 2023 (226), 2003 (207), 2005 (203), 2013 (192).

These are the known Iowa droughts. Soybean gaps are larger because their season runs through August on a shallower root zone.

**Checks of the ledger's relative soil water** (1 − depletion / capacity):

| Against | Corn | Soybeans |
|---|---|---|
| SMAP root-zone wetness, 2025, median county r over time | 0.86 | 0.91 |
| SMAP, spatial r across counties on 15 Apr / 31 Jul / 31 Oct 2025 | 0.58 / 0.27 / 0.41 | 0.55 / 0.28 / 0.66 |
| POWER GWETROOT, 1984–2025, median county r | 0.76 | 0.77 |
| ISU stations 30–60 cm water content, median station r (24 stations) | 0.51 | 0.51 |

**Against county yield anomalies** (yield / the county's linear trend, 1990–2025):

| r with the anomaly | Pooled | Iowa means by year | Within a year (median) |
|---|---|---|---|
| Corn m7 (3,460 county-years) | −0.28 | −0.28 | −0.34 |
| Corn m7 around silking | −0.26 | −0.25 | −0.28 |
| Soybeans m7 (3,427) | −0.27 | −0.32 | −0.15 |

- The gap explains part of the losses, not all of them: wet and cold years like 1993 lose yield with no water gap.
- m6 rests on POWER ET0, about 9% below gridMET (section 4).

## 8. m9: does a cover crop leave the next crop short of water? (11)

**Method.**
- From harvest to the next crop's planting (corn → soybeans and soybeans → corn), in a 1 m root zone.
- **Two branches:**
  - bare soil (Kc 0.3);
  - cereal rye: Kc 0.4 (FAO winter wheat on frozen soils) until green-up at a 5-day soil temperature of 5 °C, then a ramp to 1.0 at termination 14 days before planting.
- **Weather years:** 1984–2025, 8,217 county-years.
- **Outcome:** a "dry start", where the next crop starts with less than half of the plant-available water.

| After | P(dry start), bare | P(dry start), cereal rye | Median water at planting, bare / rye |
|---|---|---|---|
| Corn | 0.1% | 3.2% | 98% / 97% |
| Soybeans | 0.0% | 2.9% | 98% / 98% |

- 244 of 8,217 county-years start dry only because of the rye.
- **The risk sits in a few winters.** The extra spring depletion from the rye averages 32% of capacity after the 1999 harvest, then 19% after 2020, 17% after 1988, 16% after 1987, 15% after 2003 and 11% after 2005. These are dry autumns followed by dry springs.
- For the rule engine (`m3 ≥ 4 months and m9 ≤ 0.3`), m9 is low almost everywhere in Iowa. Its real use is a year-specific warning after a dry autumn.
- **Not done yet:**
  - the proposal's correction of the ledger against SMAP root-zone moisture (SMAP since 2015 now exists, section 10);
  - the "autumn rain needed" output.

## 9. m11 with soil water (13)

**Setup.** The panel, the county trend and the validation are script 04's. The functions are imported, not copied. Every feature set is scored on the same county-years.
- **Soil features at planting**, for a planner:
  - POWER root-zone wetness percentile, 1–15 April;
  - October–March precipitation;
  - ledger plant-available water at the modelled planting date.
- **In-season features**, an oracle for a pre-season tool:
  - m7 and stress days;
  - corn's gap around silking;
  - July–August root-zone percentile;
  - heat days at silking.

RMSE in bu/ac (lower is better):

| Corn | Forward 1995–2025 | Leave-one-year-out 1991–2025 |
|---|---|---|
| Trend only | **20.0** | **20.9** |
| + yield lags (ridge) | 22.2 | 21.3 |
| + soil at planting (ridge / gradient boosting) | 23.8 / 23.0 | 22.3 / 23.8 |
| Oracle: same-summer weather means (04), boosting | 19.2 | 19.1 |
| Oracle: in-season water, boosting | **18.6** | **17.7** |
| Oracle: in-season water + same-summer weather, boosting | 17.7 | 17.6 |

| Soybeans | Forward 1995–2025 | Leave-one-year-out 1991–2025 |
|---|---|---|
| Trend only | **6.14** | **5.92** |
| + soil at planting (ridge) | 8.48 | 6.24 |
| Oracle: same-summer weather (ridge) | 6.82 | 6.00 |
| Oracle: in-season water (ridge / boosting) | 6.71 / 6.36 | 5.61 / 5.88 |
| Oracle: in-season water + same-summer weather (ridge) | 6.03 | **4.91** |

With April drought, forward from 2001: corn trend 23.3, + soil at planting + April drought 24.0; soybeans 5.99 against 6.67.

**What it says:**
- **Soil water at planting does not help m11.** Every pre-season set is worse than the trend, as the previous-summer weather was in `field_dataset.md` section 10. Iowa soils are usually refilled by spring (section 8), so the planting state carries little of the season.
- **Season water explains part of the corn residual.** It does better than the same-summer weather means: 18.6 against 19.2 forward. That is a 7% gain over the trend forward and 15% in leave-one-year-out.
- **Soybeans gain only with water and weather together** (−17% in leave-one-year-out). The forward gain is small.

**m11 in a pre-season planner is therefore the trend plus a conditional range.** The yield anomaly (yield / the county's trend) depends on the season's water gap:

| Corn, m7 range | County-years | P10 | P50 | P90 |
|---|---|---|---|---|
| 0–3 mm (no gap; includes the wet and cold years) | 1,384 | 0.85 | 1.03 | 1.15 |
| 3–39 mm | 692 | 0.91 | 1.03 | 1.15 |
| 39–103 mm | 692 | 0.91 | 1.02 | 1.14 |
| 104–345 mm | 692 | **0.76** | 0.96 | 1.09 |

| Soybeans, m7 range | County-years | P10 | P50 | P90 |
|---|---|---|---|---|
| 0–1 mm | 686 | 0.83 | 1.02 | 1.12 |
| 1–32 mm | 685 | 0.92 | 1.03 | 1.15 |
| 32–86 mm | 685 | 0.93 | 1.03 | 1.15 |
| 87–173 mm | 685 | 0.91 | 1.03 | 1.12 |
| 173–458 mm | 686 | **0.73** | 0.95 | 1.09 |

(The corn quintiles merge into four bins because 40% of county-seasons have a gap below 3.3 mm.)

**How to use it.** For a strategy, m14 can pair M3/ledger scenarios (the water-gap distribution of the county over 1991–2025) with these conditional ranges, instead of a point forecast.

## 10. SMAP L4 before 2025 (12)

**Source.** No Earthdata login was available, so the backfill uses Crop-CASMA (USDA NASS with George Mason University, CSISS). It needs no key.
- **Data:** SMAP L4 SPL4SMGP surface (0–5 cm) and root-zone (0–100 cm) soil moisture. Each day is the mean of the eight 3-hourly files, the same definition as the panel. Coverage is 31 Mar 2015 – 1 Nov 2026: 4,232 days, with 14–15 Dec 2016 missing. The latest day lags about 3 days.
- **Format:** reprojected to EPSG:5070 on a 9 km grid.
- **Access:**
  - the WPS `GetFileByAoi` call returns a float32 GeoTIFF for a lon/lat polygon, which covers all 1,891 panel cells;
  - `GetFileByFips` drops about 100 edge cells;
  - WCS returns uint8, so it is not usable.

**Matching to the panel's EASE-2 cells.** The script picks one Albers pixel per cell: the best of the 5×5 around the cell centre, fitted on April–July 2025. On held-out days (Aug–Oct 2025, 173,972 cell-days):

| Variable | r | RMSE, m³/m³ | Median r per cell |
|---|---|---|---|
| Root zone | 0.9975 | 0.0027 | 0.9999 |
| Surface | 0.9967 | 0.0044 | 0.9992 |
| Root zone, centre pixel only | 0.863 | 0.0201 | – |

- Close, not identical: 65% of held-out root-zone values agree to 0.001 m³/m³. The causes are the reprojection and possibly a different product version, which Crop-CASMA does not state.

**Percentiles and what is missing.**
- **Only 2 of the 16 panel variables exist here.** There is no soil temperature, ET, runoff, snow or SPL4SMGP percentile.
- **Percentiles are recomputed** per cell against the 2015–2026 record, ±15 days of the date. Against the panel's percentile in 2025:
  - r = 0.951, bias −4.4 points;
  - 13.5% of cell-days fall below 20, against 9.9% in the panel;
  - the "below 20" flag agrees on 93.3% of cell-days.
- The record includes the 2021–2023 droughts, so these percentiles run lower.

**The M2 SMAP rule by year.** Cells with ≥ 30 days below the 20th percentile in July–August:

| 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 0 | 572 | 347 | 0 | 333 | 895 | 678 | 1,106 | 0 | 0 | 223 |

- **It agrees with the USDM seasons** in section 3: 2020–2023 dry, 2019 and 2024–2025 not.
- **It adds 2017,** which USDM rates mild.
- **It adds 2026,** which is not yet in the USDM build. The proposal flags a SMAP geolocation issue for May–July 2026, and the 2026 values were not checked for it.

**Checks over 2015–2025** (script `notes/smap_history_checks.py` in the data folder):

| Comparison | Median r |
|---|---|
| Water ledger (11) vs SMAP root zone, per county over time, all days / Apr–Oct | corn 0.82 / 0.87, soybeans 0.81 / 0.87 |
| Ledger vs SMAP across counties on 15 April, median of the years | corn 0.49, soybeans 0.38 |
| ISU stations 30–60 cm vs SMAP root zone, all days (24 stations, 75,991 days) | 0.55 |
| **Same 24 stations and days, Apr–Oct (45,490 days): SMAP / MERRA-2 GWETROOT / ledger (corn)** | **0.68 / 0.58 / 0.69** |

- **Across many growing seasons, SMAP beats MERRA-2 at the stations, but by less** than the 2025 comparison suggested (section 5).
- **The simple county ledger does as well as SMAP** at points. They agree closely in time (0.87), so the proposal's step "correct the ledger against SMAP with a residual model" now has 11 years to train on.

**The exact 16-variable backfill needs Earthdata.** NSIDC SPL4SMGP v008 has 28,524 granules for 2015–2024, about 4.06 TB at 142.4 MB each (public CMR search). Without a subsetting service that is not practical, and none was tested. Steps:
1. create an account at urs.earthdata.nasa.gov;
2. give `earthaccess` the credentials (environment variables, `.netrc` or prompt);
3. test Harmony or OPeNDAP subsetting to Iowa first.

**Output.** `smap/smap_cropcasma_cellday_2015_2026.parquet`: 8,002,712 rows (1,891 cells × 4,232 days), 84 MB, no nulls. Alongside it are the pixel map and the 2025 validation table.

## 11. Demo: Field Season 2025 (14)

The demo page is https://claude.ai/artifact/J1Nv1Rwh7s3N6dJHaJq3y2. It is private: share it from its Share menu.

**What it shows.** It has 198 real CSB fields: the largest corn field and the largest soybean field of 2024 in each county. For the chosen field, on one time axis from 1 April to 31 October 2025, it shows:
- IMERG rain;
- the USDM class with all 32 maps, including 10 June;
- SMAP root-zone percentile, soil temperature and ET;
- POWER ET0;
- the county water ledger.

**Cards beside the chart:**
- the cell's M3 windows against 2025;
- heat at silking for shifted planting;
- m6 and m7 of 2025 against history;
- m9 for cereal rye.

A weekly table gives every value without hovering.

**The 2025 crop is a rotation guess.** CDL 2025 is not in the data, so the page takes the opposite of the 2024 crop and lets the viewer switch it.

## 12. Not done, and why

- **The backend's soil-moisture thresholds** in `backend/app/services/crop_conditions.py` were not changed.
  - The backend serves forecasts for any coordinates. SMAP here is Iowa history only, with a few days' latency.
  - The ready pieces for an endpoint are `field_daily_2025/` (any CSBID in two joins), `m3/` and `water/`.
  - That decision belongs to the backend owner.
- **CDL 2025 per field.** The CSB 2025 edition on Source Cooperative has CDL2025 and the real polygons (keyless).
- **M2 outcomes:** HLS greenness is now built (see `greenness_m1_m2.md`); ECOSTRESS ESI and OpenET per field are not.
- **M3 futures** from NEX-GDDP-CMIP6 deltas, and an ML quantile model on top of the climatology baseline.
- **m6 per crop calibrated on OpenET.** That needs an API key. SMAP ET cannot separate crops: its LAI is a climatology.

## 13. Recommendations

1. **Use the normalised tables, not the zips,** and `usdm/field_map_class_2018_2025.parquet` instead of the panel's drought block.
2. **M2:** build the outcome table for 2020–2023 drought seasons first (HLS peak greenness per field), then the corn-after-corn contrast in the 42 counties of 2021 and 2023.
3. **M3:**
   - ship the planting and silking windows;
   - correct POWER's autumn frost by −6 days;
   - replace GDD maturity with a day interval until it beats one.
4. **Water:**
   - present m7 as a range per county and crop, P50 and P90;
   - move ET0 to gridMET (or apply ×1.09) if absolute millimetres matter more than ranking.
5. **m9:** show it as a year-specific warning after dry autumns, not as a fixed county score.
6. **SMAP history (section 10):**
   - use it for the M2 SMAP drought rule per cell, 2015–2026;
   - train the ledger's SMAP residual correction on it;
   - keep the cached tiles, since one university server is the only keyless source.
   - The exact 16-variable panel for 2015–2024 needs an Earthdata account and a subsetting service.
