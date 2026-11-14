from fastapi import APIRouter

from app.api.auth import CurrentUser
from app.api.dependencies import FieldId, Store
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
def events(store: Store):
    return service.system_events(store)


@router.get("/planning/responses", response_model=dict[str, EventResponse])
def responses(store: Store):
    return {}


@router.get("/fields/{field_id}/events", response_model=list[PlannedEvent])
def field_events(field_id: FieldId, store: Store):
    return service.field_events(store, field_id)


@router.get("/fields/{field_id}/rotation", response_model=RotationPlan)
def rotation(field_id: FieldId, store: Store):
    return service.rotation(store, field_id)


@router.get("/fields/{field_id}/strategy", response_model=FieldStrategy)
def strategy(field_id: FieldId, store: Store):
    return service.strategy(store, field_id)


@router.put("/fields/{field_id}/strategy/response", response_model=dict[str, EventResponse])
def respond(field_id: FieldId, input: StrategyResponse, store: Store):
    service.strategy(store, field_id)
