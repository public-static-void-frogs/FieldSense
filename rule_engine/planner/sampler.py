"""Historical years as the source of randomness.

One draw is one whole historical year: its weather at the field, its yields and its prices
together, so their real co-movement (a drought year has low yield and a high price) is kept.

Yield of a crop in a drawn year, per acre in the crop's own unit:

    expected yield now  x  that year's anomaly

- anomaly "observed": the year's yield divided by the linear trend. County yields for corn and
  soybeans (USDA NASS, from the season summary), state yields for the other crops. An observed
  yield already contains that year's weather, so no hazard loss is applied on top of it.
- anomaly "modelled": used when the year has no observed yield. The product of the published
  losses in data/weather_yield_response.csv for the hazards that occurred in that season.
- anomaly "none": no observed yield and no response row; the expected yield is used as is.

Prices are the year's marketing-year price in constant dollars (deflated with the consumer
price index, data/cpi_u.csv), rescaled so that the crop's mean over the history equals the
engine's current planning price. Real crop prices have fallen since the 1980s, so early years
are drawn as high-price years and recent years as below the mean.

Prices and state yields come from planner/data/nass_long_history.csv (since 1980, every state)
where it has the series, otherwise from the rule engine's nass_reference_history.csv.
"""

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from random import Random

from rule_engine.engine import RotationAdvisor
from rule_engine.planner.adapter import RuleAdapter, WeatherPart
from rule_engine.planner.context import FieldContext
from rule_engine.planner.tables import Response, load_responses

HISTORY_CSV = Path(__file__).parents[1] / "data" / "nass_reference_history.csv"
LONG_HISTORY_CSV = Path(__file__).parent / "data" / "nass_long_history.csv"
CPI_CSV = Path(__file__).parent / "data" / "cpi_u.csv"  # BLS CPI-U, all items, 1982-84 = 100
COUNTY_COLUMNS = {"corn": "yield_corn_bu_ac", "soybeans": "yield_soy_bu_ac"}
MIN_TREND_POINTS = 5


@dataclass(frozen=True)
class CropYear:
    yield_per_acre: float
    price: float  # USD per yield unit
    mode: str  # observed | modelled | none
    anomaly: float
    modelled_factor: float  # what the response table gives for this season (1.0 = no loss)
    drought_loss: float  # the drought share of the modelled loss, for the soil water modifier
    paid_rules: tuple[str, ...]  # hazard rules whose effect is carried by the yield
    weather: WeatherPart | None


@dataclass(frozen=True)
class Year:
    year: int
    crops: dict[str, CropYear]


@dataclass(frozen=True)
class CropBasis:
    unit: str  # bu | ton (per acre)
    expected_yield: float
    yield_level: str  # county | state | reference
    yield_verified: bool
    price: float
    price_level: str
    price_years: int
    observed_years: int
    notes: tuple[str, ...] = field(default=())


def _trend(points: dict[int, float]):
    """Least-squares line through (year, value); a flat mean when there are too few points."""
    years = sorted(points)
    mean_y = sum(points.values()) / len(points)
    if len(years) < MIN_TREND_POINTS:
        return lambda year: mean_y
    mean_x = sum(years) / len(years)
    sxx = sum((x - mean_x) ** 2 for x in years)
    slope = sum((x - mean_x) * (points[x] - mean_y) for x in years) / sxx
    return lambda year: mean_y + slope * (year - mean_x)


@lru_cache(maxsize=1)
def _history_rows() -> tuple[dict, ...]:
    """Long-history rows first, so `_series` finds them before the engine's shorter series."""
    rows: list[dict] = []
    for path in (LONG_HISTORY_CSV, HISTORY_CSV):
        if path.exists():
            with path.open(newline="") as handle:
                rows += list(csv.DictReader(handle))
    return tuple(rows)


@lru_cache(maxsize=1)
def _cpi() -> dict[int, float]:
    with CPI_CSV.open(newline="") as handle:
        return {int(row["year"]): float(row["cpi_u"]) for row in csv.DictReader(handle)}


def price_levels(history: dict[int, float]) -> dict[int, float]:
    """{year: price in constant dollars}, scaled to mean 1. Years without a CPI value are left out."""
    cpi = _cpi()
    real = {y: p / cpi[y] for y, p in history.items() if y in cpi}
    mean = sum(real.values()) / len(real)
    return {y: v / mean for y, v in real.items()}


def _series(rows, kind: str, crop: str, region: str) -> tuple[dict[int, float], str, str]:
    """({year: value}, unit, geography) preferring the field's state, then national, then Iowa.

    A price series that covers under 80 % of the years of the longest candidate is passed over
    (NASS stopped reporting some state prices), so the drawn years keep a price.
    """
    candidates = []
    for geography in (region, "US", "IA"):
        match = [
            r
            for r in rows
            if r["kind"] == kind and r["crop"] == crop and r["geography"] == geography
        ]
        if not match:
            continue
        first = match[0]  # one series per geography: the first file that has it defines it
        values = {
            int(r["year"]): float(r["value"])
            for r in match
            if r["unit"] == first["unit"]
            and r.get("nass_short_desc") == first.get("nass_short_desc")
        }
        candidates.append((values, first["unit"], geography))
    if not candidates:
        return {}, "", ""
    if kind == "price":
        longest = max(len(values) for values, _, _ in candidates)
        candidates = [c for c in candidates if len(c[0]) >= 0.8 * longest]
    return candidates[0]


