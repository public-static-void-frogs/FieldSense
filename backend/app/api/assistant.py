import logging
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.auth import CurrentUser
from app.api.dependencies import Store
from app.schemas.assistant import ChatRequest
from app.services import assistant as service
from app.services.assistant_tools import ChatContext
from app.services.llm import llm_available

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])


class ToolInfo(BaseModel):
    name: str
    description: str


@router.get(
    "/tools",
    response_model=list[ToolInfo],
    description="Tools the assistant can call. Names can be listed in chat `tools` to restrict it.",
)
def tools(request: Request):
    return request.app.state.assistant_tools.describe()


@router.post(
    "/chat",
    response_class=StreamingResponse,
    description=(
        "Stateless chat with the farming assistant. Send the whole conversation each time. "
        "The system prompt comes from the server's prompt file and cannot be set by the client. "
        "Data is not preloaded: the model calls tools (forecast, M3 insights, soil depletion, "
        "registered ML models) when it needs them, using field_id as the selected field. "
        'Streams NDJSON: {"delta": text} lines, {"tool": name} when a tool starts, then '
        '{"done": true}. A stream that ends without done failed.'
    ),
    responses={
        200: {
            "description": "NDJSON text deltas followed by a done event on success.",
            "content": {"application/x-ndjson": {"schema": {"type": "string"}}},
        },
        404: {"description": "Field not found"},
        422: {"description": "Invalid conversation or unknown tool name"},
        503: {"description": "Assistant or its prompt file is unavailable"},
    },
)
def chat(request: Request, body: ChatRequest, user: CurrentUser, store: Store):
    state = request.app.state
    if not llm_available(state.config):
        logger.warning(
            "Assistant chat refused with 503: gemini_enabled=%s, api_key_set=%s. Set "
            "GEMINI_ENABLED=true and GEMINI_API_KEY in the server environment and restart.",
            state.config.gemini_enabled,
            bool(state.config.gemini_api_key.strip()),
        )
        raise HTTPException(503, "Assistant is unavailable")
    registry = state.assistant_tools
    unknown = sorted(set(body.tools or []) - set(registry.names()))
    if unknown:
        raise HTTPException(422, f"Unknown tools: {', '.join(unknown)}")
    try:
        prompt = service.load_system_prompt(state.config.assistant_prompt_file)
    except service.PromptUnavailable as error:
        logger.warning(
            "Assistant chat refused with 503: cannot read prompt file %s (%s)",
            state.config.assistant_prompt_file,
            error,
        )
        raise HTTPException(503, "Assistant prompt is not configured") from error
    field = store.require_field(body.field_id) if body.field_id else None
    # Tools run while streaming, after this request's database session is closed, so copy
    # everything they need now.
    settings = user.settings
    location = SimpleNamespace(
        latitude=settings.latitude,
        longitude=settings.longitude,
        time_zone=settings.time_zone,
        units=settings.units,
        location=settings.location,
    )
    ctx = ChatContext(
        state,
        location,
        field,
        body.locale,
        store.fields(),
        body.calendar_date,
        body.weather_date,
    )
    return StreamingResponse(
        service.stream_chat(
            state.config, body, service.build_system_prompt(prompt, ctx), registry, ctx
        ),
        media_type="application/x-ndjson",
    )
