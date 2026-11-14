# Rotation rule engine

Standalone Python package for the Field Shift question: *"I want to plant X on this field — what
are my alternatives, and what are the risks of my current rotation?"* No web framework; the
backend (or a notebook) calls `build_advisor(...).advise(field, intended_crop, priorities, units)`.

```sh
python -m pip install -r rule_engine/requirements.txt       # PyYAML, duckdb
python -m unittest discover -s rule_engine/tests -t .        # from the repo root
ruff check rule_engine && ruff format --check rule_engine
```

## Input and output

`field` is a dict with `id`, `crop` (declared crop name), `area` (ha), `sourceId` (15-digit CSBID
or None), `countyFips`, `sourceYear` and optionally `sourceProperties` (CSB attributes; `CDL<year>`
keys give the satellite crop history). `priorities` ⊂ `water | soil | erosion | income |
pest_break`; `units` is `metric` or `imperial`.

`latitude` and `longitude` (decimal degrees) locate the field in the long weather record. Without
them the centroid of the field's season summary is used. `field["stageCalendar"]` may give local
stage dates, `{crop_id: {"stages": {"planted": day_of_year}, "source": "..."}}`: a stage the
regional calendar has is moved to the local day, the stages that follow it (`emerged` after
`planted`) move by the same number of days, and `calendar.localShiftDays` reports the shift.

Two optional blocks feed the soil, tillage, cover-crop and herbicide rules. Without them those
rules stay silent and the result lists `soil_not_provided` / `practices_not_provided`:

- `field["soil"]`: `slope_pct`, `drainage_class` (SSURGO wording, e.g. `Poorly drained`),
  `aws_100cm_mm`, `sand_pct`, `ph`, `caco3_pct`, `nirr_class` (land capability class), `hel`
  (bool, NRCS determination). `rule_engine.ssurgo.fetch_soil(lat, lon)` returns this block from
  USDA Soil Data Access; the values are SSURGO map-unit estimates, not a soil test, and a
  farmer's soil test should overwrite `ph`.
- `field["practices"]` (farmer-declared, for the coming season):
  - `tillage`: `conventional | reduced | strip_till | no_till`.
  - `tile_drained`: bool. SSURGO gives the natural drainage class, so wet-soil rules are
    switched off on tiled fields.
  - `cover_crop`: the cover seeded after last season's crop and growing ahead of the candidate
    (`rye | winter_wheat | triticale | oats | clover | radish | none`), and
    `cover_termination_days` (days between killing it and planting).
  - `herbicides`: list of `{active, month, season}`; `month` is the application month (default
    6) and `season` how many seasons ago (default 1). Actives are those in
    `data/herbicide_plantback.csv`.
  - `weed_escapes`: bool, weeds survived last season's programme.

Keys may be snake_case or camelCase (`tileDrained`); keys with digits are safest in snake_case.

The result is a plain, purely structured dict (camelCase keys, no prose). The wording for the
farmer is left to the consumer, such as an LLM agent:

- `historySource`: {kind `cdl | declared | none`, seasons, firstYear, lastYear,
  `satelliteEstimate`}, plus `history[]` and `seasonsAvailable[]`.
- `candidates[]`, ranked (lower `score` is better). Each one has:
  - `scoreBreakdown[]`: the points per rule and the `income_rank` entry; the points sum to `score`.
  - `economicsAvailable`.
  - `risks[]`, `benefits[]` and `advisories[]`, as findings.
  - `calendar` {kind `nass_region | crop_default | group_default`, stages, localShiftDays,
    localSource}.
  - `soil[]` and `yield` {low, mid, high, unit, method, inputs, factorsApplied[]}.
  - `revenue`: gross only.
  - `dataGaps[]` and `needsLocalReview`.
- A finding has `ruleId`, `category`, `kind`, `level`, `points`, `yieldFactor`,
  `evidenceStrength`, `unverifiedTraits[]` and `trigger`:
  - `{type: conditions, conditions: [{fact, op, expected, actual}]}`; or
  - `{type: hazard, stage, window {startDoy, endDoy, startDate, endDate}, metric, metricUnit,
    aggregate, compare, threshold, seasonsHit, seasonsTotal, share, worstYear, worstValue,
    levelCapped, perSeason[], record}`. `record` is `weather_record` when the seasons counted
    are those of the long weather record and `field_seasons` when they are the field's own
    summaries.
