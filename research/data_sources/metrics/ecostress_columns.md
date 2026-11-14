# ECOSTRESS (ET, temperature, water stress): column descriptions

Source: https://ecostress.jpl.nasa.gov ; LP DAAC https://lpdaac.usgs.gov ; product table https://ecostress.jpl.nasa.gov/data/atbds-summary-table
Basis: `sources-descriptions.md` §9.

**Read this first**
- Measured from the ISS: **irregular, non-repeating passes** at 70 m, from 2018. Daytime/instantaneous/daily products exist.
- Format depends on the collection: swath/gridded HDF5, or tiled COG/GeoTIFF. Collection 2 and 3 differ: V3 merges MET/SM/SEB into `ETAUX`.
- The families below are **separate products**: the fields do not all sit in one file.
- Do not convert ET from W/m² to mm/day without a time and energy model.

## 1. Logical tables

`ECOSTRESSScene` (one per granule/tile)

| Column | Type | Description |
|---|---|---|
| `granule_id` | string | Granule identifier. |
| `product_id` | string | Product short name (see section 2). |
| `collection` | string | Collection/version. |
| `acquisition_time` | datetime | Overpass time. |
| `tile_id` | string? | For tiled products. |
| `footprint` | geometry | Scene/tile footprint. |
| `crs` | string | Coordinate reference system. |

`ECOSTRESSPixel`

| Column | Type | Description |
|---|---|---|
| `granule_id` | string | Parent scene. |
| `row`, `col` | int | Pixel indices. |
| `variable` | enum | Layer name. |
| `value` | float? | Physical value. |
| `units` | string | Unit. |
| `uncertainty` | float? | Layer uncertainty if provided. |
| `quality_flags` | int? | Bit flags. |

## 2. Product families

| Product | Contents | Type and unit |
|---|---|---|
| `ECO_L2T_LSTE` / L2G | Land surface temperature, emissivity, uncertainty, cloud/water/QA | float: K / dimensionless; flags integer |
| `ECO_L3T_JET` / L3G | Ensemble ET and components (PT-JPL-SM, STIC, BESS, MOD16) | float; unit and time definition from the layer |
| `ECO_L3T_ET_ALEXI` | Daily ET, uncertainty, CONUS | `ETdaily` float32 mm/day; `ETdailyUncertainty` float32 mm/day |
| `ECO_L4T_ESI` | Ratio of actual to potential ET | float, dimensionless |
| `ECO_L4T_ESI_ALEXI` | Daily stress ratio and uncertainty | `ESIdaily`, `ESIdailyUncertainty`: float32 |
| `ECO_L4T_WUE` | Water-use efficiency, GPP / ET | float; carbon/water units from metadata |

## 3. Notes
- Cloud gaps and irregular timing: do not build regular weekly series without checking acquisition times.
- Keep the QA/cloud layers; a missing pixel is not zero ET.
