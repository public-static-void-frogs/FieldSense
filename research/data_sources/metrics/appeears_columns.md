# AppEEARS point-sample output: column descriptions

Source: https://appeears.earthdatacloud.nasa.gov/ ; tutorials https://github.com/nasa/AppEEARS-Data-Resources ; example CSV https://nasa-openscapes.github.io/earthdata-cloud-cookbook/external/appeears_csv_cloud_access.html
Basis: `sources-descriptions.md` (AppEEARS section). Related script: `appeears_download.py`.

**Read this first**
- AppEEARS is a **subsetting/extraction service**, not an independent data source. Columns depend on the request, product version and quality decoding.
- Point requests give CSV time series with quality descriptions; area requests give GeoTIFF/NetCDF.
- Not every NASA product is supported by AppEEARS, and the list changes.
- Check the export's metadata so a scale factor is not applied twice (AppEEARS CSV values are already scaled).
- **Unverified:** the exact file names and column headers produced by your own requests. Confirm on the first real download.

## 1. Example point-CSV columns (MOD11A1.061 as the illustration)

| Column | Type | Description |
|---|---|---|
| `ID` | string | Your point ID. |
| `Latitude`, `Longitude` | float | Point coordinates. |
| `Date` | string | Observation date. |
| `MODIS_Tile` | string? | MODIS tile of the sample. |
| `MOD11A1_061_Line_Y_1km` | int? | Row in the tile. |
| `MOD11A1_061_Sample_X_1km` | int? | Column in the tile. |
| `MOD11A1_061_LST_Day_1km` | number? | Daytime land surface temperature (already scaled; K). |
| `MOD11A1_061_QC_Day` | int? | Quality bits. |
| `MOD11A1_061_QC_Day_MODLAND_Description` | string? | Decoded text of the QC bits. |

Pattern for other layers: `<PRODUCT>_<VERSION>_<LAYER>` plus, for quality layers, one extra decoded description column per bit field.

## 2. Logical table `PointSample`

| Column | Type | Description |
|---|---|---|
| `point_id` | string | `ID`. |
| `location` | coordinates | `Longitude`, `Latitude`. |
| `date` | date | `Date`. |
| `product_id`, `product_version` | string | From the column prefix. |
| `layer` | string | Layer name. |
| `value` | float? | Sampled value. |
| `quality_code` | int? | QC integer. |
| `quality_description` | string? | Decoded QC text. |