- `dataGaps[]` at both levels are `{code, ...params}`. The codes are `no_csb_id`,
  `no_season_summary`, `no_weather_record`, `few_weather_seasons`, `short_history`, `hazards_not_evaluated`,
  `hazard_stage_not_in_calendar`, `calendar_not_nass`, `rule_uses_unverified_traits`,
  `no_yield_estimate`, `yield_unverified`, `no_price`, `price_unverified`,
  `price_not_local`,
  `field_area_unknown`, `price_unit_unconvertible`, `soil_not_provided` and
  `practices_not_provided` (each with the `facts[]` that rules wanted) and
  `herbicide_plantback_unknown` (`actives[]` with no label interval for that candidate).
- `weatherRecord`: {source, seasons, firstYear, lastYear, nodeLatitude, nodeLongitude,
  distanceKm}, or null when no record is configured or no grid node is within 30 km.
- `offSeason`: the slot between the previous crop's harvest and the next planting. See
  "The off-season slot" below.
- `scoring`: the weights, the priority multiplier, the income bonus and the tie-break order,
  so the ranking can be explained without hard-coding.
- Soil indicators carry `basis` (`crop_trait | cdl_history | smap_rootzone | soil_team`),
  `threshold`, `verified` and `inputs`.

## Layout

| Piece | Path |
| --- | --- |
| Crop catalog (groups, traits, CDL codes) | `data/crops.yaml` |
| Rules (YAML, one file per theme; format in `data/rules/README.md`) | `data/rules/*.yaml` |
| Stage calendar, prices, reference yields | `data/*.csv` |
| Season summaries (weekly bins per field) | built by `scripts/build_season_summary.py` |
| Modules | `catalog`, `rules`, `reference`, `summary`, `facts`, `yield_model`, `soil`, `engine` |

Rules are evaluated per candidate crop: `applies_to` (crop, group or trait selector), then `when`
conditions over facts (`candidate.*`, `history.*`, `county.*`, `field.*`) or a `hazard` block
evaluated season by season. Trait precedence is crop > group.

## The long weather record

A hazard rule counts in how many seasons its threshold was crossed, so it needs many seasons.
There are two sources:

- **Weather record** (`ClimateRecordStore`): weekly gridMET statistics for the whole year on a
  0.25 degree grid over the contiguous USA, 1996-2025. The engine reads the node nearest to the
  field, so it works for any field, not only for fields with season summaries. Every hazard
  whose metric is in the record (temperature, precipitation, reference evapotranspiration) is
  counted over these seasons.
- **Field season summaries** (`SeasonSummaryStore`): the few seasons assembled per field. They
  are still the only source for root-zone soil moisture (SMAP) and the Drought Monitor class.

A hazard that was hit in fewer than 1 season in 10 is not reported (`MIN_HAZARD_SHARE`).

```sh
bash data/usa_sample/download_gridmet.sh data/local/usa_sample/cache/gridmet 1996 2025
python rule_engine/scripts/build_climate_record.py \
  --cache data/local/usa_sample/cache/gridmet --out data/local/usa_sample/climate_record \
  --years 1996 2025
advisor = build_advisor(summary_root=..., climate_root="data/local/usa_sample/climate_record")
```

The download is about 12 GB (4 files per year); the record itself is about 0.5 GB. gridMET
starts in 1979, so the record can be made longer the same way. The node is a 4 km cell up to
about 20 km from the field: good for temperature, rougher for a single heavy rain.

## The off-season slot

The ranking answers "which crop next season". `offSeason` answers the rest of the year: after
the crop now in the field is harvested, is there enough autumn left for a cover crop or a
fall-sown crop? It is a separate block and does not change scores or ranks.

- The slot opens at the previous crop's median harvest day in the stage calendar plus 7 days
  for seeding. The previous crop is the latest known year of the history. There is no slot
  after a perennial stand.
- Each option is tested in every season of the weather record. `seasonsMet / seasonsTotal` is
  the share of past autumns in which its criterion held: `reliable` from 0.8, `marginal` from
  0.5, else `unlikely`. At least 10 seasons are required.
- `status` is `ok`, or the reason there are no options: `previous_crop_unknown`,
  `no_harvest_in_calendar`, `no_weather_record` or `weather_record_too_short`.

| Option | Criterion | Source |
| --- | --- | --- |
| Cereal rye cover crop | 130 degree days (base 0 C) from seeding to the year's end | Ontario winter wheat emergence guidance, used for rye as a winter cereal. Needs local review |
| Oat cover crop, winter-killed | 40 days from seeding to the first freeze of -2 C | SARE, Managing Cover Crops Profitably |
| Winter wheat for harvest | 400 degree days (base 0 C) from seeding to the year's end | Virginia Tech SPES-431, citing Oakes et al. 2016. Needs local review |

Winter wheat is offered only where it is a candidate crop in the state. The options are in
`offseason.py:OPTIONS`. Radish, clover and other covers are not there because no sourced
establishment threshold was found for them. The check covers autumn heat only: it does not
check soil water at seeding, winter survival or spring termination.

