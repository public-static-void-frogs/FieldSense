from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StrategyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["proposed", "accepted", "declined"]


class EventResponse(BaseModel):
    status: Literal["accepted", "declined"]
    fingerprint: str


class PlanningContext(BaseModel):
    today: str


class LabelValue(BaseModel):
    label: str
    value: str


class RotationPlan(BaseModel):
    id: UUID
    nextCropId: UUID
    followingCropId: UUID
    fieldId: UUID
    currentCrop: str
    nextCrop: str
    followingCrop: str
    confidence: int
    sowingDate: str
    windowEnd: str
    followingDate: str
    dateExplanation: str
    reasons: list[str]
    inputs: list[LabelValue]


class PlannedEvent(BaseModel):
    id: UUID
    fieldId: UUID
    fieldName: str
    date: str
    category: str
    title: str
    description: str
    priority: str
    duration: str
    rationale: str


class StrategyStep(BaseModel):
    event: PlannedEvent
    checkpoint: str


class Forecast(BaseModel):
    date: str
    stage: str
    progress: float
    health: int
    currentHealth: int
    healthImprovement: list[int]
    range: list[int]


class Comparison(BaseModel):
    name: str
    current: int
    projected: int


class Technical(BaseModel):
    key: str
    parameter: str
    value: str
    role: str


class Contingency(BaseModel):
    condition: str
    action: str


class FieldStrategy(BaseModel):
    plan: RotationPlan
    events: list[PlannedEvent]
    steps: list[StrategyStep]
    forecast: list[Forecast]
    comparison: list[Comparison]
    technicals: list[Technical]
    contingencies: list[Contingency]
