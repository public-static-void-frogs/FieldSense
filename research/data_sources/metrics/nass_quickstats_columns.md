# USDA NASS Quick Stats: column descriptions

Source: https://quickstats.nass.usda.gov/api ; bulk files https://data.nass.usda.gov/Quick_Stats/
Basis: `sources-descriptions.md` §18.

**Read this first**
- **Aggregate published statistics** (yield, acreage, price, production), not field observations. One record = one estimate for a commodity/statistic/practice/domain/geography/period.
- API needs a key. Formats: JSON `{"data":[...]}`, CSV, XML; bulk compressed files.
- All native fields are **strings**. Keep FIPS/ANSI codes as strings (leading zeros).
- `Value` can hold commas or special codes such as `(D)` (withheld). Do not parse it blindly to float.
- There are no geometries; join county/state boundaries separately.
- The natural key includes **all** dimension fields, not only county/year/crop.

## 1. Native fields (all string)

| Field | Description |
|---|---|
| `source_desc` | Program: survey or census. |
| `sector_desc`, `group_desc`, `commodity_desc`, `class_desc` | Hierarchy from sector to commodity and class. |
| `prodn_practice_desc`, `util_practice_desc` | Production and utilization practice (e.g. irrigated). |
| `statisticcat_desc` | Statistic category (yield, area planted, production, price...). |
| `unit_desc` | Unit of `Value` (e.g. BU / ACRE). |
| `short_desc` | Combined description of the series. |
| `domain_desc`, `domaincat_desc` | Domain and category within it. |
| `agg_level_desc` | National, state, county, etc. |
| `country_code`, `country_name` | Country. |
| `state_ansi`, `state_alpha`, `state_name` | State. |
| `asd_code`, `asd_desc` | Agricultural statistics district. |
| `county_ansi`, `county_code`, `county_name` | County. |
| `region_desc`, `zip_5`, `watershed_code`, `watershed_desc`, `congr_district_code` | Other geography. |
| `year` | Reference year. |
| `freq_desc` | Frequency (annual, monthly, weekly...). |
| `begin_code`, `end_code`, `reference_period_desc` | Period within the year. |
| `week_ending` | Week-ending date for weekly series. |
| `load_time` | When NASS loaded the record. |
| `Value` | The estimate (string; may be `(D)` or other special code). |
| `CV (%)` | Coefficient of variation, if published. |

## 2. Added during parsing (suggested)

| Column | Type | Description |
|---|---|---|
| `year_int` | int | `year` as integer. |
| `value_numeric` | float? | Parsed `Value` (strip commas) or null. |
| `value_status` | enum | `numeric`, `suppressed`, `unavailable`, `other`. |
| `raw_value` | string | Original `Value`. |
| `cv_percent` | float? | Parsed `CV (%)`. |
| `loaded_at` | datetime? | Parsed `load_time`. |
