# Application core outputs and dataset input contract

This report defines the information that the application needs from its agronomic core and from external datasets. The core may use models, rules, calculations, or a combination; its implementation is outside this contract.

The aim is to replace demo data with real sources while preserving field identity, spatial relationships, crop relationships, timelines, and the connections between strategies and calendar operations. Measurement choices and presentation can change as sources become available.

Weather is outside this report’s dataset requirements. It will be retrieved from live APIs using geographic position and the relevant time or time interval; no weather dataset delivery is required here.

This is an integration contract, not a claim that every proposed field is already implemented. The current HTTP shapes are defined by [`openapi.json`](../openapi.json) and [`app/schemas`](../app/schemas). The current normalized storage relationships are described in the [collection model](../app/data/README.md). Where this report recommends richer metadata or missing-data behavior, it explicitly identifies that as future work.

## Shared rules

| Concern             | Contract                                                                                                                                                                                                                    |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Field identity      | A stable UUID identifies a managed field. Keep it unchanged when its name, crop, or readings change. Related records carry `fieldId`; never infer associations from array order, names, or ID prefixes.                     |
| Land identity       | A parcel and a managed field are separate concepts. Keep the parcel/source identifier separate from `fieldId`. A source boundary can exist without an active field.                                                         |
| Crop identity       | Use `cropId` references into a crop catalog. Display names are labels, not join keys. Map source crop codes to this catalog.                                                                                                |
| Geometry            | Exchange field boundaries as GeoJSON `Polygon` or `MultiPolygon`, with closed rings and `[longitude, latitude]` coordinates in WGS84. An ingestion adapter must convert a source's different coordinate system.             |
| Dates               | Use `YYYY-MM-DD` for agricultural calendar dates. Use ISO 8601 timestamps with an offset for observations, ingestion, and generation times. Declare the field/region time zone when turning timestamps into calendar dates. |
| Seasons             | A season needs an identifier and an understood time interval. Do not assume planting and harvest occur in the same calendar year.                                                                                           |
| Measurements        | Supply typed values, a metric identifier, a unit, and observation time or interval. Distinguish absent values from zero. Definitions must make aggregation and comparison meaningful.                                       |
| Relationships       | References resolve to existing records. Historical observations and projected values remain distinct. Records are not identified by their position in a file.                                                               |
| Missing information | Report missing coverage or unsupported calculations explicitly. Do not manufacture measurements, historical seasons, confidence values, or predictions to match demo fixtures.                                              |

## Supplied-data availability

The supplied local files were reviewed on 2026-10-29. Status annotations below describe
verified on-disk coverage, not completed application integration. See the
[dataset availability review](dataset-availability-review.md) for file counts, join checks,
and limitations, and the [audit evidence](dataset-review-evidence.json) for measured results.

**Already available:** source field IDs, centroids and area for 15,973,095 matched records,
eight annual crop-class columns (2018–2025), and weekly regional drought context for a subset.
**Still missing:** original field polygons, confirmed 2026 crop assignments, soil profiles,
actual field-operation history, and planning reference inputs. Supplied weather extracts
remain outside the required dataset contract and do not change the live API plan.

## 2. Desired outputs of the application core

### 2.1 Output families

| Output                             | Information the core must deliver                                                                                                                                                     | Application use                                        | Current collection/read model                                                                                              | Supplied-file availability                                                                                           |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Field assessment                   | Field reference, assessment date, interpreted condition/score, severity or status, and an explanation of relevant evidence                                                            | Field summaries, map overlays, attention filters       | Current field summary and `field_readings`; ownership of an individual metric depends on whether it is observed or derived | Not supplied; observed annual classes and drought context are inputs, not field assessments.                         |
| Crop rotation plan                 | Field reference, current crop context, proposed future crop sequence, season/date assignments, planting windows, reasoning, and a defined confidence/quality indicator when available | Rotation summary and strategy overview                 | `rotation_plans`                                                                                                           | Not supplied; annual historical crop classes are available as inputs.                                                |
| Scheduled operations               | Identifiable actions associated with a field and plan, scheduled dates/windows, category, priority, instructions, duration or timing guidance, and rationale                          | Calendar, action detail pages, ordered strategy steps  | `planned_events`, joined with `checkpoints`                                                                                | Not supplied; no dated future work plan or historical operation log.                                                 |
| Strategy forecast                  | Dated projections for agreed metrics, associated with the field and proposed scenario, including a baseline and uncertainty information when available                                | Forecast curves and comparison with present conditions | `strategy_forecasts`                                                                                                       | Not supplied.                                                                                                        |
| Current/projected comparison       | The same metric evaluated at a defined baseline and a defined future horizon, with consistent units and scale                                                                         | Strategy comparison charts                             | `strategy_comparisons`                                                                                                     | Not supplied; no generated future scenario values.                                                                   |
| Recommendation                     | An identifiable field-level recommendation with a concise title, explanation, and actionable next step                                                                                | Field detail guidance                                  | `recommendations`                                                                                                          | Not supplied.                                                                                                        |
| Evidence and technical explanation | Which inputs or assumptions were used, their interpreted values, and how they influenced the result                                                                                   | Technical details and explanation tables               | `strategy_technicals`, plan reasons and inputs                                                                             | Not supplied for core results; source column notes provide partial input metadata.                                   |
| Conditional guidance               | A condition that would invalidate or modify a proposed operation, and the corresponding action or review step                                                                         | Strategy contingency guidance                          | `contingencies`, `plan_contingencies`, `checkpoints`                                                                       | Not supplied.                                                                                                        |
| Analytical summaries               | Time series selected from observations or calculated assessments, and aggregates such as area grouped by crop                                                                         | Overview trends and crop-area summaries                | Overview API read model; not necessarily a separately stored collection                                                    | Derivable subset: area by annual crop class, class sequences, and drought summaries; aggregation not yet integrated. |

