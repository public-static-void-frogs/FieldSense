# SMAP L4 SPL4SMGP v8 (surface and root-zone soil moisture): column descriptions

Source: NSIDC DAAC, https://nsidc.org/data/spl4smgp/versions/8 ; product spec: https://nsidc.org/sites/default/files/documents/technical-reference/smap_l4_sm_psd_v17_for_l4sm_version_8.pdf
Basis: `sources-descriptions.md` §5 and the Earth Engine SPL4SMGP.008 band summary. Pipeline output: `csb_smap.py`.

**Read this first**
- Model output (GEOS land model) with **assimilated SMAP brightness temperatures**, not a measurement at the field. 9 km is the grid spacing.
- HDF5, 3-hourly averages (8 files per UTC day), EASE-Grid 2.0 Global (EPSG:6933), 1624 × 3856, from 2015-03-31. Arrays are `[y,x]`.
- During SMAP outages (19 Jun–23 Jul 2019, 6 Aug–20 Sep 2022) the values are model-only, without assimilation.
- NSIDC reports a geolocation issue for L4 products from 14 May to 28 Jul 2026 (reprocessing planned).
- Variables beyond surface and root-zone soil moisture are additional research products and are not validated.
- Static model constants are in `SPL4SMLM`; analysis diagnostics in `SPL4SMAU`. Neither is a field of the SMGP file.

## 1. Native variables (representative; all float32, `[y,x]`)

| Variable | Unit | Description |
|---|---|---|
| `sm_surface` | m³/m³ | Surface soil moisture, 0–5 cm. |
| `sm_rootzone` | m³/m³ | Root-zone soil moisture, 0–100 cm. |
| `sm_profile` | m³/m³ | Total soil moisture from the surface to model bedrock. |
| `sm_surface_wetness` | 0–1 | Surface wetness, dry to saturated. |
| `sm_rootzone_wetness` | 0–1 | Root-zone wetness. |
| `sm_profile_wetness` | 0–1 | Profile wetness. |
| `sm_rootzone_pctl` | % | Root-zone soil moisture percentile. |
| `sm_profile_pctl` | % | Profile soil moisture percentile. |
| `surface_temp` | K | Mean surface soil temperature (incl. snow-covered areas). |
| `soil_temp_layer1` … `layer6` | K | Soil temperature in the heat-diffusion model layers. |
| `snow_mass` | kg/m² | Snow water equivalent over the ground fraction. |
| `snow_depth` | m | Snow depth within the snow-covered fraction. |
| `land_evapotranspiration_flux` | kg/m²/s | Land evapotranspiration. |
| `overland_runoff_flux` | kg/m²/s | Overland runoff (incl. subsurface runoff). |
| `baseflow_flux` | kg/m²/s | Baseflow. |
| `snow_melt_flux`, `soil_water_infiltration_flux` | kg/m²/s | Snowmelt and infiltration. |
| `land_fraction_saturated`, `_unsaturated`, `_wilting`, `_snow_covered` | fraction | Land-area fractions by moisture/snow state. |
| `heat_flux_sensible`, `heat_flux_latent`, `heat_flux_ground` | W/m² | Heat fluxes. |
| `net_downward_shortwave_flux`, `net_downward_longwave_flux`, `radiation_shortwave_downward_flux`, `radiation_longwave_absorbed_flux` | W/m² | Radiation terms. |
| `precipitation_total_surface_flux`, `snowfall_surface_flux` | kg/m²/s | Precipitation and snowfall (the Earth Engine catalog lists a likely typo in the unit). |
| `leaf_area_index` | m²/m² | Vegetation leaf area index. |
| `vegetation_greenness_fraction` | unitless | Transpiring leaf fraction. |
| `temp_lowatmmodlay`, `specific_humidity_lowatmmodlay`, `windspeed_lowatmmodlay`, `height_lowatmmodlay` | K, mass ratio, m/s, m | Lowest atmospheric model layer state. |
| `depth_to_water_table_from_surface_in_peat`, `free_surface_water_on_peat_flux` | m, kg/m²/s | Peatland variables. |
| `mwrtm_vegopacity` | unitless | Microwave radiative-transfer vegetation opacity. |
| `sm_surface_anomaly` | not listed | Experimental anomaly of the 30-day mean `sm_surface`. |

Caution: the Earth Engine catalog metadata for `surface_pressure` looks wrong (unit given as K); check the product specification before using it.

## 2. Logical table `SoilMoistureL4`

| Column | Type | Description |
|---|---|---|
| `timestamp` | datetime | Centre time of the 3-hour average (UTC). |
| `row`, `col` | int | EASE-Grid indices. |
| `location` | coordinates | Cell centre. |
| `surface_moisture`, `rootzone_moisture`, `rootzone_percentile` | float? | `sm_surface`, `sm_rootzone`, `sm_rootzone_pctl`. |

## 3. Output of `csb_smap.py` (`smap_daily.parquet`)

| Column | Type | Description |
|---|---|---|
| `cell_id` | string | `rRRRRcCCCC` (row and column in the 1624 × 3856 grid). Join key to `field_cell_map.parquet` / `cells.parquet`. |
| `date` | datetime64 | UTC day (daily resolution). With `--resolution 3hourly` this is `timestamp` instead. |
| `n_files` | int | Number of 3-hourly files averaged (8 = complete day). Incomplete days are retried on re-run. |
| variables | float32 | Mean of the day's files for each requested variable. Fill values become NaN. |

`cells.parquet`: `cell_id`, `row`, `col`, `cell_lat`, `cell_lon`, `n_fields`. `field_cell_map.parquet`: `CSBID`, `cell_id`.

## 4. Notes
- Averaging percentiles or wetness over a day is a mean of the 3-hourly values; it is not a recomputed daily percentile.
- Fill value comes from the `_FillValue` attribute (script falls back to −9999, unverified).
