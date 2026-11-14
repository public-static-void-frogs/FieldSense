# FieldSense

A frontend crop field management dashboard built with React, TypeScript, Vite, Ant Design, and Lucide icons.

## Run

```sh
npm install
npm run dev
```

Start the FastAPI backend from `../backend` with `python main.py`
(see its README for Python setup). Open the local URL printed by Vite.
The frontend `.env` contains the entire API prefix:

```dotenv
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

Copy `.env.example` to `.env` for a fresh checkout. Change this value for your backend,
then restart Vite. Production builds read it at build time. Requests go directly to the
configured API; allow the frontend origin through the backend's `CORS_ORIGINS` setting.
There is no Vite API proxy.

Connection failures, HTTP server errors, and requests that exceed 10 seconds display
an **API is unavailable** page with a **Try again** button. Retrying reloads the failed
queries without changing the current route. Validation failures retain their usual feedback.

```sh
npm run build
npm run preview
```

## Formatting

Run `npm run format` to apply Oxlint fixes, component spacing rules, and Prettier,
or `npm run format:check` to verify them. Control-flow bodies always use braces,
including single-line `if` statements. Leave a blank line after imports and before
JSX returns following hooks or other logic. Oxlint enforces braces;
`scripts/code-spacing.mjs` enforces these blank lines because Prettier has no options
for either convention. The shared Prettier configuration uses single quotes and a
100-column print width. Generated output and the npm lockfile are excluded.

## Project structure

```text
src/
  api/           Feature HTTP methods, query keys/options, mutations, and shared transport
  app/           Application providers, route rendering, and theme
  components/    Common UI shared across unrelated features
  features/      Feature components, hooks, utilities, and constants
  hooks/         Shared hooks for farm resources and chart behavior
  pages/         Dedicated screens for each route
  styles/        Global, application layout, and dashboard styles
  types/         Domain entities and data models grouped by feature
  utils/         General formatting, pagination, and pointer helpers
  main.tsx       Application entry point
```

Feature UI lives alongside its behavior:

```text
features/
  maps/
    components/
      FieldMap.tsx
      FieldMap.css
      MapCard.tsx
    hooks/
    utils/
    constants/
      maps.constants.ts