An external reading is source data. An assessment inferred from readings is a core output. The existing mock collection name alone does not establish which it is; provenance must make that distinction clear.

### 2.2 Rotation plan

A usable plan must answer:

- Which field and baseline crop/season does the plan concern?
- What crop is proposed next, and what follows it over the supported horizon?
- When should each proposed crop be established, and what is its acceptable planting window?
- Why is the sequence appropriate, and what constraints or assumptions affect it?
- How reliable is the result, if that can be meaningfully assessed?

Crop choices must resolve to the crop catalog. Windows need explicit start/end dates; a phrase such as “next spring” is insufficient for calendar integration. A percentage is not automatically a calibrated probability: the producer must define what its quality/confidence indicator means. If none is available, expose that absence rather than invent a score.

The current API flattens the outlook into `currentCrop`, `nextCrop`, `followingCrop`, `sowingDate`, `windowEnd`, and `followingDate`, with crop-ID references for the future crops. A core can produce a more general ordered sequence; the Python adapter can select the supported horizon for these views.

### 2.3 Operations and strategy consistency

Each operation needs a UUID, `fieldId`, a date or window that can be mapped to a calendar date, a machine-readable category and priority, a title, instructions, and an explanation. The plan/scenario it belongs to must be identifiable, either by an explicit reference or an unambiguous enclosing result.

The strategy page and calendar must consume the same operations. An operation must not be independently regenerated with different dates or IDs for each screen. Preserve an operation's identity when returning the same stored result again.

Schedules must be internally consistent: preparation precedes the planting it supports, required prerequisite work precedes dependent work, and an operation's dates agree with the plan's windows. This is a semantic constraint, not a requirement to reproduce the demo's exact list of actions.

Checkpoints and conditional guidance should explain what to verify before proceeding and what would trigger a review. They may be selected from reference rules; they need not be generated prose.

### 2.4 Forecast and comparison semantics

A forecast point needs a field/scenario association, a target date, a metric identity, and a numeric projected value with a declared unit or score scale. For uncertainty bounds, declare their interpretation and ensure `lower ≤ projected ≤ upper`. A milestone/stage label is useful but must not replace the date.

A comparison needs the same metric definition for both values, the baseline date, and the future horizon. A forecast should not silently switch units, score definitions, or scenarios halfway through a series.

The current strategy DTO uses fixed metric columns, improvement intervals, and one uncertainty range. Those are chart projections of the result, not requirements that every future model must predict those exact mock variables. Different metrics can be mapped into revised chart bindings without changing field references, plan relationships, or scheduling logic.

A producer should be able to return an empty/partial forecast when it lacks support. Supporting that honestly requires the API and relevant chart cards to accept missing results; the current dense numeric DTO should not be satisfied with fabricated zeros.

### 2.5 Result traceability and incomplete results

For real integration, the recommended result envelope is:

| Metadata                                     | Purpose                                                                       |
| -------------------------------------------- | ----------------------------------------------------------------------------- |
| `runId` or `resultVersion`                   | Distinguishes one generated result from a replacement                         |
| `fieldId` and season/horizon                 | Defines the subject and time span                                             |
| `generatedAt` and baseline/as-of time        | Distinguishes production time from input observation time                     |
| Input record references or snapshot/version  | Makes the result attributable to the data actually used                       |
| Producer/version and assumptions             | Explains which model, rule set, or calculation produced it                    |
| Availability state and missing-input reasons | Distinguishes a valid empty result from an unsupported calculation or failure |

