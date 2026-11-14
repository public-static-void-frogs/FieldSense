# Field greenness: the M1 archives, an HLS build for 2021–2025, and the first M2 estimate

Work of 7 Nov 2026. It covers:
- the two archives `dataset.zip` and `dataset (2).zip`;
- scripts 15–17 in [`ml/field-prediction-model/analysis/`](../../../ml/field-prediction-model/analysis/).

Every number below is copied from script output. The data is in `Field-Shift-NASA-data/` (`src/greenness_2025_v1`, `…_v2`, `greenness/`, `m1/`, `m2/effect/`). Nothing large is in git.

**In short.**

- **The archives are the M1 crop-type training set** (8,000 fields, 47 states, 2025), not drought-year greenness.
- **Use `dataset.zip` (v1). `dataset (2).zip` (v2) is broken:**
  - same fields and labels, but corn and soybean curves are swapped in time;
  - a reference classifier reaches 0.90 on v1 and 0.74 on v2;
  - an independent HLS build matches v1 at r = 0.98 and v2 at no lag.
- **M1 is feasible early.** On v1, corn and soybeans are told apart nine times in ten by mid-July. Iowa held out scores 0.97. A model trained on 2025 still gets 0.86–0.91 on corn vs soybeans in 2021–2024.
- **HLS greenness built for M2 without a key.** NASA HLS from Planetary Computer covers 50,209 fields in 32 squares, 2021, 2023, 2024 and 2025, in the archive's 16-step format.
- **M2, first estimate:**
  - in the 2021 and 2023 droughts, corn after corn did not lose more greenness than corn after soybeans (peak NDVI interaction +0.001, 95% CI −0.0006 … +0.0027, roughly ±2 bu/ac);
  - those droughts were mild for the crops (−0.006 peak NDVI for corn);
  - **soybeans after soybeans are clearly less green in every year** (−0.028 peak NDVI, −0.06 NDWI), whether or not there is a drought;
  - **in bushels, through an NDVI → yield proxy, about −3.8 bu/ac a year (se 0.8).** The proxy works for soybeans (it ranks counties within a year, median r 0.42) but not for corn, whose canopy saturates.
- **ECOSTRESS evaporative stress** (canopy temperature; 4.08 M field-overpasses, 2020–2024, partial download):
  - **corn after corn again shows no extra drought loss** (+0.0002, CI −0.0018 … +0.0020);
  - **but ESI itself does not register the 2021/2023 droughts,** and its county relation with yield has the wrong sign;
  - so it does not replace NDVI as a stress outcome here.
  - A soybean-monoculture drought signal in ESI (−0.012, p ≈ 0.005) is a lead, not evidence (section 7).
- **M3 check:** satellite green-up of soybeans follows NASS planting dates (r = 0.61), slightly better than M3's model on the same district-years (0.52).

## 1. What the archives are

Both archives are the **M1 crop-type training set**, not a drought-year greenness table:

| | `dataset.zip` (v1, 3 Nov) | `dataset (2).zip` (v2, 4 Nov) |
|---|---|---|
| Fields | 8,000 | 7,999 (the same fields, one dropped) |
| States | 47 (Iowa 546) | 47 (Iowa 546) |
| Year | 2025 | 2025 |
| Classes | corn, soybeans, alfalfa, grassland/pasture, 2,000 each | same |
| Tensor `X` | (8,000, 3, 16): NDVI, EVI, NDWI × 16 season steps | (7,999, 3, 16) |
| Split train / val / test | 5,580 / 1,254 / 1,166 | 5,449 / 1,236 / 1,314 (39% of fields moved) |
| Median observed steps | 16 | 15 |

