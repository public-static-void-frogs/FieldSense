# GRACE-FO drought indicators (NASA GRACE / UNL): column descriptions

Source: https://nasagrace.unl.edu
Basis: `sources-descriptions.md` §7. **All column names below are logical**: the homepage does not document the binary header, dtype or byte order. Read the README of the specific numeric download before parsing.

**Read this first**
- Weekly **wetness percentiles** from GRACE/GRACE-FO terrestrial water storage assimilated into a land model. Not a direct measurement of any well or field.
- Global grid 0.25°, CONUS grid 0.125°. Forecasts for 30, 60 and 90 days are separate products.
- Formats: PNG/PDF maps and numeric binary data files.
- A percentile shows relative dryness for the place and season. It has **no units** (not m³/m³, not metres of groundwater).

## 1. Logical table `DroughtWetnessIndicator`

| Column | Type | Description |
|---|---|---|
| `valid_date` | date | Date the indicator is valid for. |
| `domain` | enum | `global` (0.25°) or `CONUS` (0.125°). |
| `row`, `col` | int | Grid indices (grid definition in the download README). |
| `location` | coordinates | Cell centre. |
| `groundwater_percentile` | float? | Groundwater wetness percentile, 0–100. |
| `rootzone_percentile` | float? | Root-zone wetness percentile, 0–100. |
| `surface_percentile` | float? | Surface-soil wetness percentile, 0–100. |

## 2. Logical table `DroughtWetnessForecast`

| Column | Type | Description |
|---|---|---|
| `issued_date` | date | When the forecast was issued. |
| `forecast_period_start`, `forecast_period_end` | date? | Period the forecast covers. |
| `lead_days` | enum | 30, 60 or 90. |
| `location` | coordinates | Cell centre. |
| `groundwater_percentile`, `rootzone_percentile`, `surface_percentile` | float? | Forecast percentiles, 0–100. |

## 3. Notes
- Low percentile = dry relative to that location's climatology; compare across places with care.
- A forecast is not an observation: always keep `issued_date` and `lead_days`.
