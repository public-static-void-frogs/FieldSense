# Weather integration

The backend fetches Open-Meteo model data using the signed-in account's saved
latitude, longitude, time zone, and metric/imperial preferences for unscoped requests.
An explicit `field_id` on forecast/history selects the stored field point and the caller's
saved time zone, retaining the account's unit preference. Saved crop areas use a representative
point of their boundary. Weather comes from Open-Meteo. Crop and available soil inputs come from
the selected database field. An unscoped request without account coordinates returns 422.

## API contract

FastAPI schemas in `app/schemas/weather.py` are the source of truth. Regenerate
`openapi.json` from `app.main.app.openapi()` after contract changes.

| Endpoint | Result |
| --- | --- |
| `GET /api/v1/weather/current` | Current model conditions and five upcoming daily summaries |
| `GET /api/v1/weather/forecast` | Fourteen daily forecasts starting today, oldest first |
| `GET /api/v1/weather/history?days=7` | Completed historical daily estimates, newest first; 7, 30, or 90 days |
| `GET /api/v1/weather/history?start_date=2025-07-01&end_date=2025-07-07` | Explicit historical period, up to 366 inclusive days, from 1940 through yesterday |

All endpoints require the existing session cookie. Dates in records are ISO calendar
dates in the saved time zone. `observedAt` is the validity time of current conditions,
not a station observation. `fetchedAt` is the upstream retrieval time and remains
unchanged on a cache hit. Metadata includes requested coordinates, actual grid
coordinates, units, source, time zone, soil depth, and data kind.

Forecast and history responses wrap `records` in metadata. A daily temperature is
the high; `low` is the minimum. Wind is the daily maximum, humidity is the mean of
available hourly values, and precipitation includes rain and snow. `rainChance` is
the daily maximum precipitation probability, unavailable for historical data.
Missing provider readings stay `null`; they are not replaced by zero or interpolated
by the app. Historic and forecast datasets must not be treated as field sensors.

Soil moisture is volumetric water content, converted from m³/m³ to percent. The
forecast source is 0–1 cm; the archive source is 0–7 cm. These depths are displayed
in day details and explained in source metadata. They are deliberately shown in
separate timelines rather than joined into one continuous soil series. Near-term
archive values may be incomplete. Long-term climate studies should select a fixed
reanalysis dataset rather than assume the default archive is homogeneous.

## Fetching and performance

`WeatherService` owns the provider adapter, pooled HTTP client, validation,
aggregation, and a bounded per-process LRU/TTL cache. Current weather and forecast
use the identical upstream request and share a ten-minute cache. Historical requests
use a six-hour cache. Concurrent identical misses share one in-flight result.
Cache identities include endpoint, coordinates, units, time zone, and dates; user
labels are added after retrieval, so a cached location name cannot leak between users.
There is no expired-cache or demo fallback. Timeouts, rate limits, HTTP errors and
malformed successful payloads become 503, without exposing upstream exception details.

The frontend uses parameterized React Query keys and cancellation, clears weather
queries when settings change, and shares forecast queries among Environment,
strategy and notification views. Current/forecast queries poll every ten minutes
while active; history is fresh for thirty minutes. Errors stay inside their weather
panel. Historical loading and forecast loading are independent.

The cache is local to each API worker and lost on restart. A multi-worker deployment
can add a shared cache without changing the DTOs. Do not use cached `fetchedAt` as a
provider model-run initialization timestamp; the service does not expose that time.

Default upstream URLs can be overridden with `WEATHER_FORECAST_URL` and
`WEATHER_ARCHIVE_URL` for a local simulation or a different Open-Meteo deployment.
The hosted free Open-Meteo endpoint is for noncommercial use under its usage limits;
commercial deployment requires an appropriate service plan or self-hosting. Preserve
Open-Meteo attribution and upstream data licensing.

## Crop-condition contract

`GET /weather/forecast?field_id=<UUID>` and `GET /weather/history?...&field_id=<UUID>`
add crop assessments to the existing weather response. The caller must have selected the
field. Malformed UUIDs return 422, and inaccessible or missing fields return 404. The API
checks both before contacting the provider. A selected field supplies coordinates even
when account coordinates are unset.

Rules cover Winter wheat, Corn, Soybeans, Alfalfa, and Grassland/Pasture. Crop names are
matched case-insensitively, ignoring leading and trailing spaces. Each available field
soil value can refine the bounds. Fields without soil still get the weather rules using
the baseline crop profile. Unsupported crops and unscoped requests return weather with
`cropAssessment: null`. Current weather remains unscoped.

The [FastAPI schemas](../app/schemas/crop_conditions.py) and
[frontend types](../../frontend/src/types/weather/weather.types.ts) define the contract.

- Series `cropAssessment.model` identifies `crop-weather-rules` version `2.0.0`,
  kind `rule_engine`, with a suitability score from 0 to 100.
- Series `cropAssessment.context` records the field, crop, requested coordinates,
  nullable field soil values, and `soilCoverage` (`complete`, `partial`, or
  `unavailable`). Climate context summarizes the requested forecast or history window
  in response units.
- Series `cropAssessment.bounds` provides window reference limits. Each record's
  `cropAssessment.bounds` provides its temperature, precipitation, soil moisture,
  humidity, and wind cutoffs. The ideal lies inside the inclusive good interval.
  Critical cutoffs are optional and lie strictly outside that interval.
