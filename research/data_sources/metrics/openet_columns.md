# OpenET (field-scale evapotranspiration): column descriptions

Source: https://openetdata.org (redirects to https://etdata.org) ; API reference https://openet.gitbook.io/docs/reference/api-reference ; documentation https://etdata.org/api/api-documentation/
Basis: `sources-descriptions.md` §22. **The tables below are logical; the live JSON response was not verified.**

**Read this first**
- ET at about 30 m from satellite models, for a point or a polygon. Access: API (JSON/tabular exports, **API key needed**), raster exports, Earth Engine collections.
- Models: Ensemble, eeMETRIC, geeSEBAL, SSEBop, SIMS, DisALEXI, PTJPL. Availability depends on dataset/endpoint; do not assume "US West only".
- Do not confuse **request inputs** with output columns. The documented request contains: `date_range`, `interval`, `geometry` (`[lon, lat]`), `model`, `variable`, `reference_et`, `units`, `file_format`.
- Ensemble spread is not automatically a confidence interval.

## 1. Logical table `OpenETTimeSeries`

| Column | Type | Description |
|---|---|---|
| `location` | coordinates? | Point (when queried by point). |
| `field_id` | string? | Your own ID when you pass a polygon. |
| `geometry` | geometry? | Polygon you supplied. |
| `period_start`, `period_end` | date | Interval the value covers. |
| `interval` | string | e.g. daily or monthly. |
| `model` | string | Model name. |
| `variable` | enum | `ET`, `ETo`, `ETof`, `NDVI`, `PR`, `ET_MAD_MIN`, `ET_MAD_MAX`. |
| `value` | float? | Value. |
| `units` | string | Unit. |
| `reference_et` | string? | Reference-ET source. |

## 2. Logical table `OpenETRaster`

`product_id`, `date`, `model`, `variable`, `values` (float raster), `mask` (boolean raster, optional).

## 3. Variables
- `ET`: actual evapotranspiration for the period (mm/period for monthly).
- `ETo`: reference ET.
- `ETof`: ratio `ET / ETo`.
- `PR`: precipitation.
- `ET_MAD_MIN` / `ET_MAD_MAX`: ensemble-spread style variables; the source does not define them, so check the API documentation before use.
