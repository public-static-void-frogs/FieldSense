# Supplied dataset availability review

Reviewed on 2026-10-29 against the [core and source-data contract](core-and-source-data-contract.md). “Available” means verified in the supplied local files, not already imported into the application. The [audit evidence](dataset-review-evidence.json) records schemas, counts, coverage, and join checks.

## Result

We have a substantial source identity/location/area dataset and an eight-year annual crop-class history. We do **not** yet have actual field polygons, a confirmed current crop assignment for the 2026 demo season, soil profiles, recorded field operations, or agronomic scheduling reference data. None of the supplied files contains the application's generated strategies or forecasts.

The supplied weather extracts were inspected, but remain outside the required dataset contract: weather is planned as a live API integration queried by position and time. Their presence does not change that decision.

## Contract coverage

| Requirement                           | Status                          | Verified available                                                                             | Remaining work or missing information                                                                                                                        |
| ------------------------------------- | ------------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Field/land identity, location, area   | **Available source attributes** | `CSBID`, centroids, area, state/county attributes; 15,973,095 matching records in each archive | Map source identities to canonical field GUIDs and select the intended operational fields                                                                    |
| Actual field polygons                 | **Missing**                     | Estimated rectangles and centroids only                                                        | Obtain original polygon/multipolygon geometry; preserve CRS and convert to the application's GeoJSON format                                                  |
| Current crop/season assignment        | **Partial**                     | Annual majority land-cover/crop codes through 2025                                             | Explicitly use a 2025 baseline, or obtain a confirmed assignment for the desired later season; annual classification does not supply an actual planting date |
| Crop catalog/reference information    | **Partial**                     | Source class codes and a supplied Python label lookup                                          | Complete the code mapping, handle non-crop/double-crop classes, and add the reference constraints/windows required by the core                               |
| Soil/site characteristics             | **Missing soil data**           | Position, area, administrative context                                                         | No soil profile dataset. Regional drought classes and grid elevation are not field soil measurements                                                         |
| Field observations over time          | **Partial contextual input**    | Weekly drought classification linked to `CSBID`, covering 1,250,000 fields                     | No measured field-condition series or ready crop-health assessment. Preserve drought's regional/centroid interpretation                                      |
| Historical crop seasons               | **Partial**                     | Eight annual class assignments for 2018–2025                                                   | Transform annual codes into linked historical classifications; do not invent planting/harvest dates, yields, or recorded practices                           |
| Historical field events               | **Missing**                     | No dated operations/event log                                                                  | Actual inspections, applications, irrigation passes, planting/harvest events, or another documented work-history source                                      |
| Regional/seasonal planning references | **Missing**                     | Geographic context and annual labels                                                           | Crop/region-specific windows and constraints needed to produce dated recommendations                                                                         |
| Core-generated results                | **Not supplied**                | Inputs for future processing                                                                   | Assessments, rotation recommendations, dated operations, strategy forecasts/comparisons, explanations, and contingencies still need core logic               |
| Analytical summaries                  | **Derivable subset**            | Area by source crop class; historical class sequences; drought summaries                       | Implement typed joins/aggregation; these calculations do not establish agronomic recommendations                                                             |

## File inventory and inspected coverage

All Parquet files inside both archives were inspected. All standalone Parquet rows were scanned for the reported structural checks, including the 65-million-row drought table. The supplied Python file was read and its literal lookup dictionary parsed; its top-level code was **not executed**.

