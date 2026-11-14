from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.auth import CurrentUser
from app.api.dependencies import Store
from app.schemas.assistant import ChatRequest
from app.services import assistant as service
from app.services.assistant_context import ChatContext
from app.services.llm import llm_available

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get(
    "/contexts",
    response_model=list[str],
    description="Names of the context providers that can be listed in chat `contexts`.",
)
def contexts(request: Request):
    return request.app.state.assistant_contexts.names()


@router.post(
    "/chat",
    response_class=StreamingResponse,
    description=(
        "Stateless chat with the farming assistant. Send the whole conversation each time. "
        "The system prompt comes from the server's prompt file and cannot be set by the client. "
        "Context sections (field, forecast, ML models) come from registered providers; with "
        "field_id they are grounded in that field. Streams NDJSON: {\"delta\": text} lines, "
        "then {\"done\": true}. A stream that ends without done failed."
    ),
    responses={
        200: {
            "description": "NDJSON text deltas followed by a done event on success.",
            "content": {"application/x-ndjson": {"schema": {"type": "string"}}},
        },
        404: {"description": "Field not found"},
        422: {"description": "Invalid conversation or unknown context name"},
        503: {"description": "Assistant or its prompt file is unavailable"},
    },
)
def chat(request: Request, body: ChatRequest, user: CurrentUser, store: Store):
    state = request.app.state
    if not llm_available(state.config):
        raise HTTPException(503, "Assistant is unavailable")
    registry = state.assistant_contexts
    unknown = sorted(set(body.contexts or []) - set(registry.names()))
    if unknown:
        raise HTTPException(422, f"Unknown contexts: {', '.join(unknown)}")
    try:
        prompt = service.load_system_prompt(state.config.assistant_prompt_file)
    except service.PromptUnavailable as error:
        raise HTTPException(503, "Assistant prompt is not configured") from error
    field = store.require_field(body.field_id) if body.field_id else None
    sections = registry.collect(
        ChatContext(state, user, store, field, body.locale), body.contexts
    )
    system_prompt = service.build_system_prompt(prompt, body.locale, sections)
    return StreamingResponse(
        service.stream_chat(state.config, body, system_prompt),
        media_type="application/x-ndjson",
    )
