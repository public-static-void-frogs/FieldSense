from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

MoistureSource = Literal["openmeteo", "power"]
MoistureFrequency = Literal["daily", "hourly"]


class CurrentSoilMoisture(BaseModel):
    coordinates: tuple[float, float]
    grid_point: tuple[float, float] | None
    time_utc: datetime | None
    layers: dict[str, float | None]
    profile_mean: float | None
    unit: Literal["m3/m3"] = "m3/m3"


class MoistureStats(BaseModel):
    n: int
    mean: float
    min: float
    max: float
    p10: float
    p50: float
    p90: float


class MoistureObservation(BaseModel):
    date: date
    time_utc: datetime | None = None
    values: dict[str, float | None]


class SoilMoistureHistory(BaseModel):
    coordinates: tuple[float, float]
    source: MoistureSource
    frequency: MoistureFrequency
    start: date
    end: date
    unit: Literal["m3/m3", "fraction_of_saturation"]
    series: list[MoistureObservation]
    stats: dict[str, MoistureStats]


class SoilMoistureComparison(BaseModel):
    current: CurrentSoilMoisture
    window_days: int
    years: dict[int, float]
    unavailable_years: list[int]
    past_mean: float | None
    anomaly: float | None
    percentile: float | None
