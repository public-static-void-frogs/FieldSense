# `field_dataset` and the 2025 daily panels: data builds, M2/M3 inputs, water ledger and m11

Scripts behind sections 8–11 of [`research/data_sources/fields/field_dataset.md`](../../../research/data_sources/fields/field_dataset.md)
(01–04), behind [`research/data_sources/fields/field_daily_2025_followup.md`](../../../research/data_sources/fields/field_daily_2025_followup.md) (05–14)
and behind [`research/data_sources/fields/greenness_m1_m2.md`](../../../research/data_sources/fields/greenness_m1_m2.md) (15–17).
They turn the delivered tables into normalised data, refill and check every input against public sources, and build
the first versions of the M2 study units, the M3 windows, the water metrics m6/m7/m9 and the m11 baseline.

## Requirements

- Python 3.10+ with `duckdb`, `pandas`, `numpy`, `scipy`, `scikit-learn`, `pyarrow`, `certifi`, `pyproj`, `shapely`,
  `pyshp`, `openpyxl`, `py7zr`, and `rasterio` for 12 (all from pip; rasterio 1.5.2 wheels bundle GDAL).
- The unpacked archives: `field_dataset/year=YYYY/part.parquet` and the 2025 daily panel (`2025/*.parquet` from
  `field_daily_2025_enriched.zip`). Keep them, the caches and all outputs **outside the repo**; the team copy lives in
  `Field-Shift-NASA-data/` next to the repo, described in its own `README.md`.
- Network for 02, 03, 06–10, 12 and 16 (NASA POWER, USDM, CropScape, gridMET, NRCS Soil Data Access, Iowa Environmental
  Mesonet, Crop-CASMA, Microsoft Planetary Computer; no keys). Every response is cached, so reruns are offline.
- LightGBM is not used: on macOS it needs `brew install libomp`. scikit-learn's `HistGradientBoostingRegressor` stands in.

## Run order

```bash
FD=/path/to/field_dataset          # unpacked field_dataset.7z
P=/path/to/2025                    # unpacked field_daily_2025_enriched.zip
D=/path/to/Field-Shift-NASA-data   # anywhere outside the repo

python 01_county_panel.py     --dataset $FD --out $D/m11/county_panel.csv
python 02_backfill_power.py   --dataset $FD --cache $D/raw/power_seasons --out $D/m11/power_seasons.csv
python 03_backfill_context.py --dataset $FD --cache $D/raw/ctx --out $D/m11/county_context.csv
python 04_m11_baseline.py     --dataset $FD --panel $D/m11/county_panel.csv --power $D/m11/power_seasons.csv \
                              --context $D/m11/county_context.csv --out $D/m11/results
python 05_normalise_daily.py  --daily $P --out $D/field_daily_2025
python 06_power_daily.py      --tables $D/field_daily_2025 --cache $D/raw/power_daily \
                              --gridmet-cache $D/raw/gridmet_et0 --out $D/power/power_daily.parquet
python 07_usdm_field_drought.py --dataset $FD --daily $P --cache $D/raw/usdm_weekly --out $D
python 08_reference.py        --cache $D/raw/reference --out $D/reference
python 09_insitu_soil.py      --tables $D/field_daily_2025 --power $D/power/power_daily.parquet \
                              --cache $D/raw/isusm --out $D/insitu
python 10_m3_windows.py       --tables $D/field_daily_2025 --power $D/power/power_daily.parquet \
                              --reference $D/reference --cache $D/raw/coop --out $D/m3
python 11_water_ledger.py     --tables $D/field_daily_2025 --power $D/power/power_daily.parquet --reference $D/reference \
                              --m3 $D/m3 --insitu $D/insitu --panel $D/m11/county_panel.csv --out $D/water
python 12_smap_backfill.py    --daily $P --cache $D/raw/cropcasma_smap9km --out $D/smap/smap_cropcasma_cellday_2015_2026.parquet
python 13_m11_soil.py         --dataset $FD --panel $D/m11/county_panel.csv --power $D/m11/power_seasons.csv \
                              --context $D/m11/county_context.csv --power-daily $D/power/power_daily.parquet \
                              --water $D/water --m3 $D/m3 --tables $D/field_daily_2025 --out $D/m11/results
python 14_season_card_export.py --data $D --out $D/demo/season_card_2025.json
python 15_m1_greenness_check.py --data $D --out $D/m1          # needs src/greenness_2025_v1, _v2 (unpacked dataset*.zip)
python 16_hls_greenness.py      --data $D --years 2025 2021 2023 2024
python 17_m2_drought_effect.py  --data $D --out $D/m2/effect
EARTHDATA_USERNAME=... EARTHDATA_PASSWORD=... python 18_ecostress.py submit --data $D --token-file /private/path/token.json
python 18_ecostress.py fetch  --data $D --token-file /private/path/token.json   # waits for AppEEARS, downloads, extracts
python 19_ndvi_yield.py        --data $D --out $D/m2/effect
```