**Format.**
- `X.npy` equals the flat `tabular.parquet` columns `ndvi_d1 … ndwi_d16`.
- NDWI is Gao's (NIR − SWIR) / (NIR + SWIR): about +0.42 at the NDVI peak, negative on bare spring soil.
- The step dates are not in the archive. 16 equal steps over 1 April – 31 October fit the crop curves, and section 4 confirms them against HLS.
- **The team's extractor is now on `main`** (`data/nasa_hls_greenness_ts/crop_ts.py`) and confirms this build:
  - HLS S30/L30 with B8A/B11 and B05/B06;
  - Fmask bits 1–4;
  - 16 equal steps over 04-01..10-31, median per step, linear fill;
  - Gao NDWI.
  It averages the pixels inside each field polygon, where script 16 uses a window at the centroid.
- The labels are CDL 2025, so the Iowa fields give the first ground truth for 2025.

**The versions differ in their values, not their fields.** NDVI differs by 0.12 on average (mean absolute). The median crop curves (NDVI, step 1 = early April):

| Step | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|
| v1 corn | 0.34 | 0.48 | 0.76 | 0.86 | 0.89 | 0.88 | 0.87 | 0.82 | 0.66 |
| v1 soybeans | 0.33 | 0.40 | 0.53 | 0.72 | 0.86 | 0.88 | 0.89 | 0.86 | 0.68 |
| v2 corn | 0.31 | 0.45 | 0.62 | 0.79 | 0.85 | 0.87 | 0.88 | 0.84 | 0.69 |
| v2 soybeans | 0.35 | 0.58 | 0.77 | 0.86 | 0.87 | 0.86 | 0.85 | 0.79 | 0.62 |

- **In v1, soybeans green up two steps after corn and peak later**, as they do in the Corn Belt: half green-up at step 7 for corn and step 8 for soybeans, peak at step 9 and step 11.
- **In v2 the order is reversed:** soybeans green up before corn and corn peaks later. That is not how these crops grow.

## 2. Which version to use: v1

The M1 reference classifier settles it (section 3). On the same fields and labels:

| | v1 | v2 |
|---|---|---|
| Test accuracy, 4 classes | **0.901** | 0.742 |
| Macro F1 | 0.900 | 0.739 |
| Corn / soybeans recall | 0.929 / 0.933 | 0.640 / 0.714 |
| Iowa held out (trained on the other 46 states) | **0.967** | 0.789 |
| Corn vs soybeans with steps 1–8 known | 0.910 | 0.719 |

Test confusions between corn and soybeans:

| | v1 | v2 |
|---|---|---|
| Corn called soybeans | 10 | 83 |
| Soybeans called corn | 10 | 78 |

**v2 lost most of the corn/soybean signal.** The reversed curves suggest the time steps were shifted for part of the fields when it was rebuilt. **Use v1** and ask whoever built v2 what changed. Section 4 confirms this with HLS.

## 3. M1 reference classifier

The classifier is scikit-learn gradient boosting on the 48 index features, using the archive's own splits. It is a yardstick for the CV model, not the CV model itself (on `main`: SAM2 segmentation in `ml/field-cv-model/`, TempCNN crop classes in `backend/app/services/section_analysis.py`).

**v1 per class** (test): alfalfa 0.83, corn 0.93, grassland/pasture 0.91, soybeans 0.93. Most alfalfa errors are grassland (44 of 282), which is expected for two perennial covers.

**How early in the season the crop is known** (v1, accuracy with steps 1..k only):

| Steps known | 4 | 6 | 7 | 8 | 9 | 10 | 12 | 16 |
|---|---|---|---|---|---|---|---|---|
| Ends about | 24 May | 20 Jun | 3 Jul | 17 Jul | 30 Jul | 12 Aug | 8 Sep | 31 Oct |
| 4 classes | 0.62 | 0.69 | 0.76 | 0.82 | 0.86 | 0.88 | 0.89 | 0.90 |
| Corn vs soybeans | 0.61 | 0.69 | 0.83 | **0.91** | 0.94 | 0.96 | 0.95 | 0.96 |

**By mid-July, corn and soybeans are told apart nine times in ten.** That is the M1 promise of "the current season before USDA publishes" (the CDL appears in winter).

