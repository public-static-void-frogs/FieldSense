# MODIS MCD12Q1 annual land cover: column descriptions

Source: LP DAAC / Earthdata Search `MCD12Q1`; guide https://www.earthdata.nasa.gov/s3fs-public/2025-04/MCD12_User_Guide_V6.pdf
Basis: `sources-descriptions.md` §20.

**Read this first**
- Annual land cover, 500 m, sinusoidal tiles (typical 2400 × 2400), HDF4/HDF-EOS, from 2001. Collection 6/6.1.
- Several **classification schemes**, not one global code list. Each scheme needs its own legend.
- Class `14` (IGBP: Cropland/Natural Vegetation Mosaic) is mixed land cover, **not** 100 % cropland.
- `255` is fill in the listed layers.
- `LC_Prop*_Assessment` is the confidence of the matching `LC_Prop*` layer, **not** of `LC_Type1`.

## 1. Native layers `[y,x]`, uint8

| Layer | Description |
|---|---|
| `LC_Type1` | IGBP classes, 1–17 (`12` = Croplands, `14` = Cropland/Natural Vegetation Mosaics). |
| `LC_Type2` | UMD scheme. |
| `LC_Type3` | LAI scheme. |
| `LC_Type4` | BGC scheme. |
| `LC_Type5` | Plant functional types. |
| `LC_Prop1` | LCCS land cover. |
| `LC_Prop2` | LCCS land use. |
| `LC_Prop3` | LCCS surface hydrology. |
| `LC_Prop1_Assessment`, `LC_Prop2_Assessment`, `LC_Prop3_Assessment` | Assessment of the matching `LC_Prop*` layer, 0–100. |
| `QC` | Quality control. |
| `LW` | Land/water mask: 1 = water, 2 = land. |

## 2. Logical table `LandCoverPixel`

| Column | Type | Description |
|---|---|---|
| `year` | int | Product year. |
| `tile_id` | string | Sinusoidal tile. |
| `row`, `col` | int | Pixel indices. |
| `classification_scheme` | string | Which `LC_*` layer the code comes from. |
| `class_code` | int | Class code for that scheme. |
| `assessment_percent` | float? | Assessment of the `LC_Prop*` layer, if applicable. |
| `quality` | int? | `QC` value. |
