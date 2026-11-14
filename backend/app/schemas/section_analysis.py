"""Replaceable section-analysis contract: WGS84 points plus georeferenced PNG imagery."""

import base64
import binascii
import struct
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Longitude = Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
Latitude = Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
Coordinate = tuple[Longitude, Latitude]


class AnalysisPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    coordinates: Coordinate


class AnalysisPolygon(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[Coordinate]] = Field(min_length=1, max_length=1)

    @field_validator("coordinates")
    @classmethod
    def closed_ring(cls, rings):
        ring = rings[0]
        if not 4 <= len(ring) <= 514 or ring[0] != ring[-1] or len(set(ring[:-1])) < 3:
            raise ValueError("A polygon needs a closed ring with at least three distinct points")
        return rings


class MapImage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataUrl: str = Field(
        max_length=12_000_000,
        description="Base64 PNG of the map imagery in image bounds; no UI overlays.",
    )
    crs: Literal["EPSG:3857"] = Field(
        description="Projection of the map image; geographic bounds are still EPSG:4326"
    )
    width: int = Field(ge=1, le=2048, strict=True)
    height: int = Field(ge=1, le=2048, strict=True)
    bounds: tuple[Longitude, Latitude, Longitude, Latitude] = Field(
        description="Image extent: west,south,east,north in EPSG:4326"
    )

    @model_validator(mode="after")
    def valid_png(self):
        west, south, east, north = self.bounds
        if west >= east or south >= north or south < -85.05112878 or north > 85.05112878:
            raise ValueError("Image bounds must have positive width and height")
        prefix = "data:image/png;base64,"
        if not self.dataUrl.startswith(prefix):
            raise ValueError("Map image must be a base64 PNG data URL")
        try:
            data = base64.b64decode(self.dataUrl[len(prefix) :], validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("Invalid image encoding") from error
        if (
            len(data) > 8 * 1024 * 1024
            or len(data) < 33
            or data[:8] != b"\x89PNG\r\n\x1a\n"
            or data[12:16] != b"IHDR"
        ):
            raise ValueError("Image must be a PNG smaller than 8 MiB")
        if struct.unpack(">II", data[16:24]) != (self.width, self.height):
            raise ValueError("Image dimensions do not match the PNG header")
        return self


class SectionAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    points: list[AnalysisPoint] = Field(min_length=1, max_length=600)
    image: MapImage
    region: AnalysisPolygon

    @model_validator(mode="after")
    def unique_points(self):
        if len({point.id for point in self.points}) != len(self.points):
            raise ValueError("Point IDs must be unique")
        west, south, east, north = self.image.bounds
        if any(
            not (
                west - 1e-8 <= p.coordinates[0] <= east + 1e-8
                and south - 1e-8 <= p.coordinates[1] <= north + 1e-8
            )
            for p in self.points
        ):
            raise ValueError("All points must lie inside the georeferenced image")
        return self


class DetectedPolygon(BaseModel):
    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[Coordinate]]


class DetectedField(BaseModel):
    id: UUID
    pointId: str
    crop: str
    classIndex: int
    cropConfidence: float
    cropProbabilities: list[float]
    cropObservationDates: list[date] = Field(min_length=16, max_length=16)
    segmentationConfidence: float
    touchesImageEdge: bool
    center: Coordinate
    geometry: DetectedPolygon
    areaHa: float = Field(gt=0)


class CropZone(BaseModel):
    id: UUID
    crop: str
    center: Coordinate
    geometry: DetectedPolygon
    areaHa: float = Field(gt=0)


class AnalysisProvenance(BaseModel):
    segmentationInputs: Literal["submitted_map_image_and_points"]
    cropInputs: Literal["sentinel-2-l2a"]
    syntheticCropInputs: Literal[False]
    sequenceShape: tuple[Literal[16], Literal[3]]
    channels: tuple[Literal["NDVI"], Literal["EVI"], Literal["NDWI"]]
    cropLabelSource: Literal["unmapped_class_indices", "training_class_mapping"]
    classLabels: list[str]
    device: str


class SkippedPoint(BaseModel):
    pointId: str
    reason: str


class SectionAnalysisResponse(BaseModel):
    requestId: UUID
    mock: Literal[False] = False
    model: Literal["sam2-tiny+tempcnn"] = "sam2-tiny+tempcnn"
    fields: list[DetectedField]
    cropZones: list[CropZone] = Field(default_factory=list)
    skippedPoints: list[SkippedPoint]
    provenance: AnalysisProvenance
