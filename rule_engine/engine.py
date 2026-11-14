"""RotationAdvisor: evaluate every candidate crop for a field and rank the alternatives.

The result is purely structured (codes, numbers, rule ids, triggering facts). Wording for the
farmer is left to the consumer, e.g. an LLM agent; nothing here renders prose.
"""

from datetime import date, timedelta
from typing import Literal

from rule_engine.catalog import Catalog, Crop
from rule_engine.facts import (
    DERIVED_FROM,
    FIELD_INPUTS,
    HazardResult,
    HistoryYear,
    candidate_facts,
    county_facts,
    crop_history,
    field_facts,
    hazard_result,
    history_facts,
)
from rule_engine.herbicide import herbicide_facts, load_plantback
from rule_engine.offseason import off_season
from rule_engine.reference import ReferenceTables, StageCalendar, localize
from rule_engine.regions import field_region
from rule_engine.rules import Rule, RuleSet, applies, check
from rule_engine.soil import DerivedSoilIndicators, SoilHealthProvider
from rule_engine.summary import ClimateRecord, ClimateRecordStore, SeasonSummary, SeasonSummaryStore
from rule_engine.yield_model import (
    YieldModel,
    apply_yield_factors,
    display_yield,
    gross_revenue,
)

Priority = Literal["water", "soil", "erosion", "income", "pest_break"]
PRIORITY_CATEGORIES: dict[str, set[str]] = {
    "water": {"water", "temperature"},
    "soil": {"soil_nutrient", "diversity"},
    "erosion": {"erosion"},
    "pest_break": {"pest_disease", "weed"},
    "income": {"yield", "market"},
}
LEVEL_WEIGHT = {"low": 1, "medium": 2, "high": 3}
PRIORITY_MULTIPLIER = 2
BENEFIT_POINTS = 1
INCOME_BONUS_MAX = 2.0
RESULT_VERSION = "2026-11-14.3"
MIN_SEASONS_FOR_HIGH = 3  # one or two seasons cannot establish a recurring hazard
MIN_HAZARD_SHARE = 0.1  # a hazard seen in fewer than 1 season in 10 is not reported as a risk
MIN_HISTORY_SEASONS = 3
METRIC_UNITS = {
    "tmax_max": "degC",
    "tmin_min": "degC",
    "pr_mm": "mm",
    "eto_mm": "mm",
    "rz_pctl_min": "percentile",
    "rz_pctl_mean": "percentile",
    "dm_max": "usdm_category",
    "eddi_max": "eddi_percentile",
}


def _json(value):
    """Facts may hold tuples or sets; keep the output JSON-friendly."""
    if isinstance(value, (tuple, set, frozenset)):
        return sorted(value) if isinstance(value, (set, frozenset)) else list(value)
    return value


def _doy_date(doy: int, year: int) -> str:
    return (date(year, 1, 1) + timedelta(days=doy - 1)).isoformat()


def _gap(code: str, **params) -> dict:
    return {"code": code, **params}


