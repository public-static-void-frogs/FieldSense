from typing import Literal

from pydantic import BaseModel, JsonValue

SoilSignal = Literal["rotation", "greenness", "soil", "county"]


class SoilMetrics(BaseModel):
    years_same_crop: int | None = None
    latest_crop: str | None = None
    top_crop_5y: str | None = None
    share_top_crop_5y: float | None = None
    observed_years_5y: int | None = None
    peak_ndvi: dict[int, float] | None = None
    peak_evi: dict[int, float] | None = None
    ndvi_trend_pct_per_yr: float | None = None
    mukey: int | None = None
    soil_component: str | None = None
    drainage_class: str | None = None
    hydrologic_group: str | None = None
    om_pct_0_30cm: float | None = None
    aws0150_cm: float | None = None
    slope_pct: float | None = None
    kffact: float | None = None
    county_fips: str | None = None
    county_yield_ratio_mean: float | None = None
    county_yield_ratio_slope_pct_yr: float | None = None
    county_yield_years: int | None = None


class SoilAssessment(BaseModel):
    score: float | None
    level: Literal["low", "moderate", "high", "very_high", "unknown"]
    coverage: float
    components: dict[SoilSignal, float | None]
    drivers: list[SoilSignal]
    metrics: SoilMetrics
    notes: list[str]


class SoilDepletion(BaseModel):
    status: Literal["pending", "busy", "ready"]
    coordinates: tuple[float, float]
    assessment: SoilAssessment | None = None


class M3Match(BaseModel):
    level: Literal["field", "cell"]
    cell_id: str
    distance_km: float
    awc_mm: float | None

    # Preserve indexed-field context supplied by the lookup.
    model_config = {"extra": "allow"}


class M3Window(BaseModel):
    date_q10: str | None
    date_q50: str | None
    date_q90: str | None
    n_years_fit: int | None
    calibrated: bool | None
    model_config = {"extra": "allow"}


class M3FutureWindow(BaseModel):
    date_q50_median: str | None
    date_q50_min: str | None
    date_q50_max: str | None
    n_models: int
    model_config = {"extra": "allow"}


class M3Windows(BaseModel):
    now: dict[str, M3Window]
    future: dict[str, dict[str, M3FutureWindow]]


class M3CropRisk(BaseModel):
    n_years: int | None
    p_heat_overlap: float | None
    p_heat_lo80: float | None
    p_heat_hi80: float | None
    p_frost_before_maturity: float | None
    adaptation_margin_days: float | None
    workable_days_q50: float | None
    model_config = {"extra": "allow"}


class M3FutureRisk(BaseModel):
    p_heat_median: float | None
    p_heat_min: float | None
    p_heat_max: float | None
    margin_min: float | None
    margin_max: float | None
    n_models: int
    model_config = {"extra": "allow"}


class M3Risk(BaseModel):
    now: dict[str, M3CropRisk]
    future: dict[str, dict[str, M3FutureRisk]]


class M3Error(BaseModel):
    code: Literal["outside_coverage", "bad_input"]
    nearest_cell_km: float | None = None


class M3Insights(BaseModel):
    ok: bool
    query: dict[str, float]
    match: M3Match | None = None
    windows: M3Windows | None = None
    risk: M3Risk | None = None
    fallow_zero: dict[str, JsonValue] | None = None
    delay_scan: dict[str, JsonValue] | None = None
    meta: dict[str, JsonValue] | None = None
    warnings: list[str] = []
    error: M3Error | None = None
