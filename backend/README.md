# Field Shift NASA backend

FastAPI API for the [frontend](../frontend/), requiring Python 3.10+.
Accounts, settings, fields and user field selections persist in PostgreSQL through
SQLAlchemy. Production demo fixtures and generated agronomic data have been removed.
Weather uses live Open-Meteo model data.

## Run locally

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Configure DATABASE_URL, JWT_ISSUER and a JWT_SECRET of at least 32 bytes.
python -c "import secrets; print(secrets.token_urlsafe(48))"
alembic upgrade head
python main.py
```

The server listens on `http://localhost:8000`. Start the frontend separately with
`npm run dev`, open `http://localhost:5173`, and set `VITE_API_BASE_URL` to
`http://localhost:8000/api/v1`. Use the same hostname for the frontend and backend
so session cookies work. Configure `CORS_ORIGINS` for deployed clients.

For an existing virtual environment, run `./.venv/bin/python -m pip install -r requirements.txt`
from `backend` to install new dependencies such as pandas and PyArrow for M3. Run
`./.venv/bin/python main.py` to launch with that same interpreter.

## Fields and selections

`fields` contains the shared catalog. `user_fields` links users to fields with a
composite primary key and cascading foreign keys. New accounts have no selections.
One catalog entry can be selected by multiple accounts. Data survives restarts
and is shared between API workers.

| Request (relative to `/api/v1`) | Purpose |
| --- | --- |
| `GET /fields/catalog` | Browse shared catalog entries |
| `GET /fields` | List the current user's selected fields |
| `POST /fields` | Create a field and select it atomically |
| `PUT /fields/{id}/selection` | Select an existing field idempotently |
| `GET /fields/{id}` | Read a selected field |
| `DELETE /fields/{id}` | Remove the caller's selection, preserving the catalog |

`GET /fields/catalog` is paginated (default 100, maximum 500); use the viewport map
API to explore the source dataset.

Manual creation requires name, crop, area in hectares, and Point
GeoJSON geometry. Parcel ID and measurements are optional. Missing measurements
return null. The catalog starts empty; migrations do not import fixtures.
See [persistent fields](docs/field-storage.md) for payloads, constraints, selection
semantics and client compatibility changes. The former parcel-only creation flow
must supply area/geometry or use the selection endpoint.

The [real-source map prototype](docs/field-map-prototype.md) imports the supplied
county point archive and serves viewport-limited points or preaggregated groups.

Maps expose catalog field points and mark the caller's selections. Overview
crop areas use only selected fields. History, schedules, notifications and chart
observations are empty until real data is available. Unavailable properties,
recommendations and strategies return 404. The planning date follows the caller's
saved time zone. Weather assessments for supported crops use the field point and
apply soil adjustments when field soil inputs are available.

## API contract and organization