**The rotation guess, checked.** The Iowa archive fields carry CDL 2025, and 07's table carries CDL 2024:
- **after corn in 2024:** soybeans in 2025 in 70.2% (285 fields);
- **after soybeans:** corn in 94.5% (164 fields).

The sample is class-balanced, so these are not Iowa-wide rates. Still, the demo's "opposite of last year" guess is right for soybean fields and wrong for about three corn fields in ten, because continuous corn is common.

## 4. HLS greenness for 2021–2025 (16)

**Source.** NASA HLS v2.0: S30 is Sentinel-2 and L30 is Landsat 8/9, both harmonised to 30 m on the MGRS tiles. Microsoft Planetary Computer hosts it in West Europe and gives an anonymous token, so no key is needed.
- The Sentinel-2 COGs on AWS us-west-2 were the first choice, but they came at about 250 KB/s in total from here; ~25 GB would have taken a day.
- HLS reads at about 80 scenes a minute.
- HLS starts there in 2020.

**Indices:**
- NDVI = (NIR − red) / (NIR + red);
- NDWI = (NIR − SWIR1) / (NIR + SWIR1), as in the archive;
- S30 bands B04 / B8A / B11, L30 bands B04 / B05 / B06.

**Valid pixels.** A pixel counts when Fmask shows no cirrus, cloud, cloud-adjacent, shadow, snow or water, and aerosol is not high. A field takes the median of its valid pixels in the 3×3 window at its centroid if it is at least 10 acres and has at least 5 valid pixels; a 5–10 acre field takes its centroid pixel.

**Steps.** 16 equal steps from 1 April to 31 October; the median of the valid observations in each step, gaps filled linearly and carried flat at the ends.

**Sample.** Whole ~20 × 20 km squares, one per county:
- **24 squares** with corn after corn and corn after soybeans both in USDM drought seasons in 2021 and/or 2023 (07), mostly in north-east and north-central Iowa;
- **8 squares** never in drought in those years;
- a bonus for squares holding M1-archive fields.

That gives **50,209 fields** of at least 5 acres in 11 tiles, 62 of them in the M1 archive.

**The build.** The rest of the scene-level values are cloud.

| Year | Scenes (S30) | Field-scenes | Valid | Fields in the tensor | Median observed steps |
|---|---|---|---|---|---|
| 2021 (drought) | 588 (417) | 2,212,063 | 65.9% | 50,209 | 13 |
| 2023 (drought) | 710 (419) | 2,734,554 | 64.0% | 50,207 | 14 |
| 2024 | 775 (460) | 2,890,050 | 69.3% | 50,207 | 15 |
| 2025 | 708 (453) | 2,568,376 | 62.4% | 50,205 | 14 |

Output in `greenness/` (419 MB): per-scene field values and one 16-step tensor per year.

**Check against the M1 archive.** The 62 shared Iowa fields, 2025, per-step correlation averaged over the 16 steps:

| Archive | Index | Lag −1 step | **Lag 0** | Lag +1 step | Pooled r at lag 0 | Bias (HLS − archive) |
|---|---|---|---|---|---|---|
| v1 | NDVI | 0.63 | **0.91** | 0.62 | 0.984 | −0.004 |
| v1 | NDWI | 0.70 | **0.93** | 0.68 | 0.985 | −0.007 |
| v2 | NDVI | 0.43 | 0.46 | 0.39 | 0.903 | −0.020 |
| v2 | NDWI | 0.46 | 0.49 | 0.41 | 0.885 | −0.017 |

What this shows:
- **This build reproduces v1 almost exactly** (pooled r 0.98, bias under 0.01), and the best match is at lag 0.
- So the archive's undocumented grid is the same 16 equal steps from 1 April, and it was very likely built from HLS too.
- **v2 matches at no lag,** which confirms it is broken.
- HLS tensors from this script can go straight into an M1 model trained on v1.

**The M1 reference classifier on other years.** It was trained on the 2025 archive v1 (NDVI and NDWI only) and scored on this HLS build with CDL as truth:

