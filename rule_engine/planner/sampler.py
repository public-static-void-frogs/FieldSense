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

Price of a crop in a drawn year: the current planning price x that year's price change, which is
the year's marketing-year price over the previous year's, both in constant dollars (consumer
price index, data/cpi_u.csv), scaled to mean 1. The planning price is the expectation, and a
drawn year says how far a season's price ended from what was known before it. Drawing the
constant-dollar price level instead (the earlier version) put most recent years below the
planning price, because real crop prices have fallen since the 1980s: in the backtest
(scripts/backtest.py) that overstated the chance of a loss by about a third.

The expected yield is the trend read one year past the last observed yield, which is the season
being planned. A yield series with fewer than 3 observations in the 10 years before that season
has ended (NASS stopped publishing Iowa sorghum after 1984, and many southern county corn and
soybean yields in the 1990s) and is not used: the crop then takes the next level (state series,
then the reference yield), and without one it is not planned (gap `no_yield`). A trend is fitted
to 10 or more observations; with fewer, the level is the mean of the recent ones.

Prices and state yields come from planner/data/nass_long_history.csv (since 1980, every state)
where it has the series, otherwise from the rule engine's nass_reference_history.csv.

A crop whose state publishes no current yield (corn for grain in the New England states and
Nevada, Iowa sorghum, Utah oats: NASS reports other crops there or stopped) takes the next wider
level that has a current series, and the basis says so: the mean of the state yields of the field's
USDA ERS region (data/nass_regional_history.csv, scripts/build_regional_history.py), level
"region", note `yield_from_region`; then the national yield, level "national", note
`yield_from_national`. A wider series that ended more than FALLBACK_FRESH_YEARS before the planned
season is passed over. A crop without a quote from the rule engine takes the latest marketing-year
price NASS published for the state, then the nation, within the same years (note
`planning_price_from_history`). Pasture is not sold: gap `not_marketed`, not `no_price`.
"""

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from random import Random

from rule_engine.catalog import unit_kind
from rule_engine.engine import RotationAdvisor
from rule_engine.planner.adapter import RuleAdapter, WeatherPart
from rule_engine.planner.context import FieldContext
from rule_engine.planner.soil_level import SoilLevel, soil_level
from rule_engine.planner.tables import Response, ers_region, load_responses
from rule_engine.reference import PriceQuote

HISTORY_CSV = Path(__file__).parents[1] / "data" / "nass_reference_history.csv"
LONG_HISTORY_CSV = Path(__file__).parent / "data" / "nass_long_history.csv"
REGIONAL_HISTORY_CSV = Path(__file__).parent / "data" / "nass_regional_history.csv"
CPI_CSV = Path(__file__).parent / "data" / "cpi_u.csv"  # BLS CPI-U, all items, 1982-84 = 100
COUNTY_COLUMNS = {"corn": "yield_corn_bu_ac", "soybeans": "yield_soy_bu_ac"}
MIN_TREND_POINTS = 10
# The farmer's own yields set the field's level against the county, the way crop insurance builds
# an actual production history (USDA RMA APH): the latest 10 years count, and with fewer than 4
# the missing years are filled at the county level. (APH discounts the fill-in years; this
# does not.)
OWN_YIELD_MAX_YEARS = 10
OWN_YIELD_MIN_YEARS = 4
# NASS stopped publishing some yields (Iowa sorghum after 1984; county corn and soybeans across
# much of the South in the 1990s). A series with fewer than MIN_RECENT_YIELDS observations in the
# RECENT_YIELD_YEARS before the planned season is not today's yield level, and its trend is not
# extended to now.
RECENT_YIELD_YEARS = 10
MIN_RECENT_YIELDS = 3
# A wider-level yield or price series must have a value this recent (years before the planned season)
FALLBACK_FRESH_YEARS = 3
# Crops nobody buys per unit of yield: grazed on the farm, so there is no price to plan with
NOT_MARKETED = frozenset({"grass_pasture"})


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
    yield_level: str  # county | state | reference | field (own yields) | field_soil
    yield_verified: bool
    price: float
    price_level: str
    price_years: int
    observed_years: int
    notes: tuple[str, ...] = field(default=())
    own_ratio: float = 1.0  # the field's yield level against the county/state/reference level
    own_points: tuple[tuple[int, float, float], ...] = ()  # (year, own yield, reference yield)
    soil_level: SoilLevel | None = None  # set when the soil index moved the expected yield


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


def _current(observed: dict[int, float], planned: int) -> dict[int, float]:
    """The part of a yield series that says what the crop yields now; {} when the series ended.

    With too few points for a trend only the recent ones are kept, so the level is their mean
    and an old yield is not read as a bad year against it.
    """
    recent = {y: v for y, v in observed.items() if planned - y <= RECENT_YIELD_YEARS}
    if len(recent) < MIN_RECENT_YIELDS:
        return {}
    return observed if len(observed) >= MIN_TREND_POINTS else recent


@lru_cache(maxsize=1)
def _history_rows() -> tuple[dict, ...]:
    """Long-history rows first, so `_series` finds them before the engine's shorter series."""
    rows: list[dict] = []
    for path in (LONG_HISTORY_CSV, REGIONAL_HISTORY_CSV, HISTORY_CSV):
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


