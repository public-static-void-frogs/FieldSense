# SoilGrids (ISRIC): column descriptions

Source: https://soilgrids.org ; FAQ https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs.html ; layer dictionary and conversion factors https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html
Basis: `sources-descriptions.md` §21.

**Read this first**
- **Static**, model-based predictions of soil properties at 250 m. Not a time series and not a field sample.
- Distribution: GeoTIFF tiles with VRT/overviews and WCS. A point JSON service exists, but its availability was not tested.
- Six depth intervals (cm): 0–5, 5–15, 15–30, 30–60, 60–100, 100–200.
- Files are integer-coded: divide by the factor below to get conventional units.
- File name pattern `property_depth_statistic`, for example `clay_5-15cm_mean.vrt`.

## 1. Logical table `SoilPrediction`

| Column | Type | Description |
|---|---|---|
| `location` | coordinates | Point of the prediction. |
| `property` | enum | Property code (section 2). |
| `depth_top_cm`, `depth_bottom_cm` | int | Depth interval. |
| `statistic` | enum | `mean`, `Q05`, `Q50`, `Q95`, or `uncertainty`. |
| `raw_value` | int? | Stored integer. |
| `value` | float? | After conversion. |
| `units` | string | Conventional unit. |
| `release` | string | SoilGrids release. |

## 2. Properties and conversions

| Property | Meaning | Unit after conversion | Raw → value |
|---|---|---|---|
| `bdod` | Bulk density of the fine earth fraction | kg/dm³ | / 100 |
| `cec` | Cation exchange capacity | cmol(c)/kg | / 10 |
| `cfvo` | Coarse fragments (volumetric) | vol % | / 10 |
| `clay`, `sand`, `silt` | Particle-size fractions | mass % | / 10 |
| `nitrogen` | Total nitrogen | g/kg | / 100 |
| `soc` | Soil organic carbon | g/kg | / 10 |
| `phh2o` | pH in water | pH | / 10 |
| `ocd` | Organic carbon density | kg/m³ | / 10 |
| `ocs` | Organic carbon stock (integrated over an interval) | kg/m² | / 10 (from t/ha) |
| `wv0010`, `wv0033`, `wv1500` | Volumetric water content at 10, 33, 1500 kPa suction | water vol % | / 10 |

Note: the source text lists `wv003`; the expected layers are the 10, 33 and 1500 kPa water-retention layers. Check the exact layer names in the dictionary.

## 3. Notes
- `ocs` is a stock for the whole integrated interval; do not assume all six layers exist for it.
- Water-retention layers are different suction levels, not a time series.
- Mean and quantile layers describe model uncertainty, not measurement error.
