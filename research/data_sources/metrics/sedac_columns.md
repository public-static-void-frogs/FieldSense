# NASA SEDAC (population, agricultural lands, hazards): column descriptions

Source: https://sedac.ciesin.columbia.edu (catalog of many datasets; the homepage was unavailable during the check)
Basis: `sources-descriptions.md` §25. SEDAC has **no single schema, coverage or resolution**; two verified examples are described.

## 1. GPWv4 Revision 11: population count and density

- Gridded GeoTIFF/ASCII plus metadata tables; 30 arc-seconds (about 1 km at the equator); reference years 2000, 2005, 2010, 2015, 2020.
- Count may be fractional (census population spread over the grid). Count, density and UN-adjusted series are not interchangeable.

| Column (logical) | Type | Description |
|---|---|---|
| `dataset_id`, `revision` | string | Dataset and revision. |
| `reference_year` | int | 2000 / 2005 / 2010 / 2015 / 2020. |
| `row`, `col` | int | Cell indices. |
| `population_count` | float? | Persons per cell (separate asset). |
| `population_density` | float? | Persons per km² (separate asset). |
| `land_area_km2`, `water_area_km2` | float? | Ancillary assets. |
| `adjustment` | enum | Census-consistent or UN-adjusted. |

For exposure, sum **counts** (mind overlap). Do not sum densities as people.

## 2. Global Agricultural Lands: Croplands, 2000

Historical cropland fraction, about 5 arc-minutes. Not a current crop map and not a field-scale map.

| Column (logical) | Type | Description |
|---|---|---|
| `reference_year` | int | 2000. |
| `row`, `col` | int | Cell indices. |
| `cropland_fraction` | float? | Fraction of the cell in cropland; normalize to 0–1 using the asset's unit/scale. |
| `source_dataset` | string | Dataset ID. |

## 3. Other SEDAC products
Hazards, vulnerability, demographics, water-security indicators are separate collections. For any chosen asset record: `dataset_id`, `variable`, `units`, `reference_year/period`, `resolution`, `nodata`, `version` and its codebook.
