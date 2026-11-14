# MERRA-2 atmospheric reanalysis: column descriptions

Source: NASA GMAO MERRA-2, distributed by GES DISC. https://gmao.gsfc.nasa.gov/gmao-products/merra-2/
Basis: `sources-descriptions.md` §2 (checked 20 Oct 2026). Native variable list below is **representative**, not a full dictionary.

**Read this first**
- It is a **reanalysis** (model plus assimilated observations), not a measurement at the field.
- Format: NetCDF4, one file set per **collection** (surface, flux, radiation, atmosphere, aerosol). The variables below are spread over several collections, so they are **not** all in one file.
- Grid: 0.5° lat × 0.625° lon, 361 × 576, from 1980. Hourly, 3-hourly and monthly collections exist. Time units and calendar are in the file's `time` metadata.
- Collection examples named in the source: `M2T1NXSLV`, `M2T1NXFLX`, `M2T1NXRAD` (hourly, single level). Which variable lives in which collection is **not stated in the source**; check the collection's file specification (usual placement: temperature/humidity/wind/pressure in SLV, precipitation/evaporation in FLX, radiation in RAD).

## 1. Native dimensions

| Name | Type | Description |
|---|---|---|
| `time` | number array | Time coordinate; units and calendar from metadata. |
| `lat` | float array | Latitude, degrees north (361 values). |
| `lon` | float array | Longitude, degrees east (576 values). |
| `lev` | float array | Vertical level, only in 3D atmosphere collections. |

## 2. Representative native variables, `cube<float>[time,lat,lon]`

| Variable | Unit | Description |
|---|---|---|
| `T2M` | K | Air temperature at 2 m. |
| `T2MDEW` | K | Dew-point temperature at 2 m. |
| `QV2M` | kg/kg | Specific humidity at 2 m. |
| `U10M` | m/s | Eastward wind at 10 m. |
| `V10M` | m/s | Northward wind at 10 m. |
| `PS` | Pa | Surface pressure. |
| `PRECTOT` | kg/m²/s | Total precipitation (model). |
| `PRECTOTCORR` | kg/m²/s | Bias-corrected total precipitation. |
| `EVAP` | kg/m²/s | Evaporation. |
| `SWGDN` | W/m² | Downward shortwave flux at the surface. |
| `LWGAB` | W/m² | Absorbed longwave radiation at the surface. |

## 3. Logical table `ReanalysisValue` (suggested after import, long format)

| Column | Type | Description |
|---|---|---|
| `collection_id` | string | e.g. `M2T1NXSLV`. |
| `timestamp` | datetime | Time of the value (instant or interval, depending on the collection). |
| `location` | coordinates | Grid-cell centre (lon, lat). |
| `level` | float? | Only for 3D variables. |
| `variable` | string | Native variable name. |
| `value` | float? | Decoded value. |
| `units` | string | From the file metadata. |

## 4. Conversions and notes
- `K → °C`: subtract 273.15.
- Precipitation rate to mm/day: `× 86400`, valid only for a daily-mean rate. For other intervals use the real interval length.
- Wind speed from components: `sqrt(U10M² + V10M²)`.
- Fill values must stay missing, not zero.
- 0.5° × 0.625° is the grid spacing, not field-level accuracy.
