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

All resource routes use `/api/v1` and require authentication.
`GET /` remains the public health endpoint.

- `app/api/`: routes and request-scoped database/user dependencies.
- `app/repositories/`: SQLAlchemy models and database reads/writes.
- `app/schemas/`: validated request and response contracts.
- `app/services/`: resource projections, weather and crop assessments.
- `migrations/`: Alembic schema migrations; run `alembic upgrade head` on deployment.
- `tests/`: API, persistence, isolation, migrations and weather checks.
- `openapi.json`: generated from routes and Pydantic models.

See [authentication](docs/authentication.md), [weather integration](docs/weather-integration.md)
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