Run every script with `python -I` when the inputs are downloaded archives (13 adds its own folder to `sys.path` to
reuse 04's functions).

| Script | What it does | Main output |
|---|---|---|
| `01_county_panel.py` | Collapses 43.6 M field rows to county × year × crop: target and lags, area-weighted weather and April drought, neighbour shares from the `field_*` flags (2019–2025) | `county_panel.csv`, 6,887 rows |
| `02_backfill_power.py` | One POWER daily request per cell (68 cells, 1989-01-01 … 2025-09-30), recomputes the eight May–Sep features. **Stops if the recomputed 2018–2024 seasons differ from the dataset** | `power_seasons.csv`, 2,516 cell-seasons |
| `03_backfill_context.py` | USDM April drought per county (from 2000) and CDL corn/soy acreage per county (2000–2024) | `county_context.csv`, 2,574 county-years |
| `04_m11_baseline.py` | Trend + lags + weather + drought + shares ablations, leave-one-year-out and forward CV, ridge and gradient boosting, permutation importance, leakage demo. The slow step | `results/*.csv` |
| `05_normalise_daily.py` | Splits a daily panel into fields, county yields, POWER / IMERG / SMAP cell-days and each field's USDM maps; SMAP gets °C and mm/day columns. **Stops unless the panel rebuilt from the tables equals the input in every column of every row** | `field_daily_2025/`, 40 MB instead of 1.2 GB |
| `06_power_daily.py` | POWER daily 1981-01-01 … 2026-09-30 for the 68 cells with soil wetness, soil temperature, snow; FAO-56 ET0; wetness percentiles against 1991–2020. Checks: equals the panel's POWER columns, against SMAP L4 2025, ET0 against gridMET | `power/power_daily.parquet`, 1.14 M cell-days |
| `07_usdm_field_drought.py` | All 418 weekly USDM maps 2018–2025 at every field centroid; M2 drought seasons and treatment arms. **Stops unless it reproduces the 2025 panel's drought** (it flags the panel's missing 2025-06-10 map) | `usdm/`, `m2/` |
| `08_reference.py` | NASS Iowa weekly progress by district since 1974 (via IEM), county → district, county soils from SSURGO (available water to 25–150 cm, CSR2, drainage) | `reference/` |
| `09_insitu_soil.py` | ISU Soil Moisture Network (29 stations): soil temperature and water content against SMAP L4 and POWER | `insitu/` |
| `10_m3_windows.py` | M3: workable days, planting progress, silking and maturity, frost, heat at silking per POWER cell 1981–2026, fitted on NASS and scored on 2016–2025 with earlier years only; frost and heat against 117 NWS COOP stations | `m3/` |
| `11_water_ledger.py` | FAO-56 daily root-zone ledger per county 1984–2026 for corn and soybeans: m6 demand, m7 water gap, m9 bare vs cereal rye; checked against SMAP, POWER, ISU stations and yields | `water/` |
| `12_smap_backfill.py` | SMAP L4 surface and root-zone moisture for the 1,891 panel cells, 31 Mar 2015 – today, from Crop-CASMA (USDA NASS / GMU, no key); pixel per cell chosen on Apr–Jul 2025, checked on Aug–Oct 2025 (r = 0.9975); percentiles recomputed on the record | `smap/`, 8.0 M cell-days |
| `13_m11_soil.py` | Soil-water features added to 04's baseline, same CV; water-gap scenario table | `m11/results/m11_soil_*.csv` |
| `14_season_card_export.py` | Data for the "Field Season 2025" demo page: 198 real fields with every layer | `demo/season_card_2025.json` |
| `15_m1_greenness_check.py` | The M1 archives (`dataset.zip`, `dataset (2).zip`): profile, v1 vs v2, rotation check on Iowa CDL 2025, reference crop classifier with early-season accuracy and Iowa held out | `m1/` |
| `16_hls_greenness.py` | NASA HLS v2.0 (S30 + L30) from Planetary Computer, no key: NDVI and NDWI for 50,209 fields in 32 ~20 km squares, 2021, 2023, 2024, 2025, as the M1 16-step tensor; checked against the M1 archive | `greenness/` |
| `18_ecostress.py` | ECOSTRESS ESI and daily ET (70 m) from NASA AppEEARS for the 32 squares, July–August 2020–2025, one request per tile and year; values at every field centroid. Needs an Earthdata login at `submit` only (token kept outside shared folders) | `raw/ecostress/`, `greenness/ecostress_*.parquet` |
| `19_ndvi_yield.py` | County NDVI → yield model on HLS 2020–2025 (one 7.68 km block per county, 21,464 fields), across and within years; the within-year model as a field yield proxy for the M2 arm gaps in bu/ac (works for soybeans, not corn) | `greenness_yield/`, `m2/effect/ndvi_yield_*`, `m2_yield_proxy_estimates.csv` |
| `17_m2_drought_effect.py` | First M2 estimate: corn after corn vs after soybeans in drought seasons, square × year effects, clustered and bootstrap CIs, placebo; M1 classifier on HLS years; M3 green-up check | `m2/effect/` |