## Building the season summaries

```sh
python rule_engine/scripts/build_season_summary.py \
  --source data/local/field_daily_2025_ext/2025 --out data/local/season_summary/2025
advisor = build_advisor(summary_root="data/local/season_summary")
```

Fields are matched by CSBID (`sourceId`) and `countyFips`. Fields without a CSBID are still
assessed on the declared crop, with the missing context listed in `dataGaps`.

## Extension points

- `YieldModel.predict(crop, seasons, reference, region)`: swap `CountyTrendYieldModel` for the ML
  county yield regression.
- `SoilHealthProvider.indicators(field, candidate, history, seasons)`: the soil team's provider
  replaces `DerivedSoilIndicators`; `kind: soil_team` marks their values.
- Crop-level `calendar: {source, stages}` in `crops.yaml` overrides the group default, as for
  winter wheat and rye, which are sown in the fall so planting falls outside the Apr-Oct window.
- New region: add rows to the CSV tables and `regions` to crops in `crops.yaml`.

## Regions

The region is resolved per field: the state from `stateFips`, else from the first two digits
of `countyFips` (`regions.py`). The result carries it as `region`. `build_advisor(region="IA")`
only sets the fallback for a field without a state or in a state with no candidate crops; that
fallback adds the gap `region_not_supported`.

| Table | Built by | Content |
| --- | --- | --- |
| `data/state_crops.csv` | `data/usa_sample/state_crops.py` | Candidate crops per state: catalog crops with at least 0.5 % of the state's CSB acres, 2021-2025 |
| `data/state_stage_calendar.csv` | `scripts/fetch_state_reference.py` | Median day each stage crossed 50 % in NASS Crop Progress, per state and crop |
| `data/state_reference_yields.csv` | same | State yield range (min, mean, max since 2021) |
| `data/state_prices.csv` | same | Latest marketing-year price received per state |

The curated Iowa files are read first and win where both have a row. A state price replaces
the default quote only when the default was observed in another state; the candidate then has
no `price_not_local` gap. A national quote is kept and the gap names where it was observed
(`observedIn`). Where NASS publishes no crop progress for a state and crop, the calendar falls
back to the crop or group default (`calendar_not_nass`), which was written for Iowa.

`data/usa_sample/` builds a 10,000-field sample over 48 states to check all of this.

## Honest limits

- Without the long weather record, hazards are counted over the field's own seasons (five in
  the USA sample), and a timed hazard is capped at `medium` until at least 3 are available.
- The weather record is past weather, not a forecast, and it has no trend correction: recent
  decades are warmer than the 1990s.
- Stage dates are regional medians. Only the local sowing date can be passed in; flowering and
  maturity stay regional.
- Corn and soybean yields are county-level. Oats and hay use the Iowa state range from NASS
  (min, mean, max of the last five years). Winter wheat yield is an unverified placeholder,
  and spring wheat, rye and sorghum have no Iowa yield, so no revenue.
- Prices: RMA 2026 projected for corn and soybeans; NASS marketing-year prices received for
  the rest, Iowa where published and national otherwise (`priceLevel`, `price_not_local`
  gap). Refresh with `python rule_engine/scripts/fetch_nass_reference.py` (needs
  `USDA_DATA_KEY`); the full series since 2015 is in `data/nass_reference_history.csv`.
  No cost estimates by design.
- Under the `income` priority, a candidate without a revenue estimate (hay, pasture, crops
  without a price) gets 0 income points, not a penalty. `economicsAvailable: false` marks it,
  and it loses ties.
- CDL/CSB crop labels are satellite estimates, not farmer-declared ground truth.
- Outside Iowa: 30 % of sampled fields get an Iowa-based default calendar; cotton, rice,
  peanuts, durum, sugarbeets and potatoes are not in the catalog, so their history years are
  unknown; rule thresholds were written for the Corn Belt and have not been reviewed elsewhere.
- With no priorities the score is agronomic risk only, so hay or pasture ranks first on every
  sampled field. Use the `income` priority, or read the rank among cash crops.
- Soil, tillage, cover-crop and herbicide rules only fire on declared inputs; nothing is
  inferred from satellite data. Slope, water-storage and sand cut-offs are design thresholds
  (evidence `weak`). Tillage C factors come from Missouri plots, and herbicide plant-back
  intervals are label maxima compiled by UW-Madison Extension (2024): the product label governs.
  Sorghum, other hay and pasture have no plant-back column and are reported as unknown.
- Double-crop winter wheat / soybeans is a ranked candidate but has no yield or price, and
  carries a fixed high risk for Iowa (ISU trials).