def price_changes(history: dict[int, float]) -> dict[int, float]:
    """{year: constant-dollar price over the previous year's}, scaled to mean 1."""
    cpi = _cpi()
    real = {y: p / cpi[y] for y, p in history.items() if y in cpi}
    change = {y: real[y] / real[y - 1] for y in real if y - 1 in real}
    if not change:
        return {}
    mean = sum(change.values()) / len(change)
    return {y: v / mean for y, v in change.items()}


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


def _exact(rows, kind: str, crop: str, geography: str) -> tuple[dict[int, float], str]:
    """({year: value}, unit) of one geography's series only, no fallback."""
    match = [
        r
        for r in rows
        if r["kind"] == kind and r["crop"] == crop and r["geography"] == geography
    ]
    if not match:
        return {}, ""
    first = match[0]
    values = {
        int(r["year"]): float(r["value"])
        for r in match
        if r["unit"] == first["unit"] and r.get("nass_short_desc") == first.get("nass_short_desc")
    }
    return values, first["unit"]


def _history_quote(rows, crop: str, region: str, planned: int) -> PriceQuote | None:
    """The latest published marketing-year price of the state, else of the nation, when it is at
    most FALLBACK_FRESH_YEARS old: a planning price for a crop the rule engine has no quote for."""
    for geography in dict.fromkeys((region, "US")):
        series, unit = _exact(rows, "price", crop, geography)
        if not series or planned - max(series) > FALLBACK_FRESH_YEARS:
            continue
        year = max(series)
        local = geography != "US"
        return PriceQuote(
            crop_id=crop,
            price_usd=series[year],
            unit=unit.split("/")[-1],
            source=f"USDA NASS Quick Stats: {geography} marketing year {year} price received",
            as_of=str(year),
            verified=True,
            level="state" if local else "national",
            region=region if local else None,
        )
    return None


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
        levels: dict[int, list[float]] = {}
        planned = now or max(seasons or (int(r["year"]) for r in rows)) + 1
        for crop_id in crops:
            quote = advisor.reference.price(crop_id, context.region)
            own_price = ((context.field.get("economics") or {}).get("prices") or {}).get(crop_id)
            notes = []
            if quote is None and crop_id in NOT_MARKETED and not own_price:
                self.unavailable[crop_id] = "not_marketed"
                continue
            if quote is None:
                quote = _history_quote(rows, crop_id, context.region, planned)
                if quote is not None:
                    notes.append("planning_price_from_history")
            if quote is None:
                self.unavailable[crop_id] = "no_price"
                continue
            unit = unit_kind(quote.unit)
            # the farmer's own expected price replaces the planning price
            planning, price_level = quote.price_usd, quote.level
            if own_price:
                planning, price_level = float(own_price), "farmer"

            observed: dict[int, float] = {}
            level = "reference"
            ended = False
            column = COUNTY_COLUMNS.get(crop_id)
            if column:
                published = {
                    y: float(s.scalars[column])
                    for y, s in seasons.items()
                    if (s.scalars.get(column) or 0) > 0  # NASS zero is "not reported", not a yield
                }
                observed, level = _current(published, planned), "county"
                ended = bool(published) and not observed
            if not observed:
                published, y_unit, geography = _series(rows, "yield", crop_id, context.region)
                if geography != context.region or unit_kind(y_unit) != unit:
                    published = {}  # another state's yield level is not this field's
                observed, level = _current(published, planned), "state"
                ended = ended or (bool(published) and not observed)
            if not observed:
                observed, level = self._wider_yield(rows, crop_id, context, unit, planned, notes)
            if ended:
                notes.append("yield_history_ended")
            verified = True
            if observed:
                trend = _trend(observed)
                last = max(observed)
                expected = trend(min(now or last + 1, last + 1))
                anomalies[crop_id] = {y: v / trend(y) for y, v in observed.items() if trend(y) > 0}
            else:
                ref = advisor.reference.yield_reference(crop_id, context.region)
                if ref is None or unit_kind(ref.unit) != unit:
                    self.unavailable[crop_id] = "no_yield"
                    continue
                expected, level, verified = ref.mid, "reference", ref.verified
                notes.append("no_yield_history")
                anomalies[crop_id] = {}

            own = (context.field.get("ownYields") or {}).get(crop_id) or {}
            points = []
            for year in sorted(own, reverse=True)[:OWN_YIELD_MAX_YEARS]:
                base = observed.get(year) or (trend(year) if observed else expected)
                if own[year] > 0 and base > 0:
                    points.append((year, float(own[year]), base))
            ratio = 1.0
            if points:
                filled = max(0, OWN_YIELD_MIN_YEARS - len(points))
                ratio = (sum(y / b for _, y, b in points) + filled) / (len(points) + filled)
                expected, level = expected * ratio, "field"
            soil = None
            if not points and level == "county":
                # no yields from the farmer: the soil index places the field within the county
                soil = soil_level(
                    crop_id, context.field.get("soil"), context.field.get("countyFips")
                )
                if soil is not None:
                    expected, level = expected * soil.ratio, "field_soil"

            history, p_unit, geography = _series(rows, "price", crop_id, context.region)
            if history and p_unit.endswith(unit):
                prices[crop_id] = {
                    y: change * planning for y, change in price_changes(history).items()
                }
                for year, value in price_levels(history).items():
                    levels.setdefault(year, []).append(value)
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
                price=planning,
                price_level=price_level,
                price_years=len(prices[crop_id]),
                observed_years=len(anomalies[crop_id]),
                notes=tuple(notes),
                own_ratio=ratio,
                own_points=tuple(sorted(points)),
                soil_level=soil,
            )

        # constant-dollar price level of each year (mean over the priced crops), a carry-over signal
        self.price_level = {year: sum(v) / len(v) for year, v in levels.items()}

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

    @staticmethod
    def _wider_yield(rows, crop_id, context, unit, planned, notes) -> tuple[dict[int, float], str]:
        """The yield series of the field's ERS region, then of the nation, when the state has none
        that is current. ({}, "reference") when neither is."""
        region = ers_region(context.field.get("countyFips"))
        for geography, level in ((f"ERS:{region}" if region else None, "region"), ("US", "national")):
            if geography is None:
                continue
            series, y_unit = _exact(rows, "yield", crop_id, geography)
            if not series or unit_kind(y_unit) != unit:
                continue
            if planned - max(series) > FALLBACK_FRESH_YEARS:
                continue
            observed = _current(series, planned)
            if observed:
                notes.append(f"yield_from_{level}")
                return observed, level
        return {}, "reference"

    def draw(self, rng: Random) -> Year:
        return rng.choice(self.years)
