from typing import Annotated
from uuid import UUID

from fastapi import Depends, Path

from app.api.auth import CurrentUser, Database
from app.repositories.fields import FieldRepository
from app.repositories.planning import EventResponses


def repository(database: Database, user: CurrentUser) -> FieldRepository:
    return FieldRepository(database, user.id)


def event_responses(database: Database, user: CurrentUser) -> EventResponses:
    return EventResponses(database, user.id)


Store = Annotated[FieldRepository, Depends(repository)]
Responses = Annotated[EventResponses, Depends(event_responses)]
FieldId = UUID
ParcelId = Annotated[int, Path(gt=0)]
