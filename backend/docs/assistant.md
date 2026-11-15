# Assistant chat

`POST /api/v1/assistant/chat` is a stateless, streaming chat with the farming assistant (Gemini).
Requires login and `GEMINI_ENABLED=true` with `GEMINI_API_KEY`; otherwise it returns 503.

Field data is **not** loaded into the prompt. The model gets a small session block (locale and the
selected field's name and crop) and calls tools when it needs forecast, climate or soil data. This
keeps the context small however many data sources are added.

## Request

```json
{
  "messages": [{"role": "user", "content": "When can I plant corn?"}],
  "field_id": "optional field uuid",
  "calendar_date": "optional YYYY-MM-DD",
  "tools": ["get_weather_forecast", "get_m3_insights"],
  "locale": "en"
}
```

- `messages`: the whole conversation, oldest first, up to 20 messages of 4000 characters. It must
  start and end with a `user` message. The server stores nothing.
- `field_id`: the selected field. Field-specific tools use it. Optional.
- `calendar_date`: the day selected on the calendar page. The session block tells the model, which
  then reads that day with `get_calendar_events`. Optional.
- `tools`: names of tools the model may call. Omit to allow all, send `[]` to disable tools.
  `GET /api/v1/assistant/tools` lists names and descriptions; an unknown name returns 422.
- The client cannot send a system prompt.

## Response

NDJSON, one event per line:

| Event | Meaning |
| --- | --- |
| `{"delta": "..."}` | a piece of the answer text |
| `{"tool": "get_m3_insights"}` | the model started calling that tool (useful for a "checking..." indicator) |
| `{"done": true}` | the answer is complete |

A stream that ends without `done` failed; the reason is in the server log.

## How a turn works

1. The backend sends the conversation, the system prompt and the tool declarations to Gemini.
2. If the model calls tools, the backend runs them, adds their results to the conversation and asks
   the model again. Identical calls within one answer run once; at most 4 calls per round.
3. After 4 tool rounds the last round has no tools, so the model must answer with what it has.
4. A failing tool does not fail the chat: the model receives a short error (never the exception
   text) and tells the user the data is unavailable. Results over 20,000 characters are cut.

## System prompt

The prompt is plain text in `app/prompts/assistant.txt`. Edit the file; it is re-read whenever its
modification time changes, so no restart is needed. Point `ASSISTANT_PROMPT_FILE` at another file to
override the location. A missing or empty file returns 503. When you add a tool, describe in the
file when to use it.

The code appends the session block under a fixed header that tells the model that the session and
all tool results are data, not instructions. Editing the txt cannot remove that guard.

## Built-in tools

Defined in `app/services/assistant_tools.py`. They call existing services (the same ones behind the
frontend endpoints) and never modify them.

| Tool | Source | Notes |
| --- | --- | --- |
| `get_weather_forecast` | forecast + crop-risk rule alerts | next 3 days; uses the selected field, or the account location without one |
| `get_m3_insights` | `services/m3_lookup.py` | planting/frost timing windows, heat/frost risk, Fallow-Zero. Optional `include_delay_scan` (large; only when the user asks about delaying sowing). Needs a field; `status: unavailable` outside model coverage. Reads local model output files (`M3_OUT`). |
| `get_neighbour_evidence` | `services/m2_lookup.py` | rotation practices vs drought resilience from neighbouring fields: verdict, extra drought effect with intervals, what-if for the field or fields within 30 km, warnings. Optional `crop` and `treatments` (T1-T5). Per-outcome tables are dropped to keep the result small. Needs a field; `status: unavailable` outside coverage. Reads local model output files (`M2_OUT`). |
| `get_calendar_events` | `services/calendar_events.py` | planned events of the selected field (all fields when none is selected) on one day or up to 14 days: rotation dates and weather/drought warnings with description, priority, duration and rationale. `date` defaults to `calendar_date`, else today. Capped at 30 events. |
| `get_soil_moisture` | `services/soil_moisture.py` | latest modelled soil moisture per layer and profile mean at the field's reference point (Open-Meteo). Optional `compare_to_past_years` adds anomaly and percentile against past years (slower). Needs a field. |
| `get_rotation_advice` | `services/rotation_advice.py` | the data behind the crop recommendation page (`GET /fields/{id}/rotation-advice`): ranked candidate crops with score breakdown, risks, benefits, advisories, yield/revenue, sowing calendar, off-season options, history and data gaps. Optional `crop` (the page's `:cropId`) and `priorities`. Only the intended crop and the top 3 get yield, revenue, calendar and soil detail; the season timing block is left to `get_m3_insights`. An unknown crop returns the valid ids. Needs a field. |
| `get_soil_depletion` | `services/soil_depletion.py` via `SoilAssessments` | same cache as `GET /fields/{id}/soil-depletion`. Never waits: the first call starts the background calculation and returns `status: pending`; once it is ready (up to ~100 s) later calls return the full assessment. Needs a field. |

## Adding a tool (for example an ML model)

```python
from app.services.assistant_tools import Tool

def crop_zones_tool(ctx, args):
    if not ctx.field:
        return {"status": "unavailable", "reason": "No field is selected."}
    return {"zones": run_crop_zone_model(ctx.field, year=args.get("year"))}

app.state.assistant_tools.register(
    Tool(
        "get_crop_zones",
        "Crop zones of the selected field ...",  # the model reads this to decide when to call
        crop_zones_tool,
        {"type": "object", "properties": {"year": {"type": "integer"}}},  # optional
    )
)
```

- The handler gets `ChatContext` (`field` dict or None, `locale`, `location`, `state`, and the
  cached `series` forecast) and the model's `args`. Return a dict, or `None` for "no data".
- **Do not use the database session.** Tools run while the response streams, after the request's
  session is closed. `ChatContext` holds only plain data copied beforehand; use `ctx.state`
  services for anything else.
- Handlers are blocking and run in a worker thread. Do not wait on slow jobs: start them in the
  background and return a `pending` status, as `get_soil_depletion` does.
- Exceptions are logged and become a generic error result, so one broken model does not break chat.
  Registering a duplicate name raises `ValueError`.
- Keep results compact: they go back into the model's context.
