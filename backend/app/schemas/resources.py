from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class FarmProfile(BaseModel):
    availableSeasons: list[str]
    farmName: str
    season: str
    fullName: str
    initials: str
    email: str
    role: str
    location: str
    latitude: float | None
    longitude: float | None
    locationLabel: str
    timeZone: str
    units: str
    theme: str
    language: Literal["en", "uk"]
    sessionLifetimeHours: int


class TeamMember(BaseModel):
    id: str
    name: str
    roles: str
    alt: str


class DemoSource(BaseModel):
    key: str
    name: str
    data: str
    format: str


class Notification(BaseModel):
    id: str
    kind: Literal["field", "weather"]
    severity: Literal["error", "warning", "info"]
    fieldId: UUID | None = None
    fieldName: str | None = None
    title: str
    description: str


class CropArea(BaseModel):
    name: str
    area: float
    fill: str


class Overview(BaseModel):
    trends: list[dict[str, str | int]]
    cropAreas: list[CropArea]