| Year | Fields | 4 classes | Corn vs soybeans |
|---|---|---|---|
| 2021 | 49,232 | 0.851 | 0.860 |
| 2023 | 49,556 | 0.880 | 0.900 |
| 2024 | 49,126 | 0.889 | 0.905 |
| 2025 (62 archive fields) | 62 | 0.935 | – |

- **A classifier trained on one season carries to other seasons** with a few points' loss, and is weakest in the drought year 2021.
- Retraining it on several years of HLS would close most of the gap.

## 5. M2: continuous corn in drought (17)

**The question.** Did corn after corn lose more greenness than corn after soybeans in the 2021 and 2023 droughts? The comparison is between neighbours under the same weather.

**Design.**
- **Field-years:** corn and soybean fields of the HLS sample, 2021–2024. Arms come from CSB/CDL (07).
- **Drought** is the field's USDM season flag: D2+ in at least 4 Jul–Aug maps.
- **Model:** outcome = square × year effects + monoculture + monoculture × drought + log area. Standard errors are clustered by square (32), with a square-level bootstrap (499 draws) and a placebo (drought shuffled across square-years, 200 draws).
- **Outcomes:**
  - peak NDVI (late June – early September);
  - NDWI in July–August (canopy water);
  - late NDVI (late August – late September);
  - the season's NDVI area.
- Fields that never reached NDVI 0.5 are dropped as CDL or centroid misses: 0.1% of corn.

**Sample** (field-years, 2021–2024):

| | Drought, after corn | Drought, rotated | Normal, after corn | Normal, rotated |
|---|---|---|---|---|
| Corn | 11,877 | 15,184 | 22,105 | 27,741 |
| Soybeans | 473 | 16,346 | 876 | 29,151 |

### First: the drought barely shows in greenness

The plain drought effect, with square and year effects and both arms together:

| Outcome | Corn | Soybeans |
|---|---|---|
| Peak NDVI | **−0.0057** (se 0.0021) = −0.20 SD | **−0.0098** (se 0.0029) = −0.25 SD |
| NDWI Jul–Aug | −0.012 (se 0.007) | −0.003 (se 0.008) |
| Late NDVI | +0.006 (se 0.012) | −0.008 (se 0.009) |
| NDVI area | −0.70 (se 0.71) | −1.02 (se 0.65) |

- **The 2021 and 2023 droughts in north-east and central Iowa were mild for the crops.** Corn yield against each county's linear trend, 1990–2025 (01's panel):

  | | 2021 | 2023 |
  |---|---|---|
  | All Iowa counties | 1.02 | 0.995 |
  | The 24 drought squares' counties | 1.00 | 0.95 |
- **Peak NDVI** sees them, but only by 0.006 for corn: the canopy saturates near 0.89.
- **Translation to yield:**
  - over 100 county-years, county mean peak NDVI of corn tracks the NASS county yield with r = 0.56 (0.40 against the yield anomaly);
  - the slope is ~700 bu/ac per 1.0 NDVI, so −0.0057 is roughly −4 bu/ac;
  - this is a cross-sectional slope and only a rough guide.

### Then: does the rotation change the drought effect?

| Corn, 2021–2024 | Normal-year gap, after corn vs after soybeans | Extra in drought (monoculture × drought) | Bootstrap 95% CI | Placebo p |
|---|---|---|---|---|
| Peak NDVI | +0.0008 (se 0.0005) | **+0.0010** (se 0.0009) | −0.0006 … +0.0027 | 0.31 |
| NDWI Jul–Aug | −0.0024 (se 0.0015) | +0.0041 (se 0.0027) | −0.0012 … +0.0098 | 0.10 |
| Late NDVI | +0.0008 (se 0.0048) | +0.0125 (se 0.0063) | +0.0006 … +0.0253 | 0.04 |
| NDVI area | **−0.57** (se 0.16) | +0.35 (se 0.26) | – | – |