| Supplied file                             | Verified contents                                                                                 | Coverage / key                                                                                  |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `attrs.7z`                                | 64 Parquet partitions, **15,973,095 records**, 15,973,095 unique `CSBID`s; no geometry column     | Source attributes across 48 state-FIPS prefixes; `CDL2018`–`CDL2025`                            |
| `csb_bounds.zip`                          | 64 Parquet partitions, **15,973,095 records**, 15,973,095 unique `CSBID`s; no geometry column     | Centroid, area and estimated rectangle bounds; same identity set as `attrs.7z`                  |
| `boone_drought.parquet`                   | **65,000,000 rows**, 1,250,000 distinct fields, 52 weeks; no duplicate `(CSBID, valid_date)` keys | 2025-01-07 through 2025-12-30; each week has 1,250,000 fields                                   |
| `field_cell_map.parquet`                  | **1,500,000 unique field mappings** to 10,026 cells; no duplicate `CSBID` keys                    | Supplied mapping is for the IMERG grid                                                          |
| `cells.parquet`                           | **10,026 unique IMERG cells** with centers and grid indices                                       | Reported `n_fields` sums to 1,500,000                                                           |
| `imerg_daily.parquet`                     | **2,737,098 rows**, 10,026 cells × 273 dates; no duplicate cell/day keys                          | 2025-01-01 through 2025-09-30; historical precipitation context, outside required dataset scope |
| `weather_daily.parquet`                   | **162,790 rows**, 446 cells × 365 dates; no duplicate cell/day keys                               | 2025-01-01 through 2025-12-31; historical POWER extract, outside required dataset scope         |
| `pts_weather.parquet`                     | **2,190 rows**, six fields × 365 dates; no duplicate field/day keys; all six share one POWER cell | Same 2025 coverage; an example point extract, not coverage of the whole field catalog           |
| `read_batch_with_crops.py`                | A CDL-code/name dictionary and a helper that adds annual crop-name columns                        | Useful starting lookup; not a full crop catalog or planning algorithm                           |
| `csb_columns.md`, `csb_bounds_columns.md` | Descriptions of source attributes and estimated rectangles                                        | Useful metadata; actual schemas differ from some stated types and county-code formatting        |
| `drought_columns.md`                      | Drought-class, centroid assignment, null and estimated-release semantics                          | Important interpretation limits; not evidence of field-level soil measurements                  |
| `imerg_columns.md`, `power_columns.md`    | Gridded historical weather definitions and join conventions                                       | Metadata for optional supplied extracts; not additions to the dataset contract                  |

No supplied archive contains the missing original geometry, and no supplied file contains a `units.json` sidecar for POWER.

## Important findings for ingestion

### 1. Estimated bounds do not satisfy the polygon requirement

Every partition in `csb_bounds.zip` has the same non-geometric schema. It contains `min_lon`, `min_lat`, `max_lon`, and `max_lat`, but those values describe the estimated area-based rectangles explained in the accompanying notes. They are not a retained vertex sequence for the original field boundary. The attributes archive also has no geometry column.

It is possible to draw a rectangle from these columns, but it must be labelled approximate. It cannot be marked as an available real field polygon or used as a substitute for exact field-area spatial aggregation. The next source delivery needs the original geometry linked by `CSBID`.

### 2. The two field archives join cleanly

The complete identity sets match one to one: zero attribute IDs are missing from bounds and zero bounds IDs are missing from attributes. A second pass confirmed identical raw ID sequences in all 64 corresponding partitions; all IDs are 15 characters long. All 1,500,000 IMERG mapping IDs and all 1,250,000 drought field IDs resolve to this larger catalog.

`CSBID` is an external identity whose encoding includes the edition/year window. Preserve it, the dataset name, and edition as source identity metadata, and map them to internal GUIDs. Do not assume the same identifier survives a new source edition or that a source crop-sequence polygon is automatically the application's final management unit.

### 3. Crop history is available, but its meaning is limited

All eight annual code columns are present and non-null across the attributes archive. They describe annual majority classes, not recorded planting/harvest operations or a proposed future rotation. There is no 2026 crop column.

The observed code set contains **21 codes not covered by the supplied lookup**:

```text
0, 92, 112, 210, 211, 212, 215, 230, 231, 232, 233, 235,
242, 243, 244, 245, 246, 247, 248, 249, 250
```

Retain these as unresolved source classes until the catalog is completed. Do not turn an unknown code into an assumed crop. The source also contains non-crop and double-crop classes that need an explicit eligibility/mapping policy.

