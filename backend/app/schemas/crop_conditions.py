"""Replaceable crop-model contract. Scores are suitability, not probabilities of yield loss."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

WeatherMetric = Literal["temperature", "rainfall", "moisture", "humidity", "wind"]
RiskLevel = Literal["good", "caution", "high", "unknown"]
InputCoverage = Literal["complete", "partial", "unavailable"]
SoilInput = Literal["soilType", "soilPh", "organicMatter", "waterCapacity", "drainage"]


class CropMetricBounds(BaseModel):
    unit: str
    criticalLow: float | None
    goodLow: float
    ideal: float
    goodHigh: float
    criticalHigh: float | None

    @model_validator(mode="after")
    def ordered_bounds(self):
        if not self.goodLow <= self.ideal <= self.goodHigh:
            raise ValueError("Ideal must be inside the inclusive good range")
        if self.criticalLow is not None and self.criticalLow >= self.goodLow:
            raise ValueError("Critical low must be below the good range")
        if self.criticalHigh is not None and self.criticalHigh <= self.goodHigh:
            raise ValueError("Critical high must be above the good range")
        return self


class CropClimateContext(BaseModel):
    source: Literal["forecast_window", "history_window"]
    startDate: str
    endDate: str
    meanHigh: float | None
    meanLow: float | None
    meanHumidity: float | None
    meanDailyRainfall: float | None
    sampleDays: int


class CropSoilContext(BaseModel):
    soilType: str | None = None
    soilPh: float | None = None
    organicMatter: float | None = None
    waterCapacity: float | None = None
    drainage: str | None = None


class CropAssessmentContext(BaseModel):
    fieldId: UUID
    fieldName: str
    crop: str
    latitude: float
    longitude: float
    soil: CropSoilContext
    soilCoverage: InputCoverage = Field(
        default="complete",
        description="Availability of field soil inputs for optional adjustments.",
    )
    climate: CropClimateContext


class CropModelMetadata(BaseModel):
    id: str
    version: str
    kind: Literal["heuristic_stub", "rule_engine", "ml_model"]
    scoreMeaning: Literal["suitability_0_bad_100_good"] = "suitability_0_bad_100_good"


class CropAssessment(BaseModel):
    model: CropModelMetadata
    context: CropAssessmentContext
    bounds: dict[WeatherMetric, CropMetricBounds] = Field(
        description="Window reference limits; daily assessments carry the limits used for each reading."
    )

    @field_validator("bounds")
    @classmethod
    def complete_bounds(cls, value):
        if set(value) != {"temperature", "rainfall", "moisture", "humidity", "wind"}:
            raise ValueError("Bounds must cover all five weather metrics")
        return value


class CropRuleDriver(BaseModel):
    ruleId: str
    input: WeatherMetric | SoilInput
    value: float | str
    unit: str | None


class CropRiskAlert(BaseModel):
    metric: WeatherMetric
    reading: Literal["value", "low"]
    severity: Literal["caution", "high"]
    code: Literal["below_critical", "below_good", "above_good", "above_critical"]
    value: float
    boundary: float
    unit: str
    ruleId: str | None = Field(default=None, description="Stable warning family for this rule.")
    drivers: list[CropRuleDriver] = Field(
        default_factory=list, description="Observed inputs that adjusted the breached boundary."
    )


class CropMetricAssessment(BaseModel):
    riskLevel: RiskLevel
    valueRiskLevel: RiskLevel
    lowRiskLevel: RiskLevel | None = None
    suitabilityScore: float | None = Field(ge=0, le=100)


class CropDayAssessment(BaseModel):
    bounds: dict[WeatherMetric, CropMetricBounds] = Field(
        description="Daily crop limits used to assess this record and draw the chart zones."
    )
    suitabilityScore: float | None = Field(ge=0, le=100)
    riskLevel: RiskLevel
    coverage: InputCoverage
    metrics: dict[WeatherMetric, CropMetricAssessment]
    alerts: list[CropRiskAlert]

    @field_validator("metrics", "bounds")
    @classmethod
    def complete_metrics(cls, value):
        if set(value) != {"temperature", "rainfall", "moisture", "humidity", "wind"}:
            raise ValueError("Assessment must cover all five weather metrics")
        return value