This envelope is a recommended extension, not a requirement already enforced by the current API. At minimum, engineers must preserve this information in an equivalent form so a forecast can be traced to its baseline and a plan can be regenerated coherently.

A missing forecast should not erase an otherwise valid field boundary or observation history. Produce independent output families where possible; identify the dependency that prevented the remaining output.

## 3. Dataset inputs

### 3.1 Input packages and required structure

“Required” below means required for the associated capability, not that every provider must supply every package. Sources may be combined by spatial, temporal, and crop identifiers.

| Dataset package                     | Structural information needed                                                                                                                                                | Format after ingestion                                              | Capability/dependency                                                                                  | Supplied-file availability                                                                         |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| Field/land boundaries               | Stable source identity, canonical field association where established, boundary geometry, source/version or effective date; area or enough geometry metadata to calculate it | GeoJSON features plus normalized field/parcel records               | Required to locate, select, and spatially join a field                                                 | Partial: IDs, centroids, area, estimated rectangles available; original polygons missing.          |
| Current crop/season assignment      | `fieldId`, `cropId`, season, and effective observation/planting date; distinguish known current crop from unknown classification                                             | Records linked to field and crop catalog                            | Required to interpret the field's current crop and build a crop-specific rotation                      | Partial: annual classes through 2025; no confirmed 2026 assignment or actual planting date.        |
| Crop catalog/reference information  | Stable crop identity, source codes and labels, relevant seasonal/growing context; crop relationships or constraints needed by the selected planning approach                 | `crops` records plus reference relations where needed               | Required to interpret crop IDs; agronomic reference coverage is required for supported recommendations | Partial: class codes and incomplete label lookup; agronomic constraints/windows absent.            |
| Soil/site characteristics           | Profile or observation identity, field/spatial association, typed characteristics with units; sampling/effective date and depth/interval where relevant                      | `soil_profiles` or equivalent observation records linked to a field | Needed for the property views and any core method that depends on those characteristics                | Missing soil profiles; geographic/area context available. Drought is not a soil measurement.       |
| Field observations over time        | Record identity, `fieldId` or resolvable footprint, timestamp/interval, metric identity, typed value, unit, and quality/missing-data information                             | Time-indexed observation records, currently `field_readings`        | Required for real trends, current-condition baselines, and observation-driven assessments              | Partial: weekly regional drought classes for 1,250,000 fields; no measured field-condition series. |
| Historical crop seasons             | Record identity, `fieldId`, `cropId`, season, establishment/harvest dates when known, and observed outcomes when available                                                   | `crop_seasons` records                                              | Needed for actual rotation history and recommendations that claim to account for previous crops        | Partial: 2018–2025 annual classes; no recorded planting/harvest dates or outcomes.                 |
| Historical field events             | Record identity, `fieldId`, event date/interval, activity/observation category, description, and links to associated measurements where available                            | `history_events` records                                            | Needed for the land-history timeline and evidence of past interventions                                | Missing.                                                                                           |
| Regional/seasonal reference context | Geographic applicability, crop associations, relevant season/calendar, validity period, and reference windows/constraints                                                    | Catalog/reference records with crop and region links                | Needed to turn a proposed crop into a plausible dated schedule                                         | Missing planning windows/constraints; geographic identifiers alone are available.                  |

A supplied crop classification is an input; a crop classification inferred by this application's own core is an output.

### 3.2 Field identity, crop assignment, and spatial matching

The minimum useful field package combines identity, geometry, and current crop/season context. These may arrive in separate datasets, but ingestion must resolve their relationship before exposing them as a usable field.

Do not derive identity from a field's display name or currently planted crop. Preserve external identifiers for reconciliation with later dataset versions. Decide explicitly whether a geometry update describes the same field or a new split/merged field.

Geometry must have a known coordinate system, valid rings, and meaningful geographic coverage. Multiple polygons and holes must be preserved. Derived area needs a declared unit and a calculation consistent with the geometry's coordinate system. The current UI displays hectares; providers do not have to deliver hectares if the adapter converts them.

For observations delivered as points, grids, or regional polygons rather than `fieldId` records, the integration must define how they are assigned or aggregated to the field. Record the observation footprint, temporal coverage, and aggregation method. Do not associate a reading with a field merely because both belong to the same file.

### 3.3 Measurements and property availability