## Things that will bite

- **POWER precipitation ×24.** A daily request that reaches GEOS-IT days returns precipitation 24 times too high for the
  whole request. 02 ends at 2025-09-30 and 06 at 2026-09-30 (the last MERRA-2 day); both assert the response has no
  GEOS-IT source. See `research/weather_climate.md`.
- **POWER `EVPTRNS` is not evapotranspiration in mm.** Divided by 2.45 MJ/kg it gives half of SMAP's ET and less than
  ET0 in every month. Use ET0 from 06 and SMAP ET instead.
- **Weather in field_dataset is the previous summer.** In the dataset, the weather of target year t is May–Sep of t−1.
  Script 04 calls these `prev_*`; `same_*` (May–Sep of t) is an oracle that a pre-season planner cannot have.
- **Early CDL is not comparable.** Iowa county CDLs hold at most 10–17 classes in 2000–2005 (30–47 in 2024), and three
  county files for 2000 are empty. Use `cdl_corn_frac` = corn / (corn + soy); shares of all agricultural land drift.
- **The label is the county yield.** Never split field rows at random: script 04's leakage demo shows why.
- **Drought in the daily panels is stale-coded.** A field keeps its last covering map; the current class is `drought_dm`
  if `drought_map_age_days <= 8`, else −1. The 2025 panels also miss the 2025-06-10 map; use 07's table instead.
- **Sentinel-2 on AWS us-west-2 is slow from here** (~250 KB/s in total); 16 reads NASA HLS from Planetary Computer's
  West Europe storage instead, at ~80 scenes a minute.
- **`dataset (2).zip` (M1 archive v2) lost the corn/soybean signal.** Use `dataset.zip` (v1); see 15.
- **The ECOSTRESS download (18) is partial.** AppEEARS files come from AWS us-west-2 at ~25 KB/s per connection from here;
  after ~10 hours 3,750 of 8,698 files were in: ESI and cloud complete for 2020, 2021 and 2023, 2024 on 7 of 11 tiles,
  no 2025, ETdaily for part of 2020 only. To finish: `18_ecostress.py fetch` again (it skips files already present; the
  requests in `raw/ecostress/tasks.json` stay downloadable for about 30 days), after `submit` to log in again if the token
  expired (`submit` does not resubmit requests already in `tasks.json`).
- **Practice drifts.** In NASS data, soybeans now reach 50% planted earlier than in 2001–2015, and corn takes
  1,584 GDD (10/30 °C) from planting to maturity in 2020–2024 against 1,448 in 2000–2004. 10 refits on recent years
  for that reason; do not reuse a 2001–2015 calibration for 2026.