The 2025 columns include 3,003,844 records with code `1`, 2,413,777 with code `5`, and 937,484 with code `24`, so the three crops used by the demo have substantial source coverage under the supplied lookup. The six point-weather examples are a different case: all six have 2025 class `152` (`Shrubland` in that lookup). They should not automatically become corn/soybean/wheat demo fields.

The lookup alone does not provide rotation suitability rules, planting windows, expected outcomes, or crop physiology/reference parameters.

### 4. Drought is useful regional context, not a field-condition measurement

Despite its filename, `boone_drought.parquet` contains fields across **43 state-FIPS prefixes**, not just Boone County. The attributes archive includes **5,253** records selected by state `19` and county component `015` for a Boone County, Iowa source subset; that selection must still be checked against the chosen supplemental-data coverage.

The drought table has 29,202,285 null `dm` values. Its supplied notes say null can mean either no drought category or outside coverage; it is not equivalent to class `0`. Class `0` is represented separately in the actual file. Preserve this ambiguity until a coverage mask/flag is available.

All `release_date_est` values are exactly two days after `valid_date`. This verifies the arithmetic only; it does not verify actual publication times. Keep validity time separate from estimated availability when using the data as a model baseline or for historical evaluation.

These regional classes can be linked as contextual observations. They do not establish soil-profile properties, measured crop condition, or the application's interpreted health score.

### 5. Supplemental datasets cover different field subsets and grids

The supplied IMERG mapping resolves completely to the supplied cell metadata and daily series. Its intersection with the drought subset is **1,000,000 fields**. Both subsets resolve to the large attributes/bounds catalog, but neither covers the entire catalog.

The six point-weather IDs resolve to attributes and drought, but **none is in the supplied IMERG field mapping**. Their shared POWER cell is present in `weather_daily.parquet`.

The POWER cell IDs and supplied IMERG mapping cell IDs have **zero matching strings**. They represent different grids and cannot be joined using the shared column name alone. The supplied `field_cell_map.parquet` and `cells.parquet` should not be treated as POWER side tables. A general POWER field-to-cell association would need its own verified mapping or spatial adapter.

Do not eagerly expand shared cell observations into a copy for every field. Keep provider/grid identities and shared observations separate, and join only the selected field/time subset when needed. This remains optional historical context; the live weather API plan is unchanged.

### 6. Metadata needs a small cleanup before normalization

- The actual area columns are fractional `double` values, not the integer area type described in some notes. Preserve precision before converting to hectares.
- County components are three characters long throughout both archives, for example `059`, alongside a separate two-digit state. Do not assume that `CNTYFIPS` alone is already the five-digit combined county code described by the notes; preserve leading zeros and construct/validate the combined key deliberately.
- Actual drought `dm` storage is nullable `double`, not the documented nullable `Int8`. Its observed non-null categories are integral 0–4; an adapter can validate and convert them.
- Parquet timestamps are timezone-naive. The POWER notes also leave the time standard dependent on extraction options. Do not infer an observation time zone or a provider's publication time from these files alone.
- The POWER notes make `units.json` authoritative, but that sidecar was not supplied. Reconcile units and extraction metadata before any scientific conversion or combination.
- Structural completeness does not certify scientific accuracy. For example, IMERG quality/error estimates require product-specific interpretation; they should not be discarded merely because every cell/day key is present.

## What can be built from the available data

After selecting a target subset and adding source-to-GUID/crop mappings, engineers can populate source identities, centroids, area, annual class history, crop-area aggregates, and linked drought context. These would be real supplied-source views rather than newly invented mock observations.

A truthful operational field map still needs the original polygons. Current-season crop details need a declared supported baseline or a newer assignment. Soil-dependent assessments and date-specific agronomic recommendations still need their corresponding datasets/reference inputs and core logic.

The files do not provide the desired rotation plans, scheduled future work, strategy projections, calibrated confidence, or causal explanations. Those remain application-core outputs to implement. Annual crop histories and drought labels are evidence for that work, not substitutes for its results.