**What the corn rows say:**
- **There is no sign that continuous corn suffered more in these droughts.** The peak-NDVI interaction is +0.001 with a CI from −0.0006 to +0.0027. In yield terms that is about −0.4 to +1.9 bu/ac, i.e. a difference of at most a couple of bushels, centred on zero.
- **Late NDVI leans the other way.** In drought, rotated corn browned earlier than continuous corn:

  | Late NDVI | After corn | After soybeans |
  |---|---|---|
  | Drought | 0.715 | 0.682 |
  | Normal | 0.753 | 0.740 |

  - The result is borderline (placebo p 0.04). It drops to t = 1.5 once each year gets its own monoculture effect.
  - Earlier browning can mean earlier maturity as well as stress, so it is not evidence that monoculture helps.
- **Other drought measures agree on direction and size.** With the number of D2+ weeks or SMAP root-zone dryness as the exposure, the interactions are positive and tiny: peak NDVI +0.0002 per week, +0.0020 per unit of SMAP dryness.
- **In normal years continuous corn has a smaller NDVI area** (−0.57, t −3.6), which fits a slightly later green-up after corn residue.

| Soybeans, 2021–2024 | Normal-year gap, after soybeans vs after corn | Extra in drought | Bootstrap 95% CI | Placebo p |
|---|---|---|---|---|
| Peak NDVI | **−0.028** (se 0.005) | +0.005 (se 0.006) | −0.010 … +0.016 | 0.62 |
| NDWI Jul–Aug | **−0.061** (se 0.008) | +0.016 (se 0.012) | −0.008 … +0.037 | 0.22 |
| NDVI area | **−3.0** (se 0.5) | +1.2 (se 0.8) | – | – |

Means:

| | Soybeans after corn | Soybeans after soybeans |
|---|---|---|
| Peak NDVI | 0.910 | 0.878 |
| NDWI | 0.348 | 0.267 |

- **The clear result is soybeans after soybeans.** They are less green in every year (−0.03 peak NDVI, −0.06 to −0.08 NDWI), which is the known soybean rotation effect (disease, cyst nematode).
- **The penalty does not grow in drought,** but continuous soybeans are rare (473 drought field-years), so the drought interaction is imprecise.

**Robustness.** The same model on 2021–2025, with the 2025 crop taken from the M1 classifier (confidence ≥ 0.9), changes nothing for corn: peak NDVI +0.0014 (se 0.0009). For soybeans: −0.007 (se 0.006).

### In bushels: an NDVI → yield proxy (19)

NASS reports yield per county only, so the proxy is fitted on counties and applied to fields.

**Sample and crops.**
- In each of the 99 counties, the 7.68 km HLS block with the most corn and soybean fields: 21,464 fields, 2020–2025.
- 7,660 scenes in all, 63–69% of field-scenes valid.
- Crops are CDL for 2020–2024; for 2025, the M1 classifier's confident calls.

**Features and target.**
- Features, per county, year and crop, as medians over the county's fields: peak NDVI, late NDVI, NDWI in July–August and the NDVI area.
- Target: the NASS county yield over the county's own trend.
- Scored leaving one year out.

| | Corn | Soybeans |
|---|---|---|
| County-years | 510 | 478 |
| Across years (full curve) vs trend, RMSE bu/ac | 17.99 vs 17.18 | 5.58 vs 5.30 |
| Within a year (4 summaries) vs the year's mean, RMSE bu/ac | 14.53 vs 14.46 | **3.79 vs 4.14** |
| Within-year r by year, 2020–2025 | 0.05, 0.15, −0.21, 0.33, 0.46, 0.12 | **0.58, 0.20, 0.28, 0.58, 0.55, 0.14** |

What the table shows:
- **Across years, greenness never beats the trend.** Six years are too few to learn year-to-year differences.
- **Within a year, greenness ranks soybean counties** (median r 0.42, 8% lower error) **but not corn counties** (median r 0.13, no gain).
- Corn's canopy saturates, and in 2020 the derecho flattened corn that stayed green.
- **So the proxy is usable for soybeans only.**

