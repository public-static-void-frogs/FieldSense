"""Yield estimates (SI, t/ha) with a pluggable model and gross revenue from reference prices."""

from dataclasses import dataclass, field, replace
from typing import Protocol

from rule_engine.catalog import Crop
from rule_engine.reference import PriceQuote, ReferenceTables
from rule_engine.summary import SeasonSummary

HA_PER_ACRE = 0.404686


@dataclass(frozen=True)
class YieldEstimate:
    low_t_ha: float
    mid_t_ha: float
    high_t_ha: float
    method: str  # county_trend | reference_range
    source: str
    level: str  # county | state | group
    verified: bool
    factors: tuple[str, ...] = ()  # rule ids whose yield_factor was applied
    inputs: dict = field(default_factory=dict)  # values the range was built from (native units)


class YieldModel(Protocol):
    def predict(
        self,
        crop: Crop,
        seasons: list[SeasonSummary],
        reference: ReferenceTables,
        region: str,
    ) -> YieldEstimate | None: ...


def _to_t_ha(crop: Crop, value: float, unit: str) -> float | None:
    if unit.startswith("bu") and crop.bu_to_t_ha:
        return value * crop.bu_to_t_ha
    if unit.startswith("ton") and crop.ton_to_t_ha:
        return value * crop.ton_to_t_ha
    return None


def display_yield(crop: Crop, t_ha: float, units: str) -> tuple[float, str]:
    """Convert t/ha to the crop's display unit for imperial users, else keep t/ha."""
    if units != "imperial":
        return round(t_ha, 2), "t/ha"
    factor = crop.bu_to_t_ha or crop.ton_to_t_ha
    if factor:
        return round(t_ha / factor, 1), crop.display_unit
    return round(t_ha, 2), "t/ha"


class CountyTrendYieldModel:
    """Corn and soybeans: county yield (current, last year, 3-year mean). Others: reference CSV."""

    COLUMNS = {"corn": "yield_corn", "soybeans": "yield_soy"}

    def predict(self, crop, seasons, reference, region):
        prefix = self.COLUMNS.get(crop.id)
        latest = seasons[-1] if seasons else None
        if prefix and latest is not None:
            named = {
                "current": latest.scalars.get(f"{prefix}_bu_ac"),
                "lag1": latest.scalars.get(f"{prefix}_lag1_bu_ac"),
                "prev3Mean": latest.scalars.get(f"{prefix}_prev3_bu_ac"),
            }
            values = [v for v in named.values() if v is not None]
            if values:
                low, high = min(values), max(values)
                mid = sum(values) / len(values)
                return YieldEstimate(
                    low_t_ha=low * crop.bu_to_t_ha,
                    mid_t_ha=mid * crop.bu_to_t_ha,
                    high_t_ha=high * crop.bu_to_t_ha,
                    method="county_trend",
                    source="USDA NASS county yield survey via field dataset",
                    level="county",
                    verified=True,
                    inputs={
                        "countyFips": latest.county_fips,
                        "season": latest.year,
                        "unit": "bu/acre",
                        **{k: round(float(v), 1) for k, v in named.items() if v is not None},
                    },
                )
        ref = reference.yield_reference(crop.id, region)
        if ref is None:
            return None
        converted = [_to_t_ha(crop, v, ref.unit) for v in (ref.low, ref.mid, ref.high)]
        if any(v is None for v in converted):
            return None
        return YieldEstimate(
            low_t_ha=converted[0],
            mid_t_ha=converted[1],
            high_t_ha=converted[2],
            method="reference_range",
            source=ref.source,
            level=ref.level,
            verified=ref.verified,
            inputs={
                "region": region,
                "unit": ref.unit,
                "low": ref.low,
                "mid": ref.mid,
                "high": ref.high,
                "asOf": ref.as_of,
            },
        )


def apply_yield_factors(
    estimate: YieldEstimate, factors: list[tuple[str, tuple[float, float]]]
) -> YieldEstimate:
    """Multiply the range by every (rule_id, (low, high)) factor; low by low, high by high."""
    low, mid, high = estimate.low_t_ha, estimate.mid_t_ha, estimate.high_t_ha
    for _, (f_low, f_high) in factors:
        low *= f_low
        high *= f_high
        mid *= (f_low + f_high) / 2
    return replace(
        estimate,
        low_t_ha=low,
        mid_t_ha=mid,
        high_t_ha=high,
        factors=estimate.factors + tuple(rule_id for rule_id, _ in factors),
    )


@dataclass(frozen=True)
class Revenue:
    low_usd: float
    mid_usd: float
    high_usd: float
    price_usd: float
    price_unit: str
    price_source: str
    price_as_of: str
    price_verified: bool
    area_ha: float
    price_level: str = "state"


def gross_revenue(
    estimate: YieldEstimate, price: PriceQuote | None, crop: Crop, area_ha: float
) -> Revenue | None:
    """Gross revenue for the whole field, USD. No costs: those vary too much per farm."""
    if price is None or area_ha <= 0:
        return None
    factor = crop.bu_to_t_ha if price.unit.startswith("bu") else crop.ton_to_t_ha
    if not factor:
        return None
    acres = area_ha / HA_PER_ACRE

    def usd(t_ha: float) -> float:
        return round(t_ha / factor * acres * price.price_usd, 0)

    return Revenue(
        low_usd=usd(estimate.low_t_ha),
        mid_usd=usd(estimate.mid_t_ha),
        high_usd=usd(estimate.high_t_ha),
        price_usd=price.price_usd,
        price_unit=price.unit,
        price_source=price.source,
        price_as_of=price.as_of,
        price_verified=price.verified,
        area_ha=area_ha,
        price_level=price.level,
    )
