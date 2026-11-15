# FieldSense

Farm field monitoring: a React frontend (`frontend/`) and a FastAPI backend (`backend/`).
This README summarises the backend services in `backend/app/services/`: what each script does and
which data it reads. For setup see `backend/README.md`; for the chat assistant see
`backend/docs/assistant.md`.

## AI agent tools

The chat assistant does not get field data in its prompt. It calls these tools when it needs data
(`assistant_tools.py`; see `backend/docs/assistant.md`):

| Tool | Scripts behind it | Returns |
| --- | --- | --- |
| `get_weather_forecast` | `weather.py`, `crop_conditions.py`, `weather_insight.py` (formatter only) | Next 3 days of weather plus crop-risk alerts for the selected field, or for the saved location when no field is selected. |
| `get_m3_insights` | `m3_lookup.py` | Sowing, harvest and frost windows, heat and frost risk, Fallow-Zero water estimates. Optional delayed-sowing scan. |
| `get_neighbour_evidence` | `m2_lookup.py` | Whether rotation practices changed drought resilience for neighbouring fields: verdict, extra drought effect with intervals, what-if for the field or fields within 30 km. An adjusted association, not a guaranteed effect. |
| `get_calendar_events` | `calendar_events.py` | Planned events on a day or short range for the selected field (or all fields): rotation dates and weather or drought warnings with the reason each is scheduled. Used by the calendar page assistant. |
| `get_soil_moisture` | `soil_moisture.py` | Latest modelled soil moisture per layer and profile mean at the field point. Optional comparison with past years. |
| `get_rotation_advice` | `rotation_advice.py` (with `season_timing.py` and the `rule_engine/`) | Ranked next-crop advice behind the crop recommendation page: score breakdown, risks, benefits, advisories, yield and revenue estimates, sowing calendar, off-season options, history and data gaps. |
| `get_crop_production` | `crop_production.py` (with `nass.py`) | What the selected field, given counties or a state produced in a past year: field area x county-average NASS yield (an expected value, not a harvest record), or NASS production totals for a region. Crop from the CDL at the field point unless named. | USDA NASS Quick Stats (`NASS_API_KEY`), FCC, CropScape | Infrastructure: tool; services are new |
| `get_crop_revenue` | `crop_revenue.py` (with `nass.py`) | Expected gross revenue (low / base / high) and optional ROI of a crop plan on the selected field: yield trend x median price received from NASS. No costs other than the given investment. | USDA NASS Quick Stats (`NASS_API_KEY`) | Infrastructure: tool; services are new |
| `get_soil_depletion` | `soil_depletion.py` via `field_insights.py`, using `crop_history.py` and `ml/greenness.py` | Soil depletion screening index, or `pending` while it is still being computed. |

**Not yet available to the agent:** `season_timing.py` (its timing reaches the agent through `get_m3_insights`), `section_analysis.py` and the other `ml/` modules, `crop_history.py` map layers
and year-by-year history, and the database-backed services (`maps.py`, `saved_crop_areas.py`,
`fields.py`, `overview.py`, `planning.py`, `resources.py`). New tools are registered in
`assistant_tools.py`; the guide in `backend/docs/assistant.md` shows how.

## Backend services

### Weather and soil moisture

| Script | What it does | Data it retrieves | AI tool |
| --- | --- | --- | --- |
| `weather.py` | Weather adapter with a bounded in-memory cache and request de-duplication. Serves current conditions, the daily forecast and historical daily weather. No demo fallback: provider failure is an error. | **Open-Meteo** forecast and archive APIs, for the field point or the account's saved location. | Yes: `get_weather_forecast` |
| `soil_moisture.py` | Modelled soil moisture at a parcel's analysis point: current value, history over a date range, and a comparison with the same time of year in past years. | **Open-Meteo** hourly soil-moisture layers (forecast and archive) and **NASA POWER** daily wetness (`GWETTOP`, `GWETROOT`, `GWETPROF`). Reuses the `weather.py` fetcher and cache. | Yes: `get_soil_moisture` |
| `crop_conditions.py` | Deterministic crop-weather rule engine. Scores a forecast or history against crop-specific limits (temperature, rainfall, moisture, humidity, wind), adjusted by field soil, and returns alerts with the readings that triggered them. | Nothing external. Input is a weather series from `weather.py` plus the field's crop and soil properties. | Yes: `get_weather_forecast` (crop-risk alerts) |
| `weather_insight.py` | Builds the compact forecast + alert input and the prompt for the short weather outlook on the weather page. | The forecast and crop assessment above; the text comes from Gemini through `llm.py`. | Partly: its forecast formatter feeds `get_weather_forecast`; the weather-page Gemini call is separate |

### Crop history and soil