**M2 arm gaps in bushels** (2021–2024; square × year effects, clustered by square, bootstrap CI):

| | Field-years | Normal-year gap, monoculture vs rotated | Extra in drought | Bootstrap 95% CI |
|---|---|---|---|---|
| **Soybeans after soybeans** | 37,765 | **−3.8 bu/ac** (se 0.8) | +1.2 (se 0.9) | −0.4 … +3.0 |
| Corn after corn (proxy without skill, for completeness) | 69,605 | −0.6 (se 0.2) | +0.3 (se 0.3) | −0.3 … +0.9 |

- **Continuous soybeans lose about 3.8 bu/ac a year** against soybeans after corn. That is roughly 6–7% of an Iowa soybean yield, the size the agronomic literature reports for second-year soybeans.
- The drought interaction is not significant.
- For corn, the bushel numbers carry no information beyond section 5, because the proxy has no skill. ECOSTRESS (section 7) is the next attempt for corn.

**Reading for Sivozmina (m10 v0):**
- **The data does not support "continuous corn is a drought risk" for droughts of 2021/2023 strength in Iowa.** m10 for that contrast should say "no measurable difference (± ~2 bu/ac)", not a penalty.
- **The soybean rotation effect is large and stable.** It belongs in the strategy cards as evidence every year, not only in droughts.
- **The limits:**
  - 2021 and 2023 were mild droughts for corn; a 2012-type drought is not in the HLS years (from 2020);
  - greenness is not yield;
  - the arms differ in ways the design cannot see (management, planting date, hybrid);
  - 32 squares, mostly north-east Iowa.

## 6. M3 checked on fields

