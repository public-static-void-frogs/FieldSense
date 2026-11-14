# Ground truth for the model

How to get ground truth (GT) for each part of the Field Shift model: where open data exists, what has to be modelled, and what we can collect ourselves. Research date: 23 Oct 2026. The details and sources are in:

- [`ground_truth_by_country.md`](ground_truth_by_country.md): open crop-history, soil, yield and futures data per country, with GT scores.
- [`reconstruction_validation.md`](reconstruction_validation.md): soil-depletion reconstruction methods, validation datasets and expected accuracy.
- [`../space_apps_2026_data_sources.md`](../space_apps_2026_data_sources.md), section 2E: numbered source table with links (the `#` numbers below refer to it).

## 1. What GT each part of the model needs

| Model part | What counts as ground truth | US (best) | EU | Elsewhere |
|---|---|---|---|---|
| **Crop history** (input) | The crop grown on the field in each past year | Crop Sequence Boundaries: field polygons with 8 years of crops (#26); CDL from 2008 | Parcel registers via Fields of The World (#27): NL 2009–2026, DK 2008–2026, AT and SE 2015–2025, FR 2015–2024 | Canada AAFC 2009–2025 (#29); Argentina INTA 5 seasons; Brazil MapBiomas; Ukraine has no official open data (EU Crop Map 2022 #30, WorldCereal 2021 #31) |
| **Yield** (what "best harvest" is scored against) | Tonnes per ha for a crop, field or year | NASS Quick Stats county yields (#18); SCYM satellite yield (field R² ≈ 0.45, county ≈ 0.69) | Eurostat and national statistics (regional) | GDHY 0.5° (#32), SPAM2020 (#33), national statistics |
| **Soil baseline** (input, static) | Texture, SOC, pH and CEC at the start | SSURGO (#48) | SoilGrids (#21), LUCAS points (#51), national maps | SoilGrids, WoSIS profiles (#49), HWSD (#50) |
| **Soil change** (validates the depletion reconstruction) | Repeated measurements of SOC, P or K on the same spot | Long-term trials (KBS LTER #53); TFI soil tests by state against NuGIS balances (#36, #54) | LUCAS repeat points (#51), France RMQS (#55), Germany BZE-LW; Rothamsted e-RA (#52) in the UK | Ukraine: national humus averages only (#56) |
| **Recommendation quality** | There is no open label for "the best crop for this field" | Backtest (section 3) | Backtest | Backtest |

**Region choice:** start with the US (score 5/5). Add the Netherlands or France (4.5) as the second region. Ukraine scores 2.5, because no field-level crop history or soil data is open there.

## 2. How to get it (order of work)

Start the slow requests first: the LUCAS registration and the e-RAdata password take days.

1. **Register for LUCAS topsoil data** at ESDAC (https://esdac.jrc.ec.europa.eu/content/lucas-2022-topsoil-data). It is request-based and takes days.
2. **Get a NASS Quick Stats API key** (https://quickstats.nass.usda.gov/api). Pull county yields for corn, soybean and wheat for 2008–2025.
3. **Download CSB for one state** from the GeoParquet copy (https://source.coop/fiboa/us-usda-cropland). Choose a Corn Belt state such as Iowa, because its soil-test and yield literature is richest.
4. **Query SSURGO for the drawn polygon** through Soil Data Access (https://sdmdataaccess.nrcs.usda.gov) to get clay, SOC and pH.
5. **Get long-term experiment data for the soil carbon backtest:**
   - The Rothamsted e-RA open tier (Broadbalk, Park Grass) needs no login: https://www.era.rothamsted.ac.uk/info/RLTEdatavailable
   - The 2026 *Scientific Data* harmonized dataset covers 34 long-term experiments with 167 treatments, and gives SOC, C inputs, climate and soil. It was built for testing SOC models (https://lter.kbs.msu.edu/citations/4286). Check its licence.
6. **Get county balances for the nutrient backtest:** NuGIS (https://nugis.tfi.org/) and the TFI soil test summary (https://soiltest.tfi.org/about). TFI data are by state, not county. Some state university labs (Iowa, Wisconsin, Michigan) publish county medians; this is unverified.
7. **For the second region:** pull NL BRP or FR RPG parcels from https://source.coop/ftw/harmonized-field-data, then use LUCAS (and RMQS for France) for soil.

## 3. Validation experiments that fit in two weeks

| # | Experiment | GT used | What to report | Rigor |
|---|---|---|---|---|
| A | **Soil carbon backtest:** run RothC or ICBM using only yield-derived inputs, then compare with measured SOC change | 34-experiment dataset, Rothamsted Broadbalk, KBS surface C 1989–2001 | RMSE, and whether the ranking of rotations is recovered | High. Do this first |
| B | **County nutrient backtest:** compare the cumulative P and K balance for 2008–2017 (CDL area × NASS yield × removal coefficients) with NuGIS and with soil-test change | NuGIS, TFI (state level), state lab county summaries | Correlation and a scatter plot. Literature reaches r ≈ 0.45–0.65 at best | Medium |
| C | **Crop-history check:** compare CSB sequences with farmer-declared parcels where both exist (US: California LandIQ 2014–2024 in Fields of The World), or CDL with NASS acreage | LandIQ, NASS acreage | Share of fully correct sequences. At ~90% per year, a full 8-year sequence is right only ~0.9⁸ ≈ 43% of the time | Medium |
| D | **Recommendation backtest:** hold out the last 2–3 years; rank candidate crops with data up to the cutoff; compare with what was grown and the yield it got | CSB, county yields | Whether top-ranked crops got higher yields than the ones actually grown, on average. This is our own design, not from the literature | Low to medium |
| E | **Sanity checks:** LUCAS repeat points (EU); Ukraine national humus change compared with the modelled SOC direction | LUCAS, Ukrstat | Sign agreement | Low |

## 4. Ground truth we can make ourselves

- **Farmer soil-test upload.** An optional soil test (SOC, P, K, pH) anchors the reconstruction and narrows the ranges. Over time, these uploads become our own GT dataset of soil tests paired with crop history. This is the single biggest accuracy gain.
- **Farmer records.** Combine yield-monitor exports and the farmer's own crop list replace county yields and CDL labels for that field.
- **Crop labels for countries without registers.** Train a crop classifier on Sentinel-2 with labels from NL, DK or FR parcel registers, apply it to Ukraine or other regions, and check it against the EU Crop Map 2022 and WorldCereal reference points. This is a project on its own; outside two weeks, only do it if the region matters.
- **Rotation priors.** Count crop-to-crop transitions in CSB (e.g. corn → soybean). These give "what farmers here actually do", which acts as a plausibility check for recommendations.
- **One real field (optional).** If a team member has access to a field with a lab soil test and known history, use it as a demo case study and a single-point check.

## 5. What the GT can and cannot support

- **Supported:** crop history per field (US and much of the EU), nutrient removal per year, relative ranking of rotations with ranges, and the direction of the SOC trend.
- **Not supported without a soil test:** the field's current P, K or N level, absolute SOC, and "depleted" claims that ignore fertilizer. Fertilizer, manure, residue handling, tillage and liming are unknown for any single field.
- **Noise floor:** the smallest SOC change detectable by resampling is 6–31% of the mean. Calibrated RothC errs by 3–25%. Over 5–15 years, typical cropland SOC change is at or below the noise of a single sample.