```

Calendar components belong to `features/planning/components`; field, weather,
overview, help, and layout components follow the same pattern. Only shared UI
such as router buttons, headings, and error boundaries stays in `components/common`.

Component props types live immediately above their component in the same file,
including subcomponents. Hook-specific types live alongside their hook; API request
and query-option types stay with their owning module. `src/types` contains only
domain entities and data models.

Components focus on rendering, translations, queries, and feature hooks. Substantial state and
effects live in `src/features/<feature>/hooks`; pure feature functions live in the adjacent
`utils` folder. Keep simple component logic inline when extracting it would add little value. Hooks follow the Single Responsibility Principle: calendar URL navigation, filtering,
drawer behavior, and view controls are separate; tables use independent filters,
pagination, and viewport hooks. Each overview chart owns its controls. Query data
and mutation actions are consumed separately, and hook return values expose only
one cohesive responsibility.
Use explicit branches or mappings instead of nested ternaries. Extract large conditional JSX branches into named subcomponents
declared below the main component in the same file; keep the branch itself to a
`return <Subcomponent />`. These rules are recorded in
`AGENTS.md`, and the test suite checks for nested ternaries across the source tree.

Field details use dedicated routes such as `/fields/<guid>`. Adding fields uses
`/map/add` and `/map/add/6`. Navigation supports direct links, refresh, and
browser back/forward through React Router. Production hosting must serve `index.html`
for application paths (for example `/fields/<guid>`) so direct links and refreshes work. Settings, help,
and notifications also have their own pages. Removal uses an inline confirmation.
The app does not use modals.

Typography and library colors are centralized in `src/app/theme.ts`: body text
is 16px, supporting text is 14px, and controls are 42px tall. Custom CSS is limited
to layout, map overlays, and the existing green and cream visual treatment.
The `.editorconfig` file defines two-space indentation and consistent line endings.
Field agronomy profiles and land history come from the backend field endpoints. Status tags use explicit semantic foreground and
background colors in the shared theme for readable contrast.

## Explore

- **Overview:** farm totals, selectable field map, crop health, weather outlook, and field recommendations.
- **Field map:** pan, zoom, recenter, switch layers, select a field, or add an available parcel.
- **My fields:** search and filter fields by crop or health status. Each field page starts with a real satellite map focused on that field’s GeoJSON point. Below it are the rotation plan, an AI-style explanation with a blue-purple gradient border, crop/soil/water properties, and searchable land history. Field management and removal controls are at the bottom. The detail map has no heatmap or metric overlay controls.
- **Calendar:** an Ant Design month/year calendar with field and action filters, a compact selected-day agenda, and a searchable table. Primary action buttons open dedicated detail pages with scheduling, rationale, and current field conditions. Date selection preserves the page scroll position.
- **Environment history:** a selectable 14-day forecast, trend charts, and 7-, 30-, or 90-day weather logs.

Demo records and recommendations are owned by the FastAPI backend. Field changes and strategy decisions are shared within one backend process, survive browser refreshes, and reset when that process restarts. React Query caches resources and invalidates dependent queries after mutations. The backend and PostgreSQL are required. Register an account to sign in; no AI services are needed. Map imagery requires internet access to the Esri tile service.

## Dependency installation

All frontend dependencies are installed from the npm registry. Run `npm ci` to install
the versions recorded in `package-lock.json`.

## Crop rotation and system planning

Field pages feature a compact rotation summary and planting window linking to
`/fields/:id/strategy`. The strategy page includes step-by-step actions, technical
inputs, conditional recommendations, and interactive illustrative forecast charts.
Dates link to
`/calendar/YYYY-MM-DD` with optional field/event filters. Action details use
`/calendar/actions/:eventId`.

The entire field schedule supports Accept all and Reject all on the strategy page,
calendar drawer, and action details. Accepted events remain confirmed; rejected events are
hidden from the calendar but remain editable on the strategy page. Responses persist
in the backend demo repository and reset to proposed when event instructions change.

Planning fixtures and calculations live in the backend `app/data` and `app/services/planning.py`.
Predictions, confidence, rationale, and schedules remain illustrative demo data. The planning clock
is fixed to May 24, 2026 to match the rest of the growing-season demo.

```sh
npm run test:planning
npm run test:strategy
```

## Geographic maps

The full-screen field catalog uses `CatalogMap`; overview and field-detail mini-maps
use `FieldMap`. Both use Leaflet with the Esri World Imagery basemap and visible
source attribution. GeoJSON coordinates use `[longitude, latitude]` order.

The catalog loads the visible extent through `/maps/geojson?bbox=…&zoom=…`.
Wide or dense views return bounded geographic count groups. The client combines
these into world-anchored screen bins, with at least 96 CSS pixels between marker
centers. Markers are 40 pixels wide, without halos; nearby groups merge their
counts, area and bounds. The layout updates after navigation and resizing,
reserves space for the scale, and adapts to phone widths. Clicking a group zooms
into its combined extent. Close views render individual fields using Canvas.

The catalog never automatically fits the map after a viewport response. URL
parameters retain the explored center and zoom. The compact top-left hand and
lasso buttons switch between moving the map and selecting fields. In select mode,
clicking points toggles a local selection and drawing a lasso creates a green
section with a centered Add button. Add fits the zone and opens a preview panel;
Cancel section removes it and restores its points. Selected points are hidden. Selections use catalog UUIDs and survive panning but clear when leaving or
refreshing the map. This draft does not change saved fields.
Analyze captures map imagery and calls the real SAM2/TempCNN backend. While pending the zone
pulses; results replace it with selectable crop icons and field boundaries.
Add fields remains a UI-only control. TempCNN uses 16 clear Sentinel-2 observations downloaded
on demand. Predictions display the crop names from the training label mapping. Mini-maps read only saved field geometries. No production sample parcel collection
is generated. See [map selection](docs/map-selection.md) for interaction details.

```sh
npm run test:maps
node --experimental-strip-types --test tests/clusterLayout.test.mjs
```

## Routing

React Router manages clean browser URLs with `createBrowserRouter`. Route definitions
and lazy page modules live in `src/app/routes.ts`; GUID/parcel/date validation lives in
`src/app/route-loaders.ts`. The login and registration routes sit outside the authenticated farm layout, which
renders child pages through `Outlet`. Matched route metadata controls sidebar
selection and fullscreen workspaces.

Use `Link`, `NavLink`, or the Ant Design `RouterButton` integration for navigation
links; use `useNavigate` for operations such as opening a selected map parcel or
redirecting after a mutation. Pages read validated IDs with `useLoaderData` and
calendar parameters with `useParams` and `useSearchParams`. Do not pass navigation
functions through component props or write to `window.location.hash`.

`ScrollRestoration` handles browser history. Calendar date/filter changes use
`preventScrollReset` and retain their local view state. Unknown routes and invalid
IDs/dates render the localized not-found screen. Production hosts must rewrite
application URLs to `index.html`; Vite's dev and preview servers already provide
SPA history fallback. Static assets use root-relative paths.

React Query remains responsible for resource loading, caching, and mutations.
The router loaders validate URL parameters and do not create a second data cache.
Run `npm run test:router` for route matching, parameter validation, search state,
and browser-history behavior.

## Data access and caching

The data layer follows the sample Abitly project's separation of API methods,
query-key factories, reusable query options, and a shared query client. Features
include fields, farm profile, planning, maps, weather, overview analytics,
notifications, and help content.

```text
src/api/fields/
  fields.api.ts        Typed HTTP API methods
  fields.queries.ts    Stable fieldQueryKeys and reusable fieldQueries options
  fields.mutations.ts  Mutations and invalidation of dependent resources