Interactive docs: [Swagger UI](http://localhost:8000/docs).
Live contract: [OpenAPI](http://localhost:8000/openapi.json).

### Crop history

Selected fields expose `GET /api/v1/fields/{id}/crop-history` for annual
classifications at the default point or a supplied `lon` and `lat`, and
`GET /api/v1/fields/{id}/crop-history/layer/{year}` for the corresponding
map overlay. Both endpoints accept the zero-based saved polygon index in
`part`. A field saved as a point uses a roughly 500-meter window.

The service reads the USDA Cropland Data Layer for 2008–2025. The point
history uses the raster pixel at the requested location. The map export
uses nearest-neighbor resampling, clips to the saved polygon when present,
and returns a transparent PNG with its bounds and each class’s share of classified pixels. The
API keeps these annual classifications separate from recorded crop seasons.
Upstream failures return 502. Raster support is included in the standard
backend requirements.

### Field insights

- `GET /api/v1/fields/{id}/soil-depletion?part=0` uses the same reference point
  as crop history for a saved polygon, or the saved coordinates for a point
  field. The index combines USDA crop history, Sentinel-2 peak greenness,
  SSURGO soil properties and optional NASS county yields. Rotation now accounts
  for crop demand and reports repeated crops by year. Set `NASS_API_KEY`
  in `backend/.env` to enable county yields. An overall score requires at
  least half of the configured input weight. It is a screening estimate
  with Corn Belt thresholds, and fertility measurements require a soil test.
  The first request can return `pending` or `busy`; poll the same URL for
  `ready`. Results and running work are shared within each API process.
- `GET /api/v1/fields/{id}/soil-moisture?part=0` returns the latest available modeled
  reading at the parcel reference point, with five depths and a 0–81 cm profile.
- `GET /api/v1/fields/{id}/soil-moisture/history?part=0&start=2025-06-01&end=2025-06-30`
  returns per-layer readings and statistics. Open-Meteo ERA5-Land supports hourly
  ranges of up to 31 days and daily ranges of up to 366 days. Select
  `source=power` for daily NASA POWER wetness fractions. The Open-Meteo values
  are volumetric moisture (m³/m³); the NASA POWER values use a different scale.
- `GET /api/v1/fields/{id}/soil-moisture/comparison?part=0` compares the current
  0–81 cm profile with each of the previous ten years’ 0–100 cm profiles for the
  same calendar window. Anomaly and percentile require at least three prior
  years. Profile means require data at every layer in the advertised profile.
- `GET /api/v1/fields/{id}/rotation` and `/strategy` build the rotation plan and strategy from the
  ranked rotation advice (next crop, following crop, dates, steps, contingencies); `404` when the
  advice cannot be computed. `PUT /api/v1/fields/{id}/strategy/response` saves one decision
  (`accepted`, `declined` or `proposed` to clear) for every calendar event of the field, and
  `GET /api/v1/planning/responses` lists them. A response stores a fingerprint of the reviewed event,
  so it stops applying when the event's date or text changes. Migration `0007_event_responses`.
- `GET /api/v1/planning/events` and `GET /api/v1/fields/{id}/events` return calendar events built
  from the rotation advice (sowing, soil check, field preparation, harvest, cover crop) and from
  warnings: crop alerts, heatwaves, thunderstorms, extreme rain, wind and frost from the 14-day
  forecast, and county drought from the U.S. Drought Monitor (U.S. fields only). Rotation dates
  are medians of past seasons, not forecasts. A source that fails drops only its own events.
- `GET /api/v1/fields/{id}/m2-insights` looks up the saved point in the M2 neighbour-evidence
  tables written by `ml/field-prediction-model/neighbour-evidence-engine/m2_neighbour_evidence.py`.
  Set `M2_OUT` (default `data/m2_out`) and restart the backend after replacing the tables. The
  response is a field what-if, a summary of fields within 30 km, or the study-wide result, and
  is an adjusted association, not a guaranteed effect. A missing folder returns 503.
- `GET /api/v1/fields/{id}/m3-insights` looks up the saved point in the supplied
  `data/m3_out` tables. Set `M3_OUT` to use another directory and restart the
  backend after replacing the tables. The response distinguishes a nearby
  indexed field, a modeled weather cell, and locations outside coverage.
  It reports historical crop timing and risk and the range across climate
  models for 2040. The supplied archive contains no Fallow-Zero water result
  tables, so `fallow_zero` is null with this dataset.

All resource routes use `/api/v1` and require authentication.
`GET /` remains the public health endpoint.

- `app/api/`: routes and request-scoped database/user dependencies.
- `app/repositories/`: SQLAlchemy models and database reads/writes.
- `app/schemas/`: validated request and response contracts.
- `app/services/`: resource projections, weather and crop assessments.
- `migrations/`: Alembic schema migrations; run `alembic upgrade head` on deployment.
- `tests/`: API, persistence, isolation, migrations and weather checks.
- `openapi.json`: generated from routes and Pydantic models.

See [authentication](docs/authentication.md), [assistant chat](docs/assistant.md),
[weather integration](docs/weather-integration.md)
the [source-data integration contract](docs/core-and-source-data-contract.md),
and [SAM2/TempCNN section analysis setup](docs/section-analysis.md).

## Verification

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
ruff check app tests migrations main.py
ruff format --check app tests migrations main.py
alembic check
```

Tests use temporary SQLite databases and explicit test-only field inputs. Opt-in
weather simulation checks use the existing local Postman simulation described in
the weather integration guide; they never require live weather.

Regenerate the checked-in contract after changing routes or schemas:

```sh
python -c 'import json; from pathlib import Path; from app.main import app; Path("openapi.json").write_text(json.dumps(app.openapi(), indent=2) + "\n")'
```
