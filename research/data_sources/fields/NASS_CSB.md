# CSB 2025 edition: column descriptions

| Column | Type | Source | Description |
|---|---|---|---|
| `CSBID` | string | NASS | Polygon identifier. Chars 1–2: state FIPS. Chars 3–4: last two digits of the start year. Chars 5–6: last two digits of the end year. Last 9: sequence number. Example: `xx1825nnnnnnnnn`. |
| `CSBYEARS` | string | Observed | Year span of the edition, `1825` = 2018–2025 (start and end year, two digits each). Matches chars 3–6 of `CSBID`. Not in the official field list; constant within one edition. |
| `CSBACRES` | integer | NASS | Polygon area in acres (1 acre = 0.404686 ha). |
| `CDL2018` … `CDL2025` | integer | NASS | Majority crop in the polygon for that year's CDL, as a CDL class code (not a percentage). Examples: 1 corn, 5 soybeans, 24 winter wheat, 61 fallow/idle, 62 pasture/grass, 176 grassland/pasture. Tie handling is not documented. |
| `STATEFIPS` | string | NASS | State FIPS code (2 digits). |
| `STATEASD` | string | NASS | State FIPS plus the NASS Agricultural Statistics District (ASD). |
| `ASD` | string | NASS | NASS Agricultural Statistics District (a grouping of counties within a state). |
| `CNTY` | string | NASS | County name. |
| `CNTYFIPS` | string | NASS | County FIPS code (5 digits, includes state). |
| `INSIDE_X` | float | NASS | X "center" coordinate of the polygon. Units not stated; presumably metres in the layer's projected CRS (Albers equal-area, NAD83). |
| `INSIDE_Y` | float | NASS | Y "center" coordinate, same CRS as `INSIDE_X`. |
| `ORIG_FID` | integer | Observed | Not documented. Looks like an ID carried over from NASS processing; treat as internal. |
| `centroid_lon` | float | Script | Longitude (WGS84) of the polygon's geometric centroid. May fall outside concave polygons. |
| `centroid_lat` | float | Script | Latitude (WGS84) of the polygon's geometric centroid. |

Dropped by the script: `OBJECTID` (internal row number), `Shape_Length` (metres), `Shape_Area` (m²), and the geometry itself unless `--keep-geometry` is used.


## Notes

- Projection of the source geometry: Albers Conical Equal Area, NAD83/GRS 80, standard parallels 29.5° and 45.5°, central meridian −96°, latitude of origin 23°, metres (equivalent to EPSG:5070).
- Accuracy follows the CDL inputs (30 m raster; roughly 85–95% correct for major crop categories per the 2023 metadata).
- Other editions use other year windows (for example `CSBYEARS` = `1724`), so the `CDLyyyy` columns and `CSBID` year digits change with the edition.