def modelled_loss(crop: str, weather: WeatherPart, responses: list[Response]):
    """(yield factor, drought part of the loss, engine rules paid for by the yield)."""
    factor, drought, paid = 1.0, 0.0, set()
    evaluated = set(weather.evaluated)
    hits = {hit.rule: hit for hit in weather.hazards}
    weekly = {"per_drought_week": weather.drought_weeks, "per_d4_week": weather.d4_weeks}
    drought_total, drought_cap = 0.0, 1.0
    for row in responses:
        if row.applies_to != crop:
            continue
        if row.kind in weekly:
            weeks = weekly[row.kind]
            if weeks is None:
                continue
            paid.add(row.rule)
            drought_total += weeks * row.loss
            drought_cap = min(drought_cap, row.cap)
            continue
        if row.rule not in evaluated:
            continue
        paid.add(row.rule)
        hit = hits.get(row.rule)
        if hit is None:
            continue
        loss = row.loss if row.kind == "per_hit" else row.loss * hit.value
        factor *= 1.0 - min(row.cap, loss)
    drought = min(drought_cap, drought_total)
    return factor * (1.0 - drought), drought, tuple(sorted(paid))


class YearSampler:
    def __init__(
        self,
        context: FieldContext,
        advisor: RotationAdvisor,
        adapter: RuleAdapter,
        crops: list[str],
        responses: list[Response] | None = None,
        now: int | None = None,
    ):
        self.context = context
        self.responses = responses if responses is not None else load_responses()
        rows = _history_rows()
        seasons = context.seasons
        self.basis: dict[str, CropBasis] = {}
        self.unavailable: dict[str, str] = {}
        prices: dict[str, dict[int, float]] = {}
        anomalies: dict[str, dict[int, float]] = {}
        for crop_id in crops:
            quote = advisor.reference.price(crop_id, context.region)
            if quote is None:
                self.unavailable[crop_id] = "no_price"
                continue
            unit = "bu" if quote.unit.startswith("bu") else "ton"
            notes = []

            observed: dict[int, float] = {}
            level = "reference"
            column = COUNTY_COLUMNS.get(crop_id)
            if column:
                observed = {
                    y: float(s.scalars[column])
                    for y, s in seasons.items()
                    if s.scalars.get(column) is not None
                }
                level = "county"
            if not observed:
                observed, y_unit, geography = _series(rows, "yield", crop_id, context.region)
                level = "state"
                if observed and (geography != context.region or not y_unit.startswith(unit)):
                    observed = {}  # another state's yield level is not this field's
            verified = True
            if observed:
                trend = _trend(observed)
                last = max(observed)
                expected = trend(min(now or last, last))
                anomalies[crop_id] = {y: v / trend(y) for y, v in observed.items() if trend(y) > 0}
            else:
                ref = advisor.reference.yield_reference(crop_id, context.region)
                if ref is None or not ref.unit.startswith(unit):
                    self.unavailable[crop_id] = "no_yield"
                    continue
                expected, level, verified = ref.mid, "reference", ref.verified
                notes.append("no_yield_history")
                anomalies[crop_id] = {}

            history, p_unit, geography = _series(rows, "price", crop_id, context.region)
            if history and p_unit.endswith(unit):
                prices[crop_id] = {
                    y: level * quote.price_usd for y, level in price_levels(history).items()
                }
                if geography != context.region:
                    notes.append(f"price_history_from_{geography}")
            else:
                prices[crop_id] = {}
                notes.append("no_price_history")
            self.basis[crop_id] = CropBasis(
                unit=unit,
                expected_yield=expected,
                yield_level=level,
                yield_verified=verified,
                price=quote.price_usd,
                price_level=quote.level,
                price_years=len(prices[crop_id]),
                observed_years=len(anomalies[crop_id]),
                notes=tuple(notes),
            )

        # Years that can be drawn: those with weather at the field. Without any season summary
        # the price years are drawn instead (yields then vary only where a state series exists).
        draw_years = sorted(seasons) or sorted({y for p in prices.values() for y in p})
        self.years: list[Year] = []
        for year in draw_years:
            season = seasons.get(year)
            crops_out = {}
            for crop_id, basis in self.basis.items():
                weather = adapter.weather_part(crop_id, season) if season else None
                factor, drought, paid = (1.0, 0.0, ())
                if weather is not None:
                    factor, drought, paid = modelled_loss(crop_id, weather, self.responses)
                anomaly = anomalies[crop_id].get(year)
                if anomaly is not None:
                    mode = "observed"
                    paid = weather.evaluated if weather else ()
                elif paid:
                    mode, anomaly = "modelled", factor
                else:
                    mode, anomaly = "none", 1.0
                crops_out[crop_id] = CropYear(
                    yield_per_acre=basis.expected_yield * anomaly,
                    price=prices[crop_id].get(year, basis.price),
                    mode=mode,
                    anomaly=anomaly,
                    modelled_factor=factor,
                    drought_loss=drought,
                    paid_rules=tuple(paid),
                    weather=weather,
                )
            self.years.append(Year(year, crops_out))

    def draw(self, rng: Random) -> Year:
        return rng.choice(self.years)
