# ESA WorldCover: column descriptions

Source: https://esa-worldcover.org ; data access https://esa-worldcover.org/en/data-access ; manual https://worldcover2021.esa.int/data/docs/WorldCover_PUM_V2.0.pdf
Basis: `sources-descriptions.md` §19.

**Read this first**
- Global land cover at nominal **10 m**, COG tiles of 3° × 3°, EPSG:4326.
- Two benchmark maps: **2020 (v100)** and **2021 (v200)**. This is not an annual feed. Differences between the two include algorithm changes, not only real land change.
- Classes are categorical: resample with nearest/mode.
- Only one class (code 40) is cropland; it does not say which crop.

## 1. Native `Map` raster

| Item | Type | Description |
|---|---|---|
| `Map` | uint8 | Land-cover class code (table below). |

| Code | Class | Code | Class |
|---|---|---|---|
| 10 | Tree cover | 60 | Bare / sparse vegetation |
| 20 | Shrubland | 70 | Snow and ice |
| 30 | Grassland | 80 | Permanent water bodies |
| 40 | Cropland | 90 | Herbaceous wetland |
| 50 | Built-up | 95 | Mangroves |
| | | 100 | Moss and lichen |

## 2. `InputQuality` (separate 3-band GeoTIFF, about 60 m grid)

| Band | Description |
|---|---|
| `band_1` | Number of Sentinel-1 observations used. |
| `band_2` | Number of Sentinel-2 observations used. |
| `band_3` | Percentage of Sentinel-2 observations rejected as invalid (cloud/shadow), 0–100. |

It describes the **input data**, not the probability that the class is correct. Check dtype and scale of each band in the asset.

## 3. Logical table `WorldCoverPixel`

| Column | Type | Description |
|---|---|---|
| `year` | int | 2020 or 2021. |
| `algorithm_version` | string | v100 or v200. |
| `tile_id` | string | 3° × 3° tile name. |
| `row`, `col` | int | Pixel indices. |
| `class_code` | int | `Map` value. |
| `is_cropland` | boolean | Derived: `class_code == 40`. |

## 4. Other assets
Annual composites (RGBNIR 4-band, SWIR 2-band, NDVI percentiles 3-band, GAMMA0 3-band) are imagery assets with their own tiles and resolutions; they are not class probabilities.
