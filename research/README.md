# Field Shift research

Research for NASA Space Apps 2026, challenge "Field Shift: Adapting Farms with NASA Data". The product plan is a crop recommendation per field, based on crop history, soil, climate and a modelled soil-depletion reconstruction. Research date: 23 Oct 2026.

| File | Contents |
|---|---|
| [`GT/`](GT/README.md) | **How to get ground truth for the model.** Start here. |
| [`GT/ground_truth_by_country.md`](GT/ground_truth_by_country.md) | Open crop-history, soil, yield and futures data per country, with GT scores |
| [`GT/reconstruction_validation.md`](GT/reconstruction_validation.md) | Soil-depletion reconstruction methods, validation data and accuracy |
| [`space_apps_2026_data_sources.md`](space_apps_2026_data_sources.md) | Team data guide, corrected, with section 2E (reconstruction sources #26–56) |
| [`weather_climate.md`](weather_climate.md) | Section 2A deep-dive: weather, climate, ET0, projections and forecasts by region (#57–126), station ground truth, US validation pilot, per-country stack |
| [`soil_depletion_metrics.md`](soil_depletion_metrics.md) | Team soil metrics doc, with section 6 (what can be obtained without lab samples) |
| [`data_sources_audit.md`](data_sources_audit.md) | Audit of the team's sources: verified specs, errors found, and additional sources |
| [`crop_coefficients.md`](crop_coefficients.md) | Per-crop depletion coefficients: nutrient removal, humus balance, water, erosion, legume credits |
| [`crop_coefficients.csv`](crop_coefficients.csv) | The same coefficients as a table (24 crops) |

Tags inside the files: [V] or VERIFIED means seen in a source this session; [U] or UNVERIFIED, and †, mean check before citing.
