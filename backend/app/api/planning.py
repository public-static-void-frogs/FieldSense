from fastapi import APIRouter, Request

from app.api.auth import CurrentUser
from app.api.dependencies import FieldId, Responses, Store
from app.schemas.planning import (
    EventResponse,
    FieldStrategy,
    PlannedEvent,
    PlanningContext,
    RotationPlan,
    StrategyResponse,
)
from app.services import planning as service

router = APIRouter(tags=["planning"])


@router.get("/planning/context", response_model=PlanningContext)
def context(user: CurrentUser):
    return service.context(user)


@router.get("/planning/events", response_model=list[PlannedEvent])
def events(store: Store, request: Request, user: CurrentUser):
    return service.system_events(store, request.app.state.calendar, user.settings)


@router.get("/planning/responses", response_model=dict[str, EventResponse])
def responses(responses: Responses):
    return responses.all()


@router.get("/fields/{field_id}/events", response_model=list[PlannedEvent])
def field_events(field_id: FieldId, store: Store, request: Request, user: CurrentUser):
    return service.field_events(store, field_id, request.app.state.calendar, user.settings)


@router.get("/fields/{field_id}/rotation", response_model=RotationPlan)
def rotation(field_id: FieldId, store: Store, request: Request, user: CurrentUser):
    return service.rotation(store, field_id, request.app.state.strategy, user.settings)


@router.get("/fields/{field_id}/strategy", response_model=FieldStrategy)
def strategy(field_id: FieldId, store: Store, request: Request, user: CurrentUser):
    return service.strategy(store, field_id, request.app.state.strategy, user.settings)


@router.put("/fields/{field_id}/strategy/response", response_model=dict[str, EventResponse])
def respond(
    field_id: FieldId,
    input: StrategyResponse,
    store: Store,
    responses: Responses,
    request: Request,
    user: CurrentUser,
):
    """Accept or decline every calendar event of the field; ``proposed`` clears the decisions."""
    return service.respond(
        store, responses, field_id, input.status, request.app.state.calendar, user.settings
    )
