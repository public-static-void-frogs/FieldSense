from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic import Field as Value

from app.schemas.geometry import Geometry
from app.schemas.section_analysis import Coordinate

Crop = Literal["Winter wheat", "Corn", "Soybeans", "Alfalfa", "Grassland/Pasture"]


class CreateField(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    parcelId: int | None = Value(default=None, gt=0, strict=True)
    name: str | None = Value(default=None, min_length=1, max_length=60, deprecated=True)
    crop: Crop
    area: float = Value(gt=0)
    geometry: Geometry
    planted: date | None = None
    properties: "PropertyData | None" = None
    health: int | None = Value(default=None, ge=0, le=100, strict=True)
    moisture: int | None = Value(default=None, ge=0, le=100, strict=True)
    nitrogen: int | None = Value(default=None, ge=0, strict=True)
    status: Literal["Healthy", "Needs attention", "Critical"] | None = None


class CropAreaInput(BaseModel):
    crop: Crop
    geometry: "CropAreaPolygon"


class CropAreaPolygon(BaseModel):
    type: Literal["Polygon"]
    coordinates: list[list[Coordinate]] = Value(min_length=1)

    @field_validator("coordinates")
    @classmethod
    def closed_rings(cls, rings):
        if sum(map(len, rings)) > 50_000 or any(
            len(ring) < 4 or ring[0] != ring[-1] for ring in rings
        ):
            raise ValueError("Crop boundaries need closed rings and at most 50,000 coordinates")
        return rings


class SaveCropAreas(BaseModel):
    areas: list[CropAreaInput] = Value(min_length=1, max_length=600)


class CropBoundary(BaseModel):
    type: Literal["MultiPolygon"]
    coordinates: list[list[list[tuple[float, float]]]]


class Field(CreateField):
    id: UUID
    name: str
    boundary: CropBoundary | None = None
    crop: str | None
    sourceProperties: dict | None = None
    sourceId: str | None = None
    locationKind: Literal["user_point", "interior_point", "crop_area"] = "user_point"
    sourceYear: int | None = None
    county: str | None = None
    stateFips: str | None = None
    countyFips: str | None = None


class Parcel(BaseModel):
    id: int
    name: str
    crop: Crop
    area: float
    soilType: str | None = None


class CropOption(BaseModel):
    value: Crop
    label: str


class FieldProperties(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    soilType: str | None = None
    soilPh: float | None = None
    phosphorus: float | None = None
    potassium: float | None = None
    organicMatter: float | None = None
    soilTemperature: float | None = None
    conductivity: float | None = None
    cationExchange: float | None = None
    bulkDensity: float | None = None
    rootingDepth: float | None = None
    variety: str | None = None
    emergence: float | None = None
    plantDensity: float | None = None
    vegetationIndex: float | None = None
    yieldTarget: float | None = None
    harvestWindow: str | None = None
    elevation: float | None = None
    slope: float | None = None
    drainage: str | None = None
    irrigation: str | None = None
    lastIrrigation: str | None = None
    waterApplied: float | None = None
    rainfall: float | None = None
    waterCapacity: float | None = None


class PropertyData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    soil: FieldProperties = Value(default_factory=FieldProperties)
    crop: FieldProperties = Value(default_factory=FieldProperties)
    growthStage: str | None = None
    lastSample: str | None = None
    cultivationPractice: str | None = None
    tenure: str | None = None


class LandEvent(BaseModel):
    id: UUID
    fieldId: UUID
    date: str
    category: str
    title: str
    description: str
    measurements: list[str] = []
    attention: bool | None = None


class CropSeason(BaseModel):
    id: UUID
    fieldId: UUID
    cropId: UUID
    year: int
    crop: str
    planted: str
    harvested: str
    yield_: str = Value(alias="yield")
    soilCondition: str


class FieldHistory(BaseModel):
    events: list[LandEvent]
    seasons: list[CropSeason]


class Recommendation(BaseModel):
    title: str
    description: str
    nextStep: str


CreateField.model_rebuild()
Field.model_rebuild()
