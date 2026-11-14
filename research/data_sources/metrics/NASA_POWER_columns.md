# NASA POWER dataset: column descriptions

Produced by `csb_power_weather.py` (`weather_daily.parquet`) and `csb_power_fields.py` (per-field file).
Source: NASA POWER daily point API (`/api/temporal/daily/point`), community `AG` by default.
Docs: https://power.larc.nasa.gov/docs/services/api/temporal/daily/ , parameter dictionary: https://power.larc.nasa.gov/parameters/

**Read this first**
- One row = one **grid cell** and one **day**, not one field. POWER meteorology is a ~0.5° lat × 0.625° lon grid (solar ~1°). Every field in a cell shares the same values, so the values are not measurements at the farm.
- **Units are not fixed by this document.** The script saves the units returned by the API in `units.json`. That file is the authority, especially for radiation (units depend on `--community` and time scale).
- Missing values (API fill value, −999) are stored as NaN.
- The cell grid (centres at lat = k·0.5°, lon = −180° + k·0.625°) is an assumption from the MERRA-2 grid. Confirm it against the coordinates the API returns.

## 1. `weather_daily.parquet`: one row per cell per day

| Column | Type | Description |
|---|---|---|
| `date` | datetime64 | Calendar day. The API returns `YYYYMMDD`. Time standard is the server default unless `--time-standard utc|lst` was given. |
| `cell_id` | string | Identifier of the grid cell, `"<lat>_<lon>"` of its centre, e.g. `+41.5_-93.750`. Join key to `field_cell_map.parquet` (`CSBID` → `cell_id`) and `cells.parquet`. |
| `T2M` | float | Mean air temperature at 2 m, °C. |
| `T2M_MIN` | float | Daily minimum air temperature at 2 m, °C. Use for frost and cold-stress indicators. |
| `T2M_MAX` | float | Daily maximum air temperature at 2 m, °C. Use for heat stress. |
| `T2MDEW` | float | Dew/frost point temperature at 2 m, °C. |
| `RH2M` | float | Relative humidity at 2 m, %. |
| `QV2M` | float | Specific humidity at 2 m. Unit is given in `units.json` (commonly g/kg). |
| `PRECTOTCORR` | float | Bias-corrected total precipitation, mm/day. |
| `WS2M` | float | Wind speed at 2 m, m/s. |
| `WS10M` | float | Wind speed at 10 m, m/s. |
| `WD10M` | float | Wind direction at 10 m, degrees (meteorological convention: direction the wind comes from; confirm in the parameter dictionary). |
| `PS` | float | Surface pressure, kPa. |
| `ALLSKY_SFC_SW_DWN` | float | All-sky surface shortwave downward irradiance (incoming solar radiation). **Unit depends on community/time scale**, so read it from `units.json` (typically MJ/m²/day for `AG`). Solar parameters come from a coarser (~1°) source grid. |
| `elevation_m` | float | Elevation (m) returned by the API for the requested cell centre. It is a cell-scale value, not the elevation of any field. |

Only the parameters you pass to `fetch --parameters` are present, so your file may have fewer or more `float` columns. Up to 20 parameters per request are allowed by the API.

## 2. Side tables from `csb_power_weather.py plan`

**`field_cell_map.parquet`**: one row per field

| Column | Type | Description |
|---|---|---|
| `CSBID` | string | Crop Sequence Boundaries polygon ID. |
| `cell_id` | string | The POWER cell this field's centroid falls in. |

**`cells.parquet`**: one row per cell

| Column | Type | Description |
|---|---|---|
| `cell_id` | string | Cell identifier. |
| `cell_lon`, `cell_lat` | float | Cell centre, degrees (WGS84). This is the coordinate sent to the API. |
| `n_fields` | integer | Number of selected fields whose centroid lies in the cell. |

**`units.json`**: `{parameter: {units, longname}}` as returned by the API.

## 3. Per-field dataset from `csb_power_fields.py`: one row per field per day

| Column | Type | Description |
|---|---|---|
| `CSBID` | string | Field ID (or your `id` when `--points` is used). |
| `centroid_lon`, `centroid_lat` | float | The field's centroid (WGS84), used to find the cell. |
| `cell_id` | string | Matching POWER cell. |
| `cell_lon`, `cell_lat` | float | Centre of that cell (WGS84). |
| `date` | datetime64 | Day. |
| `T2M` … `ALLSKY_SFC_SW_DWN`, `elevation_m` | float | As in section 1. Identical for all fields in the same cell and day. |

Rows are sorted by `CSBID`, then `date`. Fields whose cell has no weather file are skipped and reported by the script.

## 4. Derived indicators (not in the data)

Growing degree days, frost-day counts and dry spells are not POWER products. Compute them from `T2M`, `T2M_MIN`, `T2M_MAX` and `PRECTOTCORR`.