| Script | What it does | Data it retrieves | AI tool |
| --- | --- | --- | --- |
| `crop_history.py` | Annual crop class (2008-2025) at a field point, and rendered crop-map layers for the map. | **USDA Cropland Data Layer** image service (`pdi.scinet.usda.gov`). | Indirect: `get_soil_depletion` uses its point and history lookups |
| `cdl_classes.py` | Lookup table from CDL class codes to crop names. | Static table, no retrieval. | No |
| `soil_depletion.py` | Soil depletion screening index (0-100) from four weighted signals: crop-rotation load, Sentinel-2 greenness trend, soil properties and county yield trend. Signals that cannot be fetched are skipped and reported. | Crop history from `crop_history.py`; **Sentinel-2** scenes via the Earth Search STAC API (AWS); **USDA Soil Data Access** (SSURGO soil); **FCC** census API (county lookup); **USDA NASS QuickStats** county and state yields (needs `NASS_API_KEY`). | Yes: `get_soil_depletion` |
| `field_insights.py` | Runs `soil_depletion.py` in the background (2 workers) and caches results for 12 hours (15 minutes when partial), so requests return `pending` instead of blocking. | Crop history, then everything `soil_depletion.py` reads. | Yes: `get_soil_depletion` (background runner and cache) |

### Climate timing and rotation advice

| Script | What it does | Data it retrieves | AI tool |
| --- | --- | --- | --- |
| `m3_lookup.py` | Reader for the precomputed **M3** model output. Matches a point to the nearest indexed field (within 1 km) or weather cell (within 45 km) and returns sowing/harvest/frost date windows, heat and frost risk, delayed-sowing scan, and Fallow-Zero cover-crop water estimates. Runs no models and calls no external service. | Local parquet/CSV/JSON files in the M3 output folder (`M3_OUT`, default `data/m3_out`): field index, cell windows and risks, 2040 risks, delay scan, Fallow-Zero units and calibration, NASS validation. | Yes: `get_m3_insights` |
| `m2_lookup.py` | Reader for the precomputed **M2** neighbour-evidence output. Matches a point to the nearest analysed field (within 1 km), or to the fields within 30 km (at least 20), or falls back to the study-wide result. Returns how rotation practices (continuous cropping, diverse rotation, small grain/hay, winter cover, host-crop return interval) changed drought resilience against neighbours under the same weather, with intervals, validation checks and a verdict. An adjusted association, not a guaranteed effect. Runs no models and calls no external service. | Local CSV/parquet files in the M2 output folder (`M2_OUT`, default `data/m2_out`), written by `ml/field-prediction-model/neighbour-evidence-engine/m2_neighbour_evidence.py`: `effects.csv` (required), `field_effects.parquet`, `outcome_diagnostics.csv`, `county_check_<crop>.csv`. Served by `GET /fields/{id}/m2-insights`. | Yes: `get_neighbour_evidence` |
| `season_timing.py` | Picks the values the recommendation page shows from the M3 output (early/typical/late sowing window, heat and frost risk per climate scenario) and renames them to the API contract. Adds no modelling. | The same M3 output files, through `m3_lookup.py`. | No |
| `rotation_advice.py` | Adapts a stored field to the standalone `rule_engine/` (repository root) and returns ranked next-crop advice with data gaps. | Local files under `ROTATION_DATA_ROOT` (default `data/local/usa_sample`): season summaries, weekly climate record, soil of sampled fields, CDL history (read with DuckDB); local timing from `season_timing.py`; **USDA Soil Data Access** for fields without stored soil (`ROTATION_SOIL_LOOKUP`). | Yes: `get_rotation_advice` |

### Map sections and ML

| Script | What it does | Data it retrieves | AI tool |
| --- | --- | --- | --- |
| `section_analysis.py` | Analyses a section of the map: SAM2 segments fields on the submitted map image and a trained TempCNN classifies each field's crop. Fields without enough clear observations are reported as skipped. | The submitted map PNG and point prompts; **Sentinel-2** time series through `ml/greenness.py`; local model weights (`ml/` folder, `SAM2_CHECKPOINT`, `TEMPCNN_CHECKPOINT`). | No |
| `ml/greenness.py` | Builds 16-observation Sentinel-2 sequences per point for the crop classifier, skipping cloudy pixels. | **Sentinel-2 L2A** scenes via the Earth Search STAC API (AWS). | Indirect: `get_soil_depletion` uses its Sentinel-2 reader |
| `ml/geometry.py` | Converts SAM2 pixel masks to geographic field polygons (Web Mercator and WGS84, geodesic area). | Nothing external. | No |
| `ml/crop_zones.py` | Dissolves classified masks into connected crop zones. | Nothing external. | No |

### Stored data (database)

