"""Response contract of the rotation advice. Codes and numbers only: wording is the client's."""

from typing import Any, Literal

from pydantic import BaseModel
from pydantic import Field as Value

Priority = Literal["water", "soil", "erosion", "income", "pest_break"]


class HistorySource(BaseModel):
    kind: Literal["cdl", "declared", "none"]
    seasons: int
    firstYear: int | None
    lastYear: int | None
    satelliteEstimate: bool
    unknownCdlCodes: list[int]


class HistoryYear(BaseModel):
    year: int
    crop: str | None
    cdlCode: int | None
    source: str


class Finding(BaseModel):
    ruleId: str
    title: str
    category: str
    kind: Literal["risk", "benefit", "advisory"]
    level: str | None = None
    points: float
    yieldFactor: dict[str, float] | None = None
    evidenceStrength: str | None = None
    unverifiedTraits: list[str] = []
    needsLocalReview: bool = False
    trigger: dict[str, Any]


class Calendar(BaseModel):
    kind: str
    stages: dict[str, int | None]
    localShiftDays: dict[str, int] = {}
    localSource: str | None = None


class SoilIndicator(BaseModel):
    id: str
    value: float | str | None
    unit: str | None = None
    direction: str | None = None
    threshold: Any = None
    basis: str | None = None
    kind: str | None = None
    verified: bool | None = None
    inputs: Any = None


class YieldEstimate(BaseModel):
    low: float
    mid: float
    high: float
    unit: str
    midTHa: float | None = None
    method: str | None = None
    level: str | None = None
    verified: bool | None = None
    inputs: Any = None
    factorsApplied: list[Any] = []


class Revenue(BaseModel):
    lowUsd: float
    midUsd: float
    highUsd: float
    priceUsd: float
    priceUnit: str
    priceAsOf: str | None = None
    priceVerified: bool | None = None
    priceLevel: str | None = None
    areaHa: float
    grossOnly: bool


class Candidate(BaseModel):
    crop: str
    label: str
    group: str
    rank: int
    isIntended: bool
    score: float
    scoreBreakdown: list[dict[str, Any]]
    economicsAvailable: bool
    risks: list[Finding]
    benefits: list[Finding]
    advisories: list[Finding]
    calendar: Calendar
    soil: list[SoilIndicator]
    soilProvider: str | None = None
    yield_: YieldEstimate | None = Value(default=None, alias="yield")
    revenue: Revenue | None = None
    dataGaps: list[dict[str, Any]]
    needsLocalReview: bool


class CropChoice(BaseModel):
    id: str
    label: str
    group: str


class TimingWindow(BaseModel):
    """A date range over past years, as month-day ("MM-DD"): 10%, 50% and 90% of years."""

    early: str
    typical: str
    late: str
    method: str | None = None
    yearsFit: int | None = None
    censoredShare: float | None = None


class HeatAtFlowering(BaseModel):
    probability: float | None  # share of years with >= 2 days at >= 35 C during flowering
    low80: float | None
    high80: float | None
    meanHotDays: float | None
    vulnerable: bool


class DayRange(BaseModel):
    low: float | None
    typical: float | None
    high: float | None


class Outlook2040(BaseModel):
    """Spread over climate models, not a probability range."""

    scenario: Literal["ssp245", "ssp585"]
    heatMedian: float | None
    heatMin: float | None
    heatMax: float | None
    marginMinDays: float | None
    marginMaxDays: float | None
    models: int | None
    sowTypical: str | None


class CropTiming(BaseModel):
    stages: dict[Literal["firstWorkable", "sow", "flower", "mature"], TimingWindow]
    dateErrorDays: dict[Literal["sow", "flower", "mature"], float]
    heatAtFlowering: HeatAtFlowering
    frostBeforeMaturity: float | None
    sowingDelayMarginDays: float | None  # null: no safe delay
    workableDays: DayRange
    years: int | None
    outlook2040: list[Outlook2040]


class WaterBranch(BaseModel):
    shortfall: float | None  # share of past years below thresholdMm at sowing
    low80: float | None
    high80: float | None
    typicalMm: float | None


class WaterAtSowing(BaseModel):
    """Plant-available soil water at the next crop's sowing, bare fallow vs a rye cover crop."""

    nextCrop: str
    years: int | None
    thresholdMm: float | None
    bare: WaterBranch
    cover: WaterBranch
    coverOk: bool | None
    safeAutumnRainMm: float | None  # 0: safe in any year; null: no safe level found
    autumnRainTypicalMm: float | None


class SeasonTiming(BaseModel):
    """Climatology from the M3 batch outputs for the field's weather cell; not a forecast."""

    source: Literal["m3"]
    matchLevel: Literal["field", "cell"]
    distanceKm: float
    cellId: str
    lastSpringFrost: TimingWindow | None
    firstAutumnFrost: TimingWindow | None
    crops: dict[str, CropTiming]
    waterAtSowing: dict[str, WaterAtSowing] = {}  # keyed by the crop just harvested


class WeatherRecord(BaseModel):
    """The long weather record the weather hazards were counted over."""

    source: str
    seasons: int
    firstYear: int
    lastYear: int
    nodeLatitude: float
    nodeLongitude: float
    distanceKm: float


class OffSeasonOption(BaseModel):
    id: str
    label: str
    kind: Literal["cover_crop", "winter_cash_crop"]
    overwinters: bool
    cropId: str | None = None
    level: Literal["reliable", "marginal", "unlikely"]
    seasonsMet: int
    seasonsTotal: int
    share: float
    metric: Literal["fall_gdd0", "days_to_killing_frost"]
    minimum: float
    typical: float
    needsLocalReview: bool


class OffSeason(BaseModel):
    """What can be established between the previous crop's harvest and winter."""

    status: Literal[
        "ok",
        "previous_crop_unknown",
        "no_harvest_in_calendar",
        "no_weather_record",
        "weather_record_too_short",
    ]
    afterCrop: str | None = None
    harvestDoy: int | None = None
    seedingDoy: int | None = None
    calendarKind: str | None = None
    seasonsTotal: int = 0
    firstKillingFrostDoy: int | None = None
    options: list[OffSeasonOption] = []


class RotationAdvice(BaseModel):
    fieldId: str
    intendedCrop: str
    intendedCropSource: Literal["requested", "field_crop", "history", "default"]
    cropOptions: list[CropChoice]
    region: str
    asOf: str
    areaHa: float
    resultVersion: str
    ruleSetVersion: str
    catalogVersion: str
    units: Literal["metric", "imperial"]
    priorities: list[Priority]
    historySource: HistorySource
    history: list[HistoryYear]
    seasonsAvailable: list[int]
    weatherRecord: WeatherRecord | None = None
    offSeason: OffSeason | None = None
    scoring: dict[str, Any]
    dataGaps: list[dict[str, Any]]
    candidates: list[Candidate]
    seasonTiming: SeasonTiming | None = None