src/types/fields/      Field entities and domain data models
```

Components consume query options with `useSuspenseQuery` or `useSuspenseQueries`.
Consumers subscribe only to the resources they use through shared query options;
there is no catch-all farm hook combining unrelated resources and mutations. The query client is created once per app root with a
60-second stale time. Suspense handles loading, and a query error boundary provides
a translated retry action. Add/remove and strategy-response controls wait for
mutations and report write failures.

Key factories include every server-side query parameter (field IDs, weather
ranges, trend ranges, and metrics). Field mutations invalidate field resources,
planning, overview charts, and notifications. Strategy responses update and
invalidate their shared response query. Removing a field also removes its saved
event responses. Filtering and other temporary UI state remain in components.

`src/api/core/http.ts` supplies the shared fetch transport, forwards cancellation signals,
and surfaces HTTP errors to the existing query and mutation boundaries. Nullable detail
lookups translate a 404 into `null`; mutations retain their status and error message.
There are no frontend domain fixtures, generators, or stores. React Query uses its default
online network mode. UI translations, filters, and presentation constants remain frontend concerns.

The HTTP integration tests start an isolated backend on an ephemeral local port per test file.
Install `../backend/requirements-dev.txt` in its `.venv` first, or set
`NASA_BACKEND_PYTHON` to a Python interpreter with those dependencies installed. Tests require
local loopback access and do not call the running development backend.

Run `npm test` for all checks of domain behavior, translations, and queries, or
`npm run test:queries` for cache deduplication, key separation, mutation
invalidation, response persistence, failure recovery, and architecture boundaries.

## UI languages

The app uses react-i18next with English as the default fallback and Ukrainian as the second locale. On first use it follows the browser’s preferred supported language (`en` or `uk`, including regional variants). The language selector in Settings applies immediately and saves the choice in local storage under `fieldsense.language`; that choice takes precedence on later visits.

UI strings live in `src/i18n/locales/en.json` and `src/i18n/locales/uk.json`. Each JSON catalog is loaded through a dynamic import, so Ukrainian is only downloaded when needed. English also loads as the fallback. Ant Design controls, calendar dates, the document language, and page metadata follow the selected language. Demo field data, user-entered values, and sample recommendation content stay unchanged.

Use `useTranslation()` and `t()` for new UI text. Keys are English phrases with key and namespace separators disabled; keep complete sentences together and use interpolation for variable values. Add matching keys and interpolation variables to both catalogs. Run `npm run test:i18n` to check catalog consistency, language detection, saved preferences, and lazy loading.

## Google OAuth registration pages

Public, localized routes are available at `/about`, `/privacy`, `/terms`, and
`/support`. They identify FieldSense, describe the demo, disclose browser storage
and third-party map requests, and explain the planned Google sign-in and optional
export to a dedicated FieldSense calendar. Support/privacy contact is
`olehzpr@gmail.com`. Login, Overview, and Help link to these pages.

Google OAuth and Calendar synchronization are not implemented. The pages describe
these as planned features and do not claim to collect or retain Google data.
See [Google OAuth registration and review](docs/google-oauth-registration.md) for
the exact production URLs, intended scopes, domain-verification steps, and work
required before submitting the actual integration for review. `vercel.json`
configures SPA deep links; deploy this build before using the new URLs in the
Google console.

## Normalized backend data

The backend loads one JSON array per collection from `app/data`. Fields own their geometry
and property references; histories, sensor readings, crop seasons, plans, events, and strategy records link
through GUID foreign keys. Python joins these records into the existing read models. The
field API also exposes `farmId`, `cropId`, `parcelId`, `geometry`, and joined `properties`.

Field routes and calendar filters use GUID strings. Parcel routes keep numeric land
identifiers. Field mutations invalidate map data so adding or removing a field updates
its parcel association. Existing numeric field links must be replaced with GUID URLs.

## Accounts and saved settings

Set up the backend database and signing secret using
[the backend auth guide](../backend/docs/authentication.md).
Open Vite at `http://localhost:5173` with `VITE_API_BASE_URL=http://localhost:8000/api/v1`.
Use the same hostname for the UI and API so SameSite cookies work. The local `.env`
has been updated accordingly.