Do not treat the mock's list of soil, crop, or environmental columns as a mandatory dataset specification. The essential measurement contract is:

```text
record identity
field identity or resolvable spatial coverage
metric/characteristic definition
value and unit (or an explicit missing value)
observation time or validity interval
sampling context where relevant
source and quality information
```

The core team and data team should agree on the subset required by each supported calculation. Additional attributes may be retained without forcing every source to populate them. A source that lacks a required input for one calculation can still supply boundaries, history, or observations for other capabilities.

Keep observed values distinct from inferred/derived assessments. In particular, a property in `field_readings` should carry enough provenance to establish whether it came from a sensor, survey, remote-sensing product, or local calculation.

The current property API requires many concrete values and formats some metadata for display. Real integration will require small schema/card adjustments for unavailable characteristics. That does not require changing how fields, crops, histories, and plans are linked.

### 3.4 Historical and temporal coverage

Historical records must describe events or observations that actually exist in the supplied coverage. A newly introduced field has no implied historical series. An empty history is valid; a repeated current value is not a substitute for historical observations.

Use explicit dates and units upstream. Human-readable dates, a value such as “not harvested,” or a quantity embedded in a prose string belong in an API presentation adapter, not in a dataset's numeric/date columns.

For each package, declare the earliest/latest supported time, cadence or irregular sampling behavior, and treatment of gaps. Any carry-forward, interpolation, or aggregation performed by Python must have a defined policy. The current chart projection carries the last available observation forward; that is an adapter choice to review with actual source cadence, not permission to synthesize missing history.

For crop seasons, preserve cross-year planting/harvest relationships. Future proposed operations must not be mixed into historical work records.

### 3.5 Delivery and validation

Providers may deliver CSV, Parquet, raster products, APIs, or other practical formats. They do not need to reproduce the demo directory layout. The ingestion boundary should produce normalized, typed records and GeoJSON geometry that Python can join.

A useful handoff includes representative records, a schema/data dictionary, identifier mappings, coordinate system, units, temporal/spatial coverage, missing-value conventions, provenance, and update behavior. For deltas, state how corrections and removed records are represented.

Before accepting a package, validate:

1. IDs are unique within their entity type and all supplied relationships resolve.
2. Field boundaries are usable and crop assignments refer to known crop records.
3. Observation values, units, time spans, and sampling footprints are interpretable.
4. Coverage limitations and unavailable values are explicit.
5. Historical records remain historical, while forecast and proposed-plan records remain identifiable as such.

## Integration boundary and compatibility

```text
External datasets
    → ingestion: identity mapping, unit/coordinate conversion, spatial/time alignment
    → normalized records
    → application core: assessments, plans, operations, forecasts, explanations
    → Python joins and API presentation adapters
    → field, map, strategy, history, calendar, and overview views
```

The following relationships must survive a change of source or core implementation:

- Field GUIDs join boundaries, observations, history, and generated results.
- Crop IDs join current/historical crop assignments and proposed future crops.
- Dates/windows place operations and forecasts on consistent timelines.
- One stored strategy result supplies its associated operations and forecasts consistently.
- Observed evidence can be distinguished from predictions and assumptions.

The following are adjustable integration details: the available measurement vocabulary, crop catalog contents, units at the source boundary, forecast horizon and cadence, available property cards, confidence representation, and chart metric bindings. Differences here require explicit mapping or focused API/frontend adjustments; they should not require replacing the relationship and scheduling model.

Current compatibility details to address during real integration:

| Current assumption                                                | Adapter or focused change needed                                                              |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Three crop names are enforced by the HTTP schema                  | Expand crop validation/catalog handling; retain stable `cropId` relationships                 |
| Fixed field-summary/property columns and two forecast metrics     | Map agreed signals or update the affected DTOs/cards; expose unsupported outputs honestly     |
| A two-step future rotation is flattened into named fields         | Project the chosen horizon from an ordered crop sequence                                      |
| Specific operation categories and priorities drive filters/styles | Map core categories to the supported vocabulary, or extend the shared vocabulary deliberately |
| Some dates, quantities, and technical inputs are display strings  | Keep source/core values typed; format them in Python/API adapters                             |
| A fixed demo clock and fixture date ranges                        | Supply an explicit real as-of date, season, and coverage                                      |
| Current map parcels use numeric land IDs                          | Preserve or map those identifiers separately from canonical field GUIDs                       |

Engineers should agree first on the identity, spatial, temporal, and crop relationships, then on the minimum source coverage and output families that can be supported. Mock measurement columns and mock prediction values should not determine which real datasets or core implementations are usable.
