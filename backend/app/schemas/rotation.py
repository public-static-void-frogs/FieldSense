"""Response contract of the rotation advice. Codes and numbers only: wording is the client's."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic import Field as Value

Priority = Literal["water", "soil", "erosion", "income", "pest_break"]


class SoilSurvey(BaseModel):
    """The farmer's own soil test. pH and organic matter replace the soil survey estimate."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    sampledOn: date | None = None
    ph: float | None = Value(default=None, ge=3, le=10)
    organicMatterPct: float | None = Value(default=None, ge=0, le=30)
    phosphorusPpm: float | None = Value(default=None, ge=0, le=1000)
    potassiumPpm: float | None = Value(default=None, ge=0, le=5000)
    # how the laboratory measured them; the categories differ (defaults: bray_p1, dried)
    phosphorusTest: Literal["bray_p1", "mehlich3_colorimetric", "mehlich3_icp", "olsen"] | None = (
        None
    )
    potassiumSample: Literal["dried", "moist"] | None = None

    @model_validator(mode="after")
    def has_a_measurement(self):
        measured = (self.ph, self.organicMatterPct, self.phosphorusPpm, self.potassiumPpm)
        if all(value is None for value in measured):
            raise ValueError("A soil survey needs at least one measurement")
        return self


class SeasonResult(BaseModel):
    """What the farmer grew in one past season, and what it yielded."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    year: int = Value(ge=1980, le=2100)
    crop: str = Value(min_length=1, max_length=64)  # catalog crop id
    yieldPerAcre: float | None = Value(default=None, gt=0, le=1000)  # bu/acre; hay in ton/acre


class SeasonResults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: list[SeasonResult] = Value(max_length=60)

    @model_validator(mode="after")
    def one_per_year(self):
        years = [r.year for r in self.results]
        if len(years) != len(set(years)):
            raise ValueError("Only one result per year")
        return self


class OwnYieldPoint(BaseModel):
    year: int
    yieldPerAcre: float
    referenceYieldPerAcre: float  # the county, state or reference yield of that year


class OwnYieldLevel(BaseModel):
    """How the farmer's yields moved the expected yield of a crop."""

    crop: str
    yieldUnit: str
    ratio: float  # field level / reference level; fewer than 4 years are filled at 1.0
    expectedYieldPerAcre: float
    points: list[OwnYieldPoint]


class SoilYieldLevel(BaseModel):
    """How the soil productivity index moved the expected yield of a crop within the county."""

    crop: str
    index: Literal["nccpi_corn", "nccpi_soy"]  # NRCS NCCPI 3.0 submodel, 0 to 1
    fieldIndex: float
    countyIndex: float  # mean over the sampled cropland fields of the county
    countyFields: int
    ratio: float  # field level / county level, within 0.85 to 1.15
    expectedYieldPerAcre: float
    verified: bool  # False: the slope is our own estimate between counties


class SoilInput(BaseModel):
    """A soil value the advice used, and whether it is the farmer's test or the soil survey."""

    id: Literal["ph", "organicMatterPct", "phosphorusPpm", "potassiumPpm"]
    value: float
    source: Literal["survey", "ssurgo"]
    # empty: stored, not in the calculation
    usedIn: list[Literal["rules", "soil_carbon", "fertilizer_cost"]]