`/register` uses two steps: account details (name, email, password confirmation),
then an optional farm name and a required map location. The map requests browser
geolocation with permission and supports manual selection or choosing its center.
The selected latitude and longitude are stored with the location label. It signs in immediately and preserves the original requested page. `/login`
verifies email/password with the API. The JWT stays in an HttpOnly cookie; requests
include browser credentials. Private routes redirect to login when the session expires.
Settings provides logout, which revokes all existing sessions for the account.

Settings saves account information, application preferences, and farm/location labels
per user. Session lifetime defaults to 24 hours and accepts 1–720 hours; saving renews
the current cookie and configures future logins. Account changes and settings survive
API restarts. Farm labels are preferences; fields and planning remain shared demo data.
Language changes apply immediately; use Save to persist them to your account.

Authentication and settings use the same API/query/mutation organization as existing
resources. Successful login/registration/logout clears cached private resources.
Frontend integration tests create temporary databases, run Alembic migrations, and
register test users; their Node transport emulates a browser cookie jar.

## Environment

Weather comes from Open-Meteo through the backend using the map location, time zone,
and units saved in Settings. Environment starts with metric tabs, followed by a
single scrollable row of 14 daily forecast cards with filled weather icons,
selected-day descriptions and a daily insight panel, and a forecast chart.
The selected-day card animates the matching weather scene for all supported
conditions, with a neutral fallback and static scenes for reduced-motion preferences.
The insight uses local forecast-based templates, styled like the field explanation;
it does not call an AI service. Forecast dates are selected with the day cards. Past conditions pairs a chart with a compact selected-metric
card, plus custom date ranges and a visible daily environment log. Missing readings
show a dash; weather errors remain within their panel. No sample weather is used.

The backend shares cached current/forecast data, and React Query deduplicates readers
across Overview, Environment, strategy, and notifications. Historical and forecast soil
moisture use different model depths, displayed in day details. Crop health and rotation
recommendations remain illustrative. See the backend's `docs/weather-integration.md`
for API semantics, source licensing, and local Postman simulations.

Environment lists supported crops from saved fields and shows a field picker when more
than one field grows the selected crop. The API uses the field's point coordinates and
farm time zone, its crop and available soil properties, and the requested weather window.
Each daily assessment includes the bounds used for its scores and alerts.
Charts interpolate those daily limits into a continuous gradient and changing critical
curves; series bounds are reference metadata. Charts show backend-provided good/caution/high-risk zones, labelled daily values,
and overnight temperature warnings. Day cards and selected-day details show ⚠️ when the
backend returns crop alerts. Alert details show the weather and soil inputs that adjusted
the breached limit. Suitability runs from 0 (poor) to 100 (good).

The API's versioned rule engine uses general growing-season limits. The frontend displays
the returned bounds, scores, coverage, and alerts. The backend's
`docs/weather-integration.md` describes the rules and the `field_id` contract.
Unscoped weather requests use the account location and return weather alone.

## Real-source field map

`/map` uses viewport-based API loading, with groups at wide zooms and a maximum of
600 map features per response. It reads the imported USDA NASS CSB catalog. The
supplied interior points represent field locations. Click a group to zoom in,
then click points or draw a lasso to build a temporary selection. Clusters cannot
be selected as individual fields, and selection performs no database actions.

See [source import and map verification](../backend/docs/field-map-prototype.md)
for the database migration, full-archive importer and performance benchmark. The
map requires `GET /maps/summary` and the parameterized `GET /maps/geojson` endpoint;
older backend versions that return a complete unbounded GeoJSON collection are
not supported. Synthetic HTTP-test inputs live only in the test harness.
