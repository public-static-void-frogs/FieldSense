# NEX-GDDP-CMIP6 climate projections: column descriptions

Source: NASA NCCS, https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6 ; AWS: https://registry.opendata.aws/nex-gddp-cmip6/
Basis: `sources-descriptions.md` §3.

**Read this first**
- Downscaled **scenario projections** from CMIP6 models, not observations and not forecasts of a specific year. Scenarios have no assigned probabilities.
- Format: NetCDF4, usually **one variable × model × scenario × member × year per file**. Daily, 0.25°, about 60°S–90°N.
- Historical 1950–2014; scenarios 2015–2100. Not every model/scenario combination exists. Several releases exist (including v2): do not mix them without storing the version.
- Each file holds **one** of the variables below (the `?` in the schema means "one of"), not all nine.

## 1. Native file

| Name | Type | Unit | Description |
|---|---|---|---|
| `time` | number array | per file | Time axis. Calendar can differ between models: read it from the NetCDF. |
| `lat`, `lon` | float arrays | degrees | Grid coordinates. |
| `hurs` | `[time,lat,lon]` | % | Near-surface relative humidity. |
| `huss` | `[time,lat,lon]` | kg/kg | Near-surface specific humidity. |
| `pr` | `[time,lat,lon]` | kg/m²/s | Precipitation rate. |
| `rlds` | `[time,lat,lon]` | W/m² | Downward longwave radiation at the surface. |
| `rsds` | `[time,lat,lon]` | W/m² | Downward shortwave radiation at the surface. |
| `sfcWind` | `[time,lat,lon]` | m/s | Near-surface wind speed. |
| `tas` | `[time,lat,lon]` | K | Near-surface mean air temperature. |
| `tasmax` | `[time,lat,lon]` | K | Daily maximum near-surface air temperature. |
| `tasmin` | `[time,lat,lon]` | K | Daily minimum near-surface air temperature. |

## 2. Logical table `ClimateProjection` (long format)

| Column | Type | Description |
|---|---|---|
| `model` | string | CMIP6 model name. |
| `member` | string | Ensemble member, e.g. `r1i1p1f1`. |
| `scenario` | enum | `historical`, `ssp126`, `ssp245`, `ssp370`, `ssp585`. |
| `version` | string | Dataset release (store it; releases differ). |
| `date` | date | Day. |
| `location` | coordinates | Grid-cell centre. |
| `variable` | string | One of the variable names above. |
| `value` | float? | Value in native units. |
| `units` | string | From metadata. |

## 3. Conversions and notes
- `K → °C`: −273.15. `pr → mm/day`: × 86400.
- Ensemble quantiles and crop-suitability indices are **not** in the data; compute them yourself.
- Compare models/scenarios only for matching `version` and calendar.
