# Assistant chat

`POST /api/v1/assistant/chat` is a stateless, streaming chat with the farming assistant (Gemini).
Requires login and `GEMINI_ENABLED=true` with `GEMINI_API_KEY`; otherwise it returns 503.

## Request

```json
{
  "messages": [{"role": "user", "content": "Any frost risk this week?"}],
  "field_id": "optional field uuid",
  "contexts": ["field", "weather_forecast"],
  "locale": "en"
}
```

- `messages`: the whole conversation, oldest first, up to 20 messages of 4000 characters. It must
  start and end with a `user` message. The server stores nothing.
- `field_id`: grounds the context in that field. Optional.
- `contexts`: names of context providers to include. Omit for all. `GET /api/v1/assistant/contexts`
  lists the names; an unknown name returns 422.
- The client cannot send a system prompt.

## Response

NDJSON: `{"delta": "..."}` lines, then `{"done": true}`. A stream that ends without `done` failed.

## System prompt

The prompt is plain text in `app/prompts/assistant.txt`. Edit the file; it is re-read whenever its
modification time changes, so no restart is needed. Point `ASSISTANT_PROMPT_FILE` at another file to
override the location. A missing or empty file returns 503.

The code appends the context after the prompt under a fixed header that tells the model the context
is data, not instructions. Editing the txt cannot remove that guard.

## Context providers

The context sent to the model is a JSON object: `locale` plus one section per provider. A provider is
a function `(ChatContext) -> dict | None` registered under a unique name:

```python
def crop_zones_context(ctx):
    if not ctx.field:
        return None
    return {"zones": run_crop_zone_model(ctx.field)}

app.state.assistant_contexts.register("crop_zones", crop_zones_context)
```

`ChatContext` gives providers `user`, `store`, `field` (dict or None), `locale`, `state` (app state)
and `series` (the cached forecast with crop assessment for the field or the account location).

Rules: return `None` for "nothing to add" (the section is omitted); an exception is logged and the
section skipped, so one broken model does not break chat. Registering a duplicate name raises
`ValueError`. Built-in providers live in `app/services/assistant_context.py`; all of them need
`field_id` except `weather_forecast`, which falls back to the account location:

| Name | Source | Notes |
| --- | --- | --- |
| `field` | the selected field | name and crop |
| `weather_forecast` | forecast + crop-risk rule alerts | next 3 days |
| `m3_insights` | `services/m3_lookup.py` | planting/frost timing windows and heat/frost risk, same data as `GET /fields/{id}/m3-insights` minus the delay scan. `status: unavailable` when the field is outside model coverage. Reads local model output files (`M3_OUT`). |
| `soil_depletion` | `services/soil_depletion.py` via `SoilAssessments` | the screening index, same cache as `GET /fields/{id}/soil-depletion`. Chat never waits for it: the first request starts the background calculation and the section says `status: pending` (or `busy`); once it is ready (up to ~100 s) later turns include the full assessment. |

To skip the heavier ones, send `contexts` (for example `["field", "weather_forecast"]`).
