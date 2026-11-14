"""The only place where the planner calls the rule engine.

The engine's assessment is split into two parts that the planner can cache separately:

- the history part: condition rules over (planned history, candidate crop, practices). It does not
  depend on weather, so it is computed once per (history, action).
- the weather part: timed hazards and county loss rules for one season. It does not depend on the
  planned history, so it is computed once per (crop, year).

Both parts reuse the engine's own fact builders, rule matching and point scale.
"""

from dataclasses import dataclass

from rule_engine.engine import LEVEL_WEIGHT, RotationAdvisor
from rule_engine.facts import (
    HistoryYear,
    candidate_facts,
    county_facts,
    field_facts,
    hazard_result,
    history_facts,
)
from rule_engine.herbicide import herbicide_facts
from rule_engine.planner.context import FieldContext
from rule_engine.rules import applies, check
from rule_engine.summary import SeasonSummary

# A cover crop in the plan is assumed to be terminated this many days before planting, which is
# the "properly managed" case of the engine's rye rules.
COVER_TERMINATION_DAYS = 14
HIT_LEVEL = "high"  # a hazard that occurs in the drawn season counts with the top level weight


@dataclass(frozen=True)
class HistoryPart:
    points: float  # rules without a yield factor (rules with one are paid for in yield)
    factor_low: float
    factor_high: float
    point_rules: tuple[tuple[str, float], ...]
    yield_rules: tuple[tuple[str, float, float], ...]
    weak_rules: tuple[str, ...]  # fired on unverified traits or flagged for local review

    @property
    def factor(self) -> float:
        value = 1.0
        for _, low, high in self.yield_rules:
            value *= (low + high) / 2
        return value


@dataclass(frozen=True)
class HazardHit:
    rule: str
    category: str
    value: float
    points: float


@dataclass(frozen=True)
class WeatherPart:
    hazards: tuple[HazardHit, ...]
    evaluated: tuple[str, ...]  # hazard rules that had data this season
    county_rules: tuple[tuple[str, float], ...]
    drought_weeks: int | None  # weeks at D1 or worse between planting and maturity
    d4_weeks: int | None

    @property
    def county_points(self) -> float:
        return sum(points for _, points in self.county_rules)


def _history(crops: tuple[str, ...]) -> list[HistoryYear]:
    return [HistoryYear(index, crop, None, "declared") for index, crop in enumerate(crops)]


class RuleAdapter:
    def __init__(self, advisor: RotationAdvisor, context: FieldContext, priorities=()):
        self.advisor = advisor
        self.context = context
        self.priorities = tuple(priorities)
        self.county_rule_ids = {
            rule.id
            for rule in advisor.rules.rules
            if rule.hazard is None and any(c.fact.startswith("county.") for c in rule.when)
        }
        self._history_cache: dict = {}
        self._weather_cache: dict = {}

    def field_with(self, tillage: str | None, cover: str | None) -> dict:
        practices = dict(self.context.field.get("practices") or {})
        if tillage is not None:
            practices["tillage"] = tillage
        if cover is not None:
            practices["cover_crop"] = cover
            if cover != "none":
                practices.setdefault("cover_termination_days", COVER_TERMINATION_DAYS)
        return {**self.context.field, "practices": practices}

    def _points(self, rule, level) -> tuple[float, dict]:
        finding = self.advisor._finding(rule, level)
        return self.advisor._points(finding, self.priorities), finding

    def history_part(
        self, history: tuple[str, ...], crop_id: str, tillage: str, cover: str
    ) -> HistoryPart:
        key = (history, crop_id, tillage, cover)
        if key in self._history_cache:
            return self._history_cache[key]
        advisor, crop = self.advisor, self.advisor.catalog.crops[crop_id]
        field = self.field_with(tillage, cover)
        years = _history(history)
        facts = {
            **candidate_facts(crop),
            **history_facts(years, crop, advisor.catalog),
            **field_facts(field, years, []),
        }
        calendar = advisor.reference.calendar(crop, self.context.region)
        facts.update(herbicide_facts(field, crop, calendar, advisor.plantback)[0])
        point_rules, yield_rules, weak = [], [], []
        for rule in advisor.rules.rules:
            if rule.hazard is not None or rule.id in self.county_rule_ids:
                continue
            if not applies(rule, crop, advisor.catalog):
                continue
            if not all(check(c, facts)[0] for c in rule.when):
                continue
            points, finding = self._points(rule, rule.effect.level)
            if rule.needs_local_review or advisor._unverified_traits(
                rule, crop, facts.get("history.prev1.crop")
            ):
                weak.append(rule.id)
            if rule.effect.yield_factor:
                yield_rules.append((rule.id, *rule.effect.yield_factor))
            elif points:
                point_rules.append((rule.id, points))
        low = high = 1.0
        for _, f_low, f_high in yield_rules:
            low, high = low * f_low, high * f_high
        part = HistoryPart(
            points=sum(p for _, p in point_rules),
            factor_low=low,
            factor_high=high,
            point_rules=tuple(point_rules),
            yield_rules=tuple(yield_rules),
            weak_rules=tuple(weak),
        )
        self._history_cache[key] = part
        return part

    def weather_part(self, crop_id: str, season: SeasonSummary) -> WeatherPart:
        key = (crop_id, season.year)
        if key in self._weather_cache:
            return self._weather_cache[key]
        advisor, crop = self.advisor, self.advisor.catalog.crops[crop_id]
        calendar = advisor.reference.calendar(crop, self.context.region)
        hits, evaluated = [], []
        for rule in advisor.rules.rules:
            if rule.hazard is None or not applies(rule, crop, advisor.catalog):
                continue
            result = hazard_result(rule.hazard, calendar, [season])
            if result is None or result.seasons_total == 0:
                continue
            evaluated.append(rule.id)
            if result.seasons_hit:
                finding = advisor._finding(rule, HIT_LEVEL)
                points = float(
                    LEVEL_WEIGHT[HIT_LEVEL]
                    * advisor._multiplier(finding["category"], self.priorities)
                )
                hits.append(HazardHit(rule.id, rule.category, float(result.worst_value), points))

        years = _history(self.context.history)
        field = self.field_with(None, None)
        facts = {
            **candidate_facts(crop),
            **history_facts(years, crop, advisor.catalog),
            **county_facts([season]),
            **field_facts(field, years, [season]),
        }
        county = []
        for rule in advisor.rules.rules:
            if rule.id not in self.county_rule_ids or not applies(rule, crop, advisor.catalog):
                continue
            if all(check(c, facts)[0] for c in rule.when):
                points, _ = self._points(rule, rule.effect.level)
                if points:
                    county.append((rule.id, points))

        drought_weeks = d4_weeks = None
        series = season.weekly.get("dm_max")
        if series and any(v is not None for v in series):
            start = calendar.stages.get("planted", calendar.stages.get("emerged"))
            end = calendar.stages.get("mature", calendar.stages.get("harvested"))
            if start is not None and end is not None:
                from rule_engine.summary import WEEK0_DOY

                first = max(0, (start - WEEK0_DOY) // 7)
                last = min(len(series) - 1, (end - WEEK0_DOY) // 7)
                weeks = [v for v in series[first : last + 1] if v is not None]
                drought_weeks = sum(v >= 1 for v in weeks)
                d4_weeks = sum(v >= 4 for v in weeks)
        part = WeatherPart(tuple(hits), tuple(evaluated), tuple(county), drought_weeks, d4_weeks)
        self._weather_cache[key] = part
        return part