class RotationAdvisor:
    def __init__(
        self,
        catalog: Catalog,
        rules: RuleSet,
        reference: ReferenceTables,
        summaries: SeasonSummaryStore,
        yield_model: YieldModel,
        soil_provider: SoilHealthProvider | None = None,
        region: str = "IA",
        climate: ClimateRecordStore | None = None,
    ):
        self.climate = climate if climate is not None and climate.available() else None
        self.catalog = catalog
        self.rules = rules
        self.reference = reference
        self.summaries = summaries
        self.yield_model = yield_model
        self.soil_provider = soil_provider or DerivedSoilIndicators()
        self.region = region
        self.plantback = load_plantback()
        self.reads_herbicides = any(
            c.fact.startswith("herbicide.") for rule in rules.rules for c in rule.when
        )
        # field.soil.* / field.practice.* facts that at least one rule reads
        self.input_facts = sorted(
            {
                c.fact
                for rule in rules.rules
                for c in rule.when
                if c.fact.startswith(tuple(FIELD_INPUTS.values()))
            }
        )

    # -- public -------------------------------------------------------------------------

    def candidate_ids(self, region: str | None = None) -> list[str]:
        return [crop.id for crop in self.catalog.candidates(region or self.region)]

    def region_for(self, field: dict) -> tuple[str, list[dict]]:
        """The field's state when the catalog has candidate crops for it, else the default."""
        state = field_region(field)
        if state is None:
            return self.region, []
        if self.catalog.candidates(state):
            return state, []
        return self.region, [_gap("region_not_supported", state=state, usedRegion=self.region)]

    def advise(self, field: dict, intended_crop: str, priorities: list[str], units: str) -> dict:
        region, region_gaps = self.region_for(field)
        intended = self.catalog.crops.get(intended_crop)
        if intended is None or intended not in self.catalog.candidates(region):
            raise ValueError(f"{intended_crop!r} is not a candidate crop for {region}")
        unknown = set(priorities) - set(PRIORITY_CATEGORIES)
        if unknown:
            raise ValueError(f"unknown priorities {sorted(unknown)}")
        csbid, county = field.get("sourceId"), field.get("countyFips")
        seasons = self.summaries.seasons(str(csbid), str(county)) if csbid and county else []
        history = crop_history(field, seasons, self.catalog)
        climate = self.climate.record(*self._position(field, seasons)) if self.climate else None
        area_ha = float(field.get("area") or 0.0)

        assessed = [
            self._assess(crop, field, history, seasons, area_ha, priorities, units, region, climate)
            for crop in self.catalog.candidates(region)
        ]
        self._apply_income_bonus(assessed, priorities)
        income = "income" in priorities
        for item in assessed:
            item["isIntended"] = item["crop"] == intended.id
        assessed.sort(
            key=lambda c: (
                c["score"],
                not c["isIntended"],
                income and not c["economicsAvailable"],
                len(c["dataGaps"]),
            )
        )
        for rank, item in enumerate(assessed, start=1):
            item["rank"] = rank
            item["score"] = round(item["score"], 2)

        return {
            "fieldId": str(field["id"]),
            "intendedCrop": intended.id,
            "region": region,
            "asOf": date.today().isoformat(),
            "resultVersion": RESULT_VERSION,
            "ruleSetVersion": self.rules.version,
            "catalogVersion": self.catalog.version,
            "units": units,
            "priorities": list(priorities),
            "historySource": self._history_source(history),
            "history": [
                {
                    "year": y.year,
                    "crop": y.crop,
                    "cdlCode": y.cdl_code,
                    "source": y.source,
                }
                for y in history
            ],
            "seasonsAvailable": [s.year for s in seasons],
            "weatherRecord": climate.describe() if climate else None,
            "offSeason": self._off_season(field, history, region, climate),
            "candidates": assessed,
            "scoring": {
                "levelWeight": LEVEL_WEIGHT,
                "benefitPoints": -BENEFIT_POINTS,
                "priorityMultiplier": PRIORITY_MULTIPLIER,
                "priorityCategories": {p: sorted(PRIORITY_CATEGORIES[p]) for p in priorities},
                "incomeBonusMax": -INCOME_BONUS_MAX if income else 0,
                "tieBreak": ["score", "isIntended", "economicsAvailable", "dataGapCount"],
                "lowerIsBetter": True,
            },
            "dataGaps": region_gaps
            + self._field_gaps(field, seasons, history, climate)
            + ([_gap("no_weather_record")] if self.climate and climate is None else [])
            + self._input_gaps(field_facts(field, history, seasons)),
        }

    # -- per candidate ------------------------------------------------------------------

    @staticmethod
    def _position(field: dict, seasons: list[SeasonSummary]) -> tuple[float | None, float | None]:
        """(latitude, longitude) of the field, from the record or else from its summaries."""
        latitude, longitude = field.get("latitude"), field.get("longitude")
        if (latitude is None or longitude is None) and seasons:
            scalars = seasons[-1].scalars
            latitude, longitude = scalars.get("centroid_lat"), scalars.get("centroid_lon")
        return latitude, longitude

    def _calendar(self, crop: Crop, region: str, field: dict) -> StageCalendar:
        """The regional calendar, moved to local stage dates when the field carries them
        (`field["stageCalendar"][crop id] = {"stages": {stage: day of year}, "source": ...}`)."""
        calendar = self.reference.calendar(crop, region)
        local = (field.get("stageCalendar") or {}).get(crop.id)
        if not local or not local.get("stages"):
            return calendar
        return localize(calendar, local["stages"], local.get("source"))

    def _off_season(self, field, history, region, climate: ClimateRecord | None) -> dict:
        previous = next((self.catalog.crops[y.crop] for y in reversed(history) if y.crop), None)
        calendar = self._calendar(previous, region, field) if previous else None
        # a standing perennial is not harvested and reseeded, so it leaves no slot
        annual = previous is not None and previous.value("lifecycle") == "annual"
        return off_season(
            previous.id if previous else None,
            calendar.stages.get("harvested") if annual else None,
            calendar.kind if calendar else None,
            climate.seasons if climate else (),
            self.candidate_ids(region),
        )

    def _assess(
        self, crop, field, history, seasons, area_ha, priorities, units, region, climate=None
    ) -> dict:
        facts = {
            **candidate_facts(crop),
            **history_facts(history, crop, self.catalog),
            **county_facts(seasons),
            **field_facts(field, history, seasons),
        }
        calendar = self._calendar(crop, region, field)
        season_year = seasons[-1].year if seasons else None
        if season_year is None and climate:
            season_year = climate.seasons[-1].year
        herbicide, unknown_actives = herbicide_facts(field, crop, calendar, self.plantback)
        facts.update(herbicide)

        findings: list[dict] = []
        gaps: list[dict] = []
        if unknown_actives:
            gaps.append(_gap("herbicide_plantback_unknown", actives=unknown_actives))
        yield_factors = []
        hazards_skipped = False
        for rule in self.rules.rules:
            if not applies(rule, crop, self.catalog):
                continue
            if rule.hazard is not None:
                if rule.hazard.stage not in calendar.stages:
                    gaps.append(
                        _gap(
                            "hazard_stage_not_in_calendar", ruleId=rule.id, stage=rule.hazard.stage
                        )
                    )
                    continue
                # weather hazards are counted over the long record, the rest over field seasons
                long_record = climate is not None and rule.hazard.metric in climate.metrics
                result = hazard_result(
                    rule.hazard, calendar, climate.seasons if long_record else seasons
                )
                if result is None or result.seasons_total == 0:
                    hazards_skipped = True
                    continue
                if result.seasons_hit == 0 or result.share < MIN_HAZARD_SHARE:
                    continue
                finding = self._timed_finding(rule, result, calendar, season_year)
                finding["trigger"]["record"] = "weather_record" if long_record else "field_seasons"
            else:
                checks = [(c, *check(c, facts)) for c in rule.when]
                if not all(ok for _, ok, _, _ in checks):
                    continue
                finding = self._finding(rule, rule.effect.level)
                finding["trigger"] = {
                    "type": "conditions",
                    "conditions": [
                        {
                            "fact": c.fact,
                            "op": c.op,
                            "expected": _json(expected),
                            "actual": _json(actual),
                        }
                        for c, _, actual, expected in checks
                    ],
                }
            unverified = self._unverified_traits(rule, crop, facts.get("history.prev1.crop"))
            if unverified:
                finding["evidenceStrength"] = "weak"
                finding["needsLocalReview"] = True
                finding["unverifiedTraits"] = unverified
                gaps.append(_gap("rule_uses_unverified_traits", ruleId=rule.id, traits=unverified))
            if rule.effect.yield_factor:
                yield_factors.append((rule.id, rule.effect.yield_factor))
            finding["points"] = self._points(finding, priorities)
            findings.append(finding)
        if hazards_skipped:
            gaps.append(_gap("hazards_not_evaluated", reason="no_season_summary"))
        if calendar.kind != "nass_region":
            gaps.append(_gap("calendar_not_nass", calendarKind=calendar.kind))

        yield_out, revenue_out = self._economics(
            crop, seasons, yield_factors, area_ha, units, gaps, region
        )

        soil = [
            {
                "id": i.id,
                "value": i.value,
                "unit": i.unit,
                "direction": i.direction,
                "threshold": i.threshold,
                "basis": i.basis,
                "kind": i.kind,
                "verified": i.verified,
                "inputs": i.inputs,
            }
            for i in self.soil_provider.indicators(field, crop, history, seasons)
        ]

        breakdown = [
            {"source": "rule", "ruleId": f["ruleId"], "kind": f["kind"], "points": f["points"]}
            for f in findings
            if f["points"]
        ]
        return {
            "crop": crop.id,
            "label": crop.label,
            "group": crop.group.id,
            "rank": 0,
            "isIntended": False,
            "score": float(sum(item["points"] for item in breakdown)),
            "scoreBreakdown": breakdown,
            "economicsAvailable": revenue_out is not None,
            "risks": [f for f in findings if f["kind"] == "risk"],
            "benefits": [f for f in findings if f["kind"] == "benefit"],
            "advisories": [f for f in findings if f["kind"] == "advisory"],
            "calendar": {
                "kind": calendar.kind,
                "stages": dict(calendar.stages),
                "localShiftDays": dict(calendar.local_shift),
                "localSource": calendar.local_source,
            },
            "soil": soil,
            "soilProvider": self.soil_provider.name,
            "yield": yield_out,
            "revenue": revenue_out,
            "dataGaps": gaps,
            "needsLocalReview": any(f["needsLocalReview"] for f in findings),
        }

    def _economics(self, crop, seasons, yield_factors, area_ha, units, gaps, region):
        estimate = self.yield_model.predict(crop, seasons, self.reference, region)
        if estimate is None:
            gaps.append(_gap("no_yield_estimate"))
            return None, None
        adjusted = apply_yield_factors(estimate, yield_factors)
        if not adjusted.verified:
            gaps.append(_gap("yield_unverified", level=adjusted.level))
        yield_out = self._yield_dict(crop, adjusted, yield_factors, units)
        price = self.reference.price(crop.id, region)
        if price is None:
            gaps.append(_gap("no_price"))
            return yield_out, None
        if not price.verified:
            gaps.append(_gap("price_unverified"))
        if price.level != "state":
            gaps.append(_gap("price_not_local", level=price.level))
        elif price.region not in (None, region):
            gaps.append(_gap("price_not_local", level=price.level, observedIn=price.region))
        if area_ha <= 0:
            gaps.append(_gap("field_area_unknown"))
            return yield_out, None
        revenue = gross_revenue(adjusted, price, crop, area_ha)
        if revenue is None:
            gaps.append(_gap("price_unit_unconvertible", priceUnit=price.unit))
            return yield_out, None
        return yield_out, {
            "lowUsd": revenue.low_usd,
            "midUsd": revenue.mid_usd,
            "highUsd": revenue.high_usd,
            "priceUsd": revenue.price_usd,
            "priceUnit": revenue.price_unit,
            "priceAsOf": revenue.price_as_of,
            "priceVerified": revenue.price_verified,
            "priceLevel": revenue.price_level,
            "areaHa": round(revenue.area_ha, 2),
            "grossOnly": True,  # no input costs by design
        }

    def _unverified_traits(self, rule: Rule, crop: Crop, prev_id) -> list[str]:
        """Traits the rule relies on that are flagged unverified on the candidate or last crop."""
        prev = self.catalog.crops.get(prev_id) if prev_id else None
        unverified = []
        for name in rule.uses_traits:
            holder = crop if name in crop.all_traits() else prev
            if holder is not None and name in holder.all_traits():
                if not holder.trait(name).verified:
                    unverified.append(name)
        return unverified

    @staticmethod
    def _finding(rule: Rule, level) -> dict:
        factor = rule.effect.yield_factor
        return {
            "ruleId": rule.id,
            "title": rule.title,
            "category": rule.category,
            "kind": rule.effect.kind,
            "level": level if rule.effect.kind == "risk" else None,
            "points": 0,
            "yieldFactor": {"low": factor[0], "high": factor[1]} if factor else None,
            "evidenceStrength": rule.evidence_strength,
            "unverifiedTraits": [],
            "needsLocalReview": rule.needs_local_review,
            "trigger": None,
        }

    def _timed_finding(
        self, rule: Rule, result: HazardResult, calendar: StageCalendar, year: int
    ) -> dict:
        bands = rule.effect.level_bands or {}
        level = "low"
        for name in ("high", "medium"):
            if name in bands and result.share >= bands[name] and result.share > 0:
                level = name
                break
        capped = level == "high" and result.seasons_total < MIN_SEASONS_FOR_HIGH
        if capped:
            level = "medium"
        hazard = rule.hazard
        start, end = result.window
        finding = self._finding(rule, level)
        finding["trigger"] = {
            "type": "hazard",
            "stage": hazard.stage,
            "stageDoy": result.stage_doy,
            "window": {
                "offsetDays": list(hazard.window_days),
                "startDoy": start,
                "endDoy": end,
                "startDate": _doy_date(start, year),
                "endDate": _doy_date(end, year),
            },
            "calendarKind": calendar.kind,
            "metric": hazard.metric,
            "metricUnit": METRIC_UNITS.get(hazard.metric, "days"),
            "aggregate": hazard.aggregate,
            "compare": hazard.compare,
            "threshold": hazard.threshold,
            "seasonsHit": result.seasons_hit,
            "seasonsTotal": result.seasons_total,
            "share": round(result.share, 3),
            "worstYear": result.worst_year,
            "worstValue": None if result.worst_value is None else round(result.worst_value, 2),
            "levelBands": bands,
            "levelCapped": capped,
            "perSeason": [{"year": y, "value": v, "hit": hit} for y, v, hit in result.per_season],
        }
        if calendar.kind != "nass_region":
            finding["needsLocalReview"] = True
        return finding

    @staticmethod
    def _yield_dict(crop: Crop, estimate, factors, units: str) -> dict:
        low, unit = display_yield(crop, estimate.low_t_ha, units)
        mid, _ = display_yield(crop, estimate.mid_t_ha, units)
        high, _ = display_yield(crop, estimate.high_t_ha, units)
        return {
            "low": low,
            "mid": mid,
            "high": high,
            "unit": unit,
            "midTHa": round(estimate.mid_t_ha, 3),
            "method": estimate.method,
            "level": estimate.level,
            "verified": estimate.verified,
            "inputs": estimate.inputs,
            "factorsApplied": [
                {"ruleId": rule_id, "low": low_f, "high": high_f}
                for rule_id, (low_f, high_f) in factors
            ],
        }

    # -- scoring ------------------------------------------------------------------------

    @staticmethod
    def _multiplier(category: str, priorities) -> int:
        hit = any(category in PRIORITY_CATEGORIES.get(p, set()) for p in priorities)
        return PRIORITY_MULTIPLIER if hit else 1

    def _points(self, finding: dict, priorities) -> float:
        multiplier = self._multiplier(finding["category"], priorities)
        if finding["kind"] == "risk":
            return float(LEVEL_WEIGHT[finding["level"]] * multiplier)
        if finding["kind"] == "benefit":
            return float(-BENEFIT_POINTS * multiplier)
        return 0.0

    @staticmethod
    def _apply_income_bonus(assessed, priorities) -> None:
        """Rank by mid gross revenue; best gets -INCOME_BONUS_MAX, worst 0, no revenue 0."""
        if "income" not in priorities:
            return
        with_revenue = [c for c in assessed if c["revenue"]]
        with_revenue.sort(key=lambda c: c["revenue"]["midUsd"], reverse=True)
        n = len(with_revenue)
        for index, item in enumerate(with_revenue):
            points = -INCOME_BONUS_MAX * (1 - index / (n - 1)) if n > 1 else -INCOME_BONUS_MAX
            item["score"] += points
            item.setdefault("scoreBreakdown", []).append(
                {
                    "source": "income_rank",
                    "revenueRank": index + 1,
                    "of": n,
                    "points": round(points, 2) + 0.0,  # no -0.0
                }
            )
        for item in assessed:
            if not item["revenue"]:
                item.setdefault("scoreBreakdown", []).append(
                    {"source": "income_rank", "revenueRank": None, "of": n, "points": 0.0}
                )

    # -- field-level context ------------------------------------------------------------

    @staticmethod
    def _history_source(history: list[HistoryYear]) -> dict:
        kinds = {y.source for y in history}
        kind = "none" if not history else ("cdl" if "cdl" in kinds else "declared")
        return {
            "kind": kind,
            "seasons": len(history),
            "firstYear": history[0].year if history else None,
            "lastYear": history[-1].year if history else None,
            "satelliteEstimate": kind == "cdl",  # CDL is a classification, not a farmer record
            "unknownCdlCodes": sorted(
                {y.cdl_code for y in history if y.crop is None and y.cdl_code}
            ),
        }

    def _input_gaps(self, facts: dict) -> list[dict]:
        """Rules read soil or practice facts the caller did not supply; those rules stay silent."""
        gaps = []
        for key, prefix in FIELD_INPUTS.items():
            missing = sorted(
                {
                    DERIVED_FROM.get(f, f)
                    for f in self.input_facts
                    if f.startswith(prefix) and f not in facts
                }
            )
            if key == "practices" and self.reads_herbicides:
                if "field.practice.herbicides" not in facts:
                    missing.append("field.practice.herbicides")
            if missing:
                code = "soil_not_provided" if key == "soil" else "practices_not_provided"
                gaps.append(_gap(code, facts=missing))
        return gaps

    @staticmethod
    def _field_gaps(field, seasons: list[SeasonSummary], history, climate=None) -> list[dict]:
        gaps = []
        weather = [] if climate else ["weather"]
        if not field.get("sourceId"):
            gaps.append(_gap("no_csb_id", affects=[*weather, "soil_moisture", "county_yield"]))
        elif not seasons:
            gaps.append(
                _gap("no_season_summary", affects=[*weather, "soil_moisture", "drought_monitor"])
            )
        elif len(seasons) < MIN_SEASONS_FOR_HIGH and not climate:
            gaps.append(
                _gap("few_weather_seasons", seasons=len(seasons), minimum=MIN_SEASONS_FOR_HIGH)
            )
        if len(history) < MIN_HISTORY_SEASONS:
            gaps.append(_gap("short_history", seasons=len(history), minimum=MIN_HISTORY_SEASONS))
        return gaps