The green-up date is the date a field reaches half of its season's NDVI amplitude. It is compared with:
- M3's modelled 50% planting date for the field's POWER cell (10);
- NASS district 50% planted dates (median green-up of the district's sample fields).

| | Square-years | r(green-up, M3 planting) | Median lag | District-years | r(green-up, NASS planting) | r(M3, NASS) on the same | Median lag |
|---|---|---|---|---|---|---|---|
| Corn | 128 | −0.00 | 41 days | 24 | 0.07 | −0.12 | 44 days |
| Soybeans | 128 | 0.35 | 44 days | 24 | **0.61** | 0.52 | 48 days |

- **Soybeans.** Satellite green-up follows the NASS planting dates (r = 0.61), slightly better than M3's model on the same district-years (0.52). It can serve as the "M1 observed green-up" check that the proposal plans for M3.
- **Corn.** Neither green-up nor the model tracks NASS across these four years. Corn planting moved little between 2021 and 2025, so there is little to track, as in 10's test.
- **The lags fit agronomy:** half green-up comes 6–7 weeks after planting.

## 7. ECOSTRESS evaporative stress (18)

**Why.** Peak NDVI barely sees mild droughts and saturates for corn. ECOSTRESS measures canopy temperature, so its evaporative stress index (ESI = actual / potential ET) falls while the crop is still green.

**What was ordered** (NASA AppEEARS, with the team's Earthdata account):
- ECO_L4T_ESI.002 (ESI and cloud mask) and ECO_L3T_JET.002 (daily ET), 70 m;
- July–August of 2020, 2021, 2023, 2024 and 2025, cut to the 32 sample squares.

**How it had to be split.** A single request was ~40 times over AppEEARS' size limit, which counts the extent of all polygons. So it went in as 55 requests, one per MGRS tile and year.

`18_ecostress.py fetch` waits for the requests, downloads them in parallel and writes:
- per-field values for every overpass (`greenness/ecostress_obs.parquet`);
- July–August means per field and year (`greenness/ecostress_field_year.parquet`).

**Coverage is partial.** AppEEARS serves its files from AWS us-west-2, which delivered about 25 KB/s per connection from here. After ~10 hours, 3,750 of 8,698 files were in:
- ESI and cloud **complete for 2020, 2021 and 2023**, the two drought seasons included;
- 2024 on 7 of 11 tiles, so few never-drought squares;
- no 2025;
- daily ET only for part of 2020, so ET is left out.

The analysis README says how to resume.

**What was read.**
- 4,076,192 field-overpasses on 115 dates, 80.9% clear.
- 183,253 field-years with July–August values, a median of 10 clear ESI values each.
- A field-year enters the models with at least 2 clear values.

Corn field-years with ESI:

| | Drought squares | Never-drought squares |
|---|---|---|
| 2021 | 19,543 | 7,383 |
| 2023 | 19,531 | 7,401 |
| 2024 | 13,305 | 1,370 |

The median July–August ESI hardly moves between years: 0.532 in 2020, 0.526 in 2021, 0.536 in 2023, 0.534 in 2024.

**Does ESI see the drought?** No. The plain drought effect, with square and year effects:
- corn: +0.004 (se 0.012), +0.07 SD;
- soybeans: +0.007 (se 0.011).

Across 91 corn county-years, county mean ESI correlates with the NASS county yield at r = −0.36 (−0.36 against the yield anomaly). That is the wrong sign for a stress index. In this sample the PT-JPL ESI tracks something other than crop water stress, plausibly north–south gradients in temperature and cloud.

**M2 on ESI** (2021–2024, same model as section 5):

| | Normal-year gap, monoculture vs rotated | Extra in drought | Bootstrap 95% CI | Placebo p |
|---|---|---|---|---|
| Corn after corn | −0.0002 (se 0.0008) | **+0.0002** (se 0.0010) | −0.0018 … +0.0020 | 0.80 |
| Soybeans after soybeans | +0.0122 (se 0.0040) | **−0.0124** (se 0.0047) | −0.0221 … −0.0042 | 0.005 |

- **Corn: nothing.** That agrees with the NDVI result: no sign that continuous corn suffered more in 2021/2023.
- **Soybeans after soybeans look relatively more stressed in drought.**
  - The interaction also holds with the number of D2+ weeks (t = −2.8) and with SMAP dryness (t = −2.1).
  - It weakens to t = −1.7 once each year has its own monoculture effect.
- **Do not read the soybean result as proof:**
  - ESI does not register the drought itself;
  - its county relation with yield has the wrong sign;
  - continuous soybeans are only 473 drought field-years.
  - It is a lead for the next round, not evidence for the strategy cards.

**Verdict for M2.** ECOSTRESS confirms the NDVI reading for corn and adds nothing for its yield. **The PT-JPL ESI is not a usable stress outcome for Iowa row crops** in these mild-drought seasons.

## 8. What's next

1. **Tell the archive's builder that v2 is broken,** and use v1 for M1 training until a fixed version exists.
2. **Retrain the M1 classifier on HLS 2021–2025** from this build, with CDL labels for 2021–2024. A one-season model already gives 0.86–0.91 on corn vs soybeans across years.
3. **M2 next steps:**
   - **Severe-drought evidence.** 2012 in Landsat: HLS does not go back that far, but Landsat Collection 2 on Planetary Computer does. Also the 2020 western-Iowa drought: HLS and ECOSTRESS 2020 are already in hand.
   - **A yield outcome that works for corn.** Neither peak NDVI nor ESI does. Options:
     - the RMA cause-of-loss county data now on `main` (`data/additional_sources/data/rma_col_county_year.parquet`), as a county check of drought damage;
     - the dis-ALEXI ESI variant (ECO_L4T_ESI_ALEXI.002), which is built from the thermal signal more directly.
   - **Management controls:** planting date from green-up, and tile drainage via the SSURGO drainage class.
4. **Strategy cards:**
   - show the soybean rotation effect as measured evidence: about −3.8 bu/ac a year;
   - show the continuous-corn drought effect as "not detected in 2021/2023 (±2 bu/ac), with greenness and with ECOSTRESS".
