# ASAP (EU JRC Agricultural Production Hotspots): column descriptions

Source: https://agricultural-production-hotspots.ec.europa.eu/ (old address https://mars.jrc.ec.europa.eu/asap/) ; downloads https://agricultural-production-hotspots.ec.europa.eu/download.php
Basis: `sources-descriptions.md` §24. **Apart from `asap*_id` and `comment`, the names below are logical: the headers of all CSVs were not verified.**

**Read this first**
- Anomaly **warnings**, not yield or crop-failure probabilities.
- National hotspots are **monthly** (series from October 2016); subnational warnings are **every 10 days (dekad)** (admin1 series from the last dekad of May 2001).
- Formats: historical CSV ZIP, Shapefile boundaries, WFS/WMS, raster indicators, indicator-statistics tables. WMS returns only pictures: use CSV/WFS/raster for attributes.
- Join with the matching `gaul*_asap` boundaries, not arbitrary GAUL boundaries.
- Define the start and end days of each dekad explicitly.

## 1. `HotspotAssessment`

| Column | Type | Description |
|---|---|---|
| `asap0_id` | int/string | Country-level join key (native). |
| `assessment_date` | date | Month of the assessment. |
| `hotspot_status` | enum | Hotspot classification. |
| `comment` | string? | Documented text field; may be text or HTML depending on the export. |

## 2. `VegetationWarning`

| Column | Type | Description |
|---|---|---|
| `asap1_id`, `asap2_id` | int/string? | Admin-1 / admin-2 unit IDs. |
| `dekad_date` | date | Dekad. |
| `land_use` | enum | `crop` or `rangeland`. |
| `warning_level` | int? | Warning category. |
| `in_season` | boolean? | If decoded from the seasonal data. |

## 3. `IndicatorStatistic`

| Column | Type | Description |
|---|---|---|
| `administrative_id` | string | Unit ID. |
| `indicator` | string | e.g. FPAR, mFPARd, precipitation. |
| `dekad_date` | date | Dekad. |
| `statistic` | string | Statistic type. |
| `value` | float? | Value. |
| `units` | string | Unit. |

## 4. `ASAPBoundary`

`asap0_id`, `asap1_id?`, `asap2_id?`, `name`, `geometry`.

Field notes from the provider: https://agricultural-production-hotspots.ec.europa.eu/files/wfs_hotspots_notes.txt , https://agricultural-production-hotspots.ec.europa.eu/files/wfs_warnings_crop_notes.txt
