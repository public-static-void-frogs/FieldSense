from math import isfinite
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class PointGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["Point"]
    coordinates: tuple[float, float]

    @field_validator("coordinates")
    @classmethod
    def valid_coordinates(cls, point):
        longitude, latitude = point
        if not (
            isfinite(longitude)
            and isfinite(latitude)
            and -180 <= longitude <= 180
            and -90 <= latitude <= 90
        ):
            raise ValueError("Coordinates must be a finite longitude/latitude pair")
        return point


Geometry = PointGeometry
