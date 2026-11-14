from typing import Annotated
from uuid import UUID

from fastapi import Depends, Path

from app.api.auth import CurrentUser, Database
from app.repositories.fields import FieldRepository


def repository(database: Database, user: CurrentUser) -> FieldRepository:
    return FieldRepository(database, user.id)


Store = Annotated[FieldRepository, Depends(repository)]
FieldId = UUID
ParcelId = Annotated[int, Path(gt=0)]
