# USA-wide field sample for the rotation rule engine

About 10,000 fields across the 48 contiguous states with everything the rule engine reads, for
seasons 2021-2025. Built on local machines only (no cloud jobs). Outputs go to
`data/local/usa_sample/` (git-ignored, about 0.4 GB plus a 2.5 GB download cache).

What the engine uses:

- `fields.jsonl`: one engine field record per line (`stateFips`, `countyFips`, area in ha,
  `sourceProperties.CDL2018..CDL2025`, `soil` block).
- `season_summary/<year>/<county_fips>.parquet`: weekly bins per field, same schema as the Iowa
  summaries.

```python
advisor = build_advisor("data/local/usa_sample/season_summary")
```

## Build steps

Run from the repo root with the repo `.venv`. `S=data/local/usa_sample`.

| Step | Script | Source | Output |
| --- | --- | --- | --- |
| 1 Sample fields | `sample_fields.py` (reads the `fields` table of the database dump on stdin, nothing else) | CSB field table | `fields.csv` |
| 2 Crop history | `csb_cdl_extract.py` | National CSB 2018-2025 geodatabase (3.8 GB zip from USDA NASS) | `cdl_history.parquet`, `state_cdl_stats.parquet` |
| 3 Weather | `download_gridmet.sh`, `gridmet.py` | gridMET yearly netCDF (tmmx, tmmn, pr, pet) | `gridmet/<year>.parquet` |
| 4 Soil | `soil.py` | SSURGO through Soil Data Access | `soil.parquet` |
| 5 Drought | `data/us_drought_monitor/csb_drought.py weekly --points` | US Drought Monitor | `usdm/weekly.parquet` |
| 6 County yields | `data/predict_crop_yield_field_final_ds/yield_nass.py` | NASS Quick Stats (needs `USDA_DATA_KEY`) | `yields/nass_yield.parquet` |
| 7 County losses | `data/additional_sources/ext_rma.py --state all` | RMA cause of loss | `rma/*.parquet` |
| 8 Join | `assemble.py --root $S --years 2021 2022 2023 2024 2025` | steps 1-7 | `daily/`, `season_summary/`, `fields.jsonl` |
| 9 Candidate crops per state | `state_crops.py --stats $S/state_cdl_stats.parquet` | step 2 | `rule_engine/data/state_crops.csv` |
| 9a Long weather record | `download_gridmet.sh $S/cache/gridmet 1996 2025`, then `rule_engine/scripts/build_climate_record.py` | gridMET, same files as step 3 | `climate_record/` |
| 10 Check | `run_engine.py --root $S` | steps 8 and 9a | `engine_results.parquet`, `engine_rule_firing.csv` |

The sample is stratified by state: proportional to the state's field count, at least 40 fields
per state, fields of 10 acres or more, fixed random seed. Step 2 was run on a second machine
because the geodatabase holds 16 million fields; it needs about 10 GB of RAM.

## Limits

- No SMAP root-zone moisture and no EDDI: those columns are null, so the rules that read them
  report a data gap.
- Drought Monitor: `-1` means no drought category that week, `0..4` mean D0..D4.
- The season window is 1 April to early November. Stages outside it (fall sowing, harvest in
  the far south before April) cannot be checked.
- County yields cover corn and soybeans only. RMA losses cover 46 states.
- Crop history comes from CDL labels, which are satellite estimates, not farmer declarations.
  10.5 % of national CSB acre-years are crops the catalog does not have yet (cotton, rice,
  peanuts, durum, sugarbeets, potatoes, almonds, peas); those years show as unknown.
- The drought script reads CSBIDs as numbers and drops the leading zero for states with FIPS
  below 10. `assemble.py` pads the id back to 15 digits.