class CropEconomics(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    crop: str = Value(min_length=1, max_length=64)  # catalog crop id
    priceUsd: float | None = Value(default=None, gt=0, le=1000)  # per bushel; hay per ton
    # production cost per acre, land excluded: conventional tillage, after a different crop
    costUsdPerAcre: float | None = Value(default=None, ge=0, le=5000)


class FieldEconomics(BaseModel):
    """The farmer's own price, cost and rent. What is left out keeps the USDA average."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    landRentUsdPerAcre: float | None = Value(default=None, ge=0, le=2000)
    crops: list[CropEconomics] = Value(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def one_per_crop(self):
        crops = [c.crop for c in self.crops]
        if len(crops) != len(set(crops)):
            raise ValueError("Only one entry per crop")
        return self


class LandRentDefault(BaseModel):
    usdPerAcre: float
    year: int
    level: Literal["county", "state", "ers_region"]
    source: Literal["nass_cash_rents", "ers_land_opportunity_cost"]


class CropEconomicsDefault(BaseModel):
    crop: str
    priceUsd: float
    priceUnit: str
    priceLevel: str
    costUsdPerAcre: float
    costLevel: Literal["ers_region", "national", "state_budget"]
    costYear: int | None
    costItems: dict[str, float] | None  # USD per acre; ERS items, land excluded


class EconomicsDefaults(BaseModel):
    costRegion: str | None  # USDA ERS farm resource region
    landRent: LandRentDefault | None
    irrigatedLandRent: LandRentDefault | None
    crops: list[CropEconomicsDefault]


class EconomicsView(BaseModel):
    inputs: FieldEconomics | None
    defaults: EconomicsDefaults


class PlanCropEconomics(BaseModel):
    crop: str
    priceUsd: float
    priceSource: Literal["farmer", "planning"]
    costUsdPerAcre: float  # conventional tillage, after a different crop; rent not included
    costSource: Literal["farmer", "tables"]
    soilTestCostChangeUsdPerAcre: float  # part of costUsdPerAcre


class PlanEconomics(BaseModel):
    landRentUsdPerAcre: float  # charged in every season's cost; 0 when the farmer gave none
    landRentSource: Literal["farmer", "not_charged"]
    crops: list[PlanCropEconomics]


class SoilTestCrop(BaseModel):
    crop: str
    rateLbPerAcre: float
    maintenanceRateLbPerAcre: float
    costChangeUsdPerAcre: float


class SoilTestEffect(BaseModel):
    """A soil-test nutrient: its category and what the recommended rate does to the cost."""

    nutrient: Literal["phosphorus", "potassium"]
    ppm: float
    test: str
    category: Literal["very_low", "low", "optimum", "high", "very_high"]
    yieldResponseProbability: float
    fertilizerUnit: str
    fertilizerUsdPerLb: float
    calibration: Literal["iowa", "iowa_applied_elsewhere"]
    verified: bool
    crops: list[SoilTestCrop]


class PlanStep(BaseModel):
    """One season of a plan, USD per acre. `objective` = net - risk penalty + soil value."""

    season: int
    crop: str
    tillage: Literal["conventional", "strip_till", "no_till"]
    coverCrop: Literal["none", "rye"]  # grown before this crop
    autumnBefore: Literal["none", "sow_cover_crop", "sow_winter_crop", "keep_stand"]
    objectiveUsdPerAcre: float
    netUsdPerAcre: float  # revenue less production cost, land excluded
    worstYearUsdPerAcre: float
    bestYearUsdPerAcre: float
    worstYear: int
    revenueUsdPerAcre: float
    costUsdPerAcre: float
    # seed, fertilizer, chemicals, fuel, repairs, custom work, interest (plus cover crop and
    # rent when charged): the part of costUsdPerAcre spent on the crop in the season. None when
    # the budget does not give the split or the cost is the farmer's own.
    operatingCostUsdPerAcre: float | None = None
    riskPenaltyUsdPerAcre: float
    soilValueUsdPerAcre: float
    yieldPerAcre: float
    yieldUnit: str
    rules: list[str]


class PlanAutumn(BaseModel):
    """What the plan asks for between this harvest and winter."""

    action: Literal["none", "sow_cover_crop", "sow_winter_crop", "keep_stand"]
    species: str | None
    establishment: Literal["reliable", "marginal", "unlikely"] | None
    ryeCoverGainUsdPerAcre: float | None  # plan value with a rye cover crop less without
    ryeCoverEstablishment: Literal["reliable", "marginal", "unlikely"] | None


class SimulatedYear(BaseModel):
    year: int
    netUsdPerAcre: float


class SimulatedOutcome(BaseModel):
    """The first season if this past year's weather and (inflation-adjusted) price came again."""

    year: int
    probability: float
    netUsdPerAcre: float  # revenue - production cost; land is not charged
    yieldPerAcre: float
    priceUsd: float
    yieldMode: Literal["observed", "modelled", "none"]


class SimulatedSpread(BaseModel):
    lossProbability: float  # share of results below the full economic cost
    operatingLossProbability: float | None = None  # below the operating costs alone
    meanUsdPerAcre: float
    p10UsdPerAcre: float  # one result in ten is worse than this
    p50UsdPerAcre: float
    p90UsdPerAcre: float
    worst: SimulatedYear
    best: SimulatedYear


class YieldSpread(BaseModel):
    unit: str
    meanPerAcre: float
    p10PerAcre: float
    p50PerAcre: float
    p90PerAcre: float


class SimulatedFirstSeason(SimulatedSpread):
    """The forecast for the coming season: each past year weighted by its odds of recurring."""

    years: int
    yieldPerAcre: YieldSpread
    planningPriceUsd: float
    observedYieldYears: int  # years whose yield is a county or state record, not a hazard model
    beatsTopProbability: float | None = None  # share of years it earns >= the first-ranked crop
    outcomes: list[SimulatedOutcome]


class SimulatedPlan(SimulatedSpread):
    """The whole plan started in each past year and run through the years that followed it."""

    runs: int


class PlanSimulation(BaseModel):
    firstSeason: SimulatedFirstSeason
    plan: SimulatedPlan | None = None


class PlanCrop(BaseModel):
    """The best plan that starts with this crop."""

    crop: str
    rank: int
    tier: Literal["top", "alternative"]
    demoted: Literal["autumn_establishment_unlikely"] | None = None
    planObjectiveUsdPerAcre: float  # total over the seasons
    # learned plans only: how far the plan is below the exact optimum starting with this crop
    belowOptimumUsdPerAcre: float | None = None
    planNetUsdPerAcre: float
    autumn: PlanAutumn
    steps: list[PlanStep]
    simulation: PlanSimulation


class PlanYears(BaseModel):
    source: Literal["climate_record", "field_seasons", "price_years"]
    count: int
    first: int
    last: int


class YearOdds(BaseModel):
    """How the past years are weighted for the coming season."""

    method: Literal["analog_years", "equal"]
    effectiveYears: float  # 1 / sum(p^2): how many years really carry the forecast
    startsAfter: int | None = None  # the year whose end-of-season state the analogs are matched to
    signals: list[str] = []


class PlanPlanner(BaseModel):
    """Who planned the seasons after the first, and whether a learned policy is installed."""

    requested: Literal["exact", "learned"]
    used: Literal["exact", "learned"]
    learnedAvailable: bool
    learnedUnavailable: (
        Literal["no_policy_file", "torch_not_installed", "policy_does_not_fit"] | None
    ) = None


class RotationPlan(BaseModel):
    status: Literal["ok", "no_modellable_crop"]
    objective: str | None = None
    method: Literal["dynamic_programming_fixed_sequence", "learned_policy"] | None = None
    planner: PlanPlanner | None = None
    seasons: int
    firstSeason: int | None = None
    weights: dict[str, float] = {}
    years: PlanYears | None = None
    costRegion: str | None = None
    yearOdds: YearOdds | None = None
    ownYields: list[OwnYieldLevel] = []
    soilYield: list[SoilYieldLevel] = []
    economics: PlanEconomics | None = None
    soilTest: list[SoilTestEffect] = []
    crops: list[PlanCrop]
    notModelled: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []


class HistorySource(BaseModel):
    kind: Literal["cdl", "declared", "none"]
    seasons: int
    declaredSeasons: int = 0
    firstYear: int | None
    lastYear: int | None
    satelliteEstimate: bool
    unknownCdlCodes: list[int]


class SummarySource(BaseModel):
    """Whose weather, drought and county record the field's seasons are read from."""

    kind: Literal["own", "weather_cell", "nearby_cell", "none"]
    distanceKm: float | None = None


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
    rank: int  # by the plan's return; crops the plan cannot price come last
    riskRank: int  # by the rule engine's risk score
    tier: Literal["top", "alternative", "not_modelled"]
    notModelledCode: str | None = None
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
    summarySource: SummarySource | None = None
    weatherRecord: WeatherRecord | None = None
    offSeason: OffSeason | None = None
    scoring: dict[str, Any]
    dataGaps: list[dict[str, Any]]
    candidates: list[Candidate]
    seasonTiming: SeasonTiming | None = None
    soilInputs: list[SoilInput] = []
    plan: RotationPlan