- Daily `cropAssessment` includes `suitabilityScore`, `riskLevel` (`good`, `caution`,
  `high`, or `unknown`), weather `coverage` (`complete`, `partial`, or `unavailable`),
  metric assessments, and alerts. Temperature has separate high and overnight-low
  assessments.
- Each alert contains a stable `ruleId`, metric, reading, severity, crossing code,
  observed value, breached boundary, and unit. Its `drivers` identify the adjustments
  that contributed to that cutoff. Each driver includes a stable rule ID, input name,
  observed value, and unit when applicable. This evidence can ground future explanations
  in the measurements and limits used by the engine.

A reading at or beyond a critical cutoff is high risk. A reading outside the good
interval and short of a critical cutoff warrants caution. Missing readings remain
unknown. The engine reports the worst available warning, and calls a day good only
when all expected weather readings are available and inside the good ranges.
The overall suitability score is the lowest available metric score, or null when
no readings are available. Coverage reports the completeness of the weather inputs.

## Growing-season rules

`CropWeatherRuleEngine.predict(series, context)` uses the same replaceable
`CropConditionModel` interface and runs after weather retrieval. It computes each date
independently using the selected crop profile, that day's Open-Meteo readings, and any
available field soil information. Examples of the interactions include the following.

- High humidity and dry surface soil lower the upper temperature limits.
- Wet surface soil lowers the tolerable precipitation amount. Crop sensitivity and
  reported drainage influence the reduction.
- Heat, dry air, and wind raise the lower surface moisture limits. The selected crop
  and available soil texture determine the baseline moisture range.
- Warm conditions, wet surface soil, and heavy precipitation can narrow humidity
  ranges. Field water capacity, organic matter, and pH can refine the weather limits.

These are general growing-season screening rules with illustrative coefficients.
Alfalfa and pasture temperature ranges draw on published forage growth ranges. The
mixed Grassland/Pasture category uses cool-season forage as a proxy. The modest
crop-specific moisture offsets reflect relative drought response as a design input.
The exact cutoffs and adjustments are product rules without field calibration.
[Oregon State forage information](https://forages.oregonstate.edu/group/1701/alfalfa),
[University of Wisconsin Extension on alfalfa frost](https://cropsandsoils.extension.wisc.edu/articles/frosted-alfalfa/),
[Penn State Extension on cool-season forage growth](https://extension.psu.edu/how-late-can-cool-season-perennial-forages-be-planted),
[FAO indicative drought sensitivity](https://www.fao.org/4/S2022E/s2022e07.htm),
[Oregon State Extension on crop root depth and allowable depletion](https://extension.oregonstate.edu/catalog/em-9717-irrigation-water-scheduling).

The engine computes bounds in metric units, converts them to the response units,
and uses the published cutoffs to classify each reading. Missing inputs contribute
no adjustment. Zero daily precipitation is inside the good rainfall range. Soil
moisture is modeled near the surface and uses different depths in the forecast
and archive. Field assessments are computed separately from the provider cache.

## UI

Environment offers a crop dropdown based on the caller's fields. If several fields
have the chosen crop, the user can select which field supplies the assessment
location. Both charts share the chosen field and use each day's backend good,
caution, and high-risk bands and warning labels. Forecasts can scroll horizontally
on narrow screens, and history fits the available width. Daily details show the
observed value, breached cutoff, contributing conditions, and missing inputs.

## Verification

Run backend tests:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check app tests
```

Run a local Postman simulation (CLI 1.74.0 was used):

```sh
postman simulation run postman/simulations/weather.sim.yaml --port 4407 --no-history --output ndjson
WEATHER_SIMULATION_URL=http://127.0.0.1:4407/open-meteo .venv/bin/python -m unittest discover -s tests -p 'test_weather_simulation.py' -v
```

The test-only stand-in follows Open-Meteo variable names and response shapes. It
supports success, null readings, 429, 503, malformed JSON shapes, delayed responses,
paired warm-normal / warm-humid scenarios, and a humidity wave within one response. The latter hold temperature constant
while varying humidity and verify the resulting heat-limit and alert changes.
The tests execute the real FastAPI routes and real HTTP client; mock values never
enter application runtime. No provider-owned Postman mock was reused or published.
The context document records the scope of evidence and live-provider limitations.

Official contracts: https://open-meteo.com/en/docs and
https://open-meteo.com/en/docs/historical-weather-api.

## Selected-day outlook

With `GEMINI_ENABLED=true` and `GEMINI_API_KEY` set on the backend,
`POST /api/v1/weather/forecast/insight` streams a short Gemini outlook.
The route takes `day` (an ISO forecast date), `locale` (the selected website
language tag), and an optional `field_id`. It reuses the caller's forecast and crop
assessment. Gemini receives the selected day and up to two following days,
including forecast readings and rule alerts. Account details and coordinates
stay on the backend. Set `GEMINI_MODEL` to override the default
`gemini-2.5-flash-lite`.

The response uses `application/x-ndjson` with a `delta` string per line and a
final `{"done":true}` on success. The card uses the built-in weather outlook
when the stream is unavailable or ends without a completion event. Critical
crop warnings come directly from the rule engine.
