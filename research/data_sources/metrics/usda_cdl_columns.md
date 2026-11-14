# USDA Cropland Data Layer (CDL / CropScape): column descriptions

Source: https://nassgeodata.gmu.edu/CropScape/ ; CroplandCROS https://croplandcros.scinet.usda.gov/ ; downloads https://www.nass.usda.gov/Research_and_Science/Cropland/Release/
Basis: `sources-descriptions.md` §17. Related scripts: `cdl_fields.py`; CDL codes also appear in the CSB dataset (`csb_columns.md`).

**Read this first**
- Annual **categorical raster** (GeoTIFF) of crop type; **no field boundaries**, owner IDs or yields.
- Historically 30 m; for 2024–2025 both 10 m and resampled 30 m are available. Full CONUS coverage from 2008; earlier years cover only some states.
- Resample categorical maps with nearest/mode, never bilinear.
- Confidence, cultivated and crop-frequency layers are **separate assets**, not extra bands.

## 1. Native raster

| Item | Type | Description |
|---|---|---|
| `class_code` | uint8, one band | Crop/land-cover class code for the pixel. `0` = background. |
| `geotransform` | float[6] | Pixel size and origin. |
| `projection` | string | CONUS: usually NAD83 Albers. |

## 2. Logical tables

`CropClassPixel`: `year` (int), `resolution_m` (float), `row`, `col` (int), `crop_code` (int).
`CropLegend`: `crop_code` (int), `crop_name` (string), `color_rgb` (int[3]?).

## 3. Example codes (full dictionary is wider and release-dependent)

| Code | Name | Code | Name |
|---|---|---|---|
| 0 | Background | 21 | Barley |
| 1 | Corn | 22 | Durum Wheat |
| 2 | Cotton | 23 | Spring Wheat |
| 3 | Rice | 24 | Winter Wheat |
| 4 | Sorghum | 26 | Double Crop Winter Wheat/Soybeans |
| 5 | Soybeans | 31 | Canola |

## 4. Notes
- Classification accuracy varies by crop and year; the CDL is a satellite classification, not a ground survey.
- Metadata catalog: https://data.nass.usda.gov/Research_and_Science/Cropland/metadata/meta.php