| Script | What it does | Data it retrieves | AI tool |
| --- | --- | --- | --- |
| `maps.py` | Viewport queries for the field map: indexed point lookups when zoomed in, pre-aggregated clusters when zoomed out, at most 600 features per response. Rebuilds the cluster cells. | Database tables `field_map_cells` and `map_datasets`, plus the account's selected fields. | No |
| `saved_crop_areas.py` | Saves one merged boundary per account and crop from analysed map zones. | Writes to the database (fields and the user's selections); computes area from the submitted polygons. | No |
| `fields.py` | Returns a field's stored properties (soil, crop details). History and recommendation are empty or "not available" until real data exists. | The account's stored field record. | No |
| `overview.py` | Totals the area per crop for the dashboard chart. Observation trends stay empty until measured. | The account's selected fields. | No |
| `planning.py` | Today's date in the account's time zone, and the planning endpoints: calendar events (`/planning/events`, `/fields/{id}/events`), the rotation plan (`/fields/{id}/rotation`), the strategy (`/fields/{id}/strategy`) and the saved accept/decline responses (`/planning/responses`, `PUT /fields/{id}/strategy/response` for all events of a field, `PUT /fields/{id}/events/{event_id}/response` for one). | The account's saved time zone and fields; table `event_responses` for the responses. | No |
| `rotation_strategy.py` | Turns the ranked rotation advice into the plan and strategy pages: next crop, the crop after it (a second engine run with the next crop added to the history), sowing and window dates, steps with checkpoints, what to do if conditions change, and a rescaled "rotation fit" comparison (100 best candidate, 0 worst; not a yield prediction). Also caches the default advice (6 hours) for the calendar and the strategy. | `rotation_advice.py` (rule engine) and the same sources it reads. | No |
| `calendar_events.py` | Builds calendar events per field and caches the rotation part for 6 hours. Agent tool: `get_calendar_events`. Rotation dates: harvest of the current crop, autumn cover-crop sowing, soil check, field preparation, sowing, flowering scouting and harvest of the best-ranked crop. Warnings: heat stress, cold, heavy rain, strong wind and dry soil from the crop rules, heatwaves (3+ days at 32 °C or more), thunderstorms, extreme rain (50 mm) and wind (60 km/h), hard frost in April-October, and county drought. A failing source drops only its own events. | `rotation_advice.py` (stage calendars, off-season options, season timing), the 14-day forecast from `weather.py` with `crop_conditions.py` alerts, and `drought.py`. | Yes: `get_calendar_events` |
| `nass.py` | Shared USDA NASS Quick Stats, FCC county and CropScape client with a per-process cache; crop table (units, test weights, price series, sale months). Needs `NASS_API_KEY`; U.S. only. | NASS Quick Stats, FCC, CropScape | Infrastructure: new |
| `crop_production.py`, `crop_revenue.py` | Past-year production of a field or region and expected gross revenue / ROI of a crop plan. Agent tools: `get_crop_production`, `get_crop_revenue`. Seed cost and a history-CSV fallback of the original scripts are not included. | via `nass.py` | Infrastructure: new |
| `drought.py` | Current drought level of the field's county: the worst category covering at least 30% of the county, and whether it is worsening over the last 5 weeks. U.S. counties only. Cached for 6 hours. | **U.S. Drought Monitor** county statistics (`usdmdataservices.unl.edu`) and the **FCC** census API for the county. | No |
| `resources.py` | Farm profile, notifications and the team list for the help page. | The account's profile and settings; notifications are empty; the team list is hard-coded. | No |

### LLM assistant

| Script | What it does | Data it retrieves | AI tool |
| --- | --- | --- | --- |
| `llm.py` | Streaming client for **Google Gemini**. `stream_gemini` serves the weather outlook; `gemini_round` serves chat, with tool calls. | Model text from the Gemini API (`GEMINI_API_KEY`, `GEMINI_ENABLED`). | Infrastructure: model client for chat |
| `assistant.py` | Chat orchestration: loads the system prompt from `app/prompts/assistant.txt`, runs the model, executes the tools it asks for (up to 4 rounds), and streams the answer. | None itself; it calls the tools below. | Infrastructure: runs the tool loop |
| `assistant_tools.py` | Tool registry and the built-in tools `get_weather_forecast`, `get_m3_insights`, `get_soil_depletion`, `get_neighbour_evidence`, `get_soil_moisture`, `get_rotation_advice`, `get_crop_production` and `get_crop_revenue`, so data is fetched only when the model asks for it. | Through the services above: forecast and crop alerts (`weather.py`, `crop_conditions.py`), M3 and M2 output (`m3_lookup.py`, `m2_lookup.py`), soil moisture (`soil_moisture.py`), soil index (`field_insights.py`). | Infrastructure: tool registry and the nine tools |

## Where the data comes from

| Source | Used by |
| --- | --- |
| Open-Meteo | `weather.py`, `soil_moisture.py` |
| NASA POWER | `soil_moisture.py` |
| USDA Cropland Data Layer | `crop_history.py` (also feeds `soil_depletion.py` and `rotation_advice.py`) |
| USDA Soil Data Access (SSURGO) | `soil_depletion.py`, `rotation_advice.py` |
| USDA NASS QuickStats, FCC census API, CropScape | `soil_depletion.py`, `nass.py` (FCC also `drought.py`) |
| U.S. Drought Monitor | `drought.py` |
| Sentinel-2 via Earth Search STAC | `soil_depletion.py`, `section_analysis.py`, `ml/greenness.py` |
| Google Gemini | `llm.py` (weather outlook and chat) |
| Local model output (`data/m2_out`) | `m2_lookup.py` |
| Local model output (`data/m3_out`) | `m3_lookup.py`, `season_timing.py`, `rotation_advice.py` |
| Local rotation data (`data/local/usa_sample`) | `rotation_advice.py` |
| PostgreSQL | `maps.py`, `saved_crop_areas.py`, and the services that read the account's fields |
