"""Turn a field, its crop history and its season summaries into flat facts for the rules."""

import re
from dataclasses import dataclass
from typing import Literal

from rule_engine.catalog import Catalog, Crop
from rule_engine.reference import StageCalendar
from rule_engine.rules import Hazard
from rule_engine.summary import SeasonSummary

CDL_KEY = re.compile(r"^CDL(\d{4})$")
HISTORY_WINDOW = 5


@dataclass(frozen=True)
class HistoryYear:
    year: int
    crop: str | None  # catalog crop id, None when the CDL code is unknown to the catalog
    cdl_code: int | None
    source: Literal["cdl", "declared"]


def _crop_by_name(name: str | None, catalog: Catalog) -> Crop | None:
    if not name:
        return None
    key = str(name).strip().lower().replace(" ", "_")
    for crop in catalog.crops.values():
        if key in (crop.id, crop.label.lower(), crop.label.lower().replace(" ", "_")):
            return crop
    return None


def crop_history(field: dict, seasons: list[SeasonSummary], catalog: Catalog) -> list[HistoryYear]:
    """Oldest-first crop history. Satellite CDL labels first, then declared crop as a fallback."""
    props = field.get("sourceProperties") or {}
    years: dict[int, HistoryYear] = {}
    for key, value in props.items():
        match = CDL_KEY.match(str(key))
        if not match or value in (None, ""):
            continue
        code = int(value)
        crop = catalog.by_cdl(code)
        years[int(match.group(1))] = HistoryYear(
            int(match.group(1)), crop.id if crop else None, code, "cdl"
        )
    if not years:
        for season in seasons:
            for offset, code in ((1, season.cdl_prev1), (2, season.cdl_prev2)):
                if code is None:
                    continue
                crop = catalog.by_cdl(int(code))
                years.setdefault(
                    season.year - offset,
                    HistoryYear(season.year - offset, crop.id if crop else None, int(code), "cdl"),
                )
    if not years:
        declared = _crop_by_name(field.get("crop"), catalog)
        if declared is not None:
            year = field.get("sourceYear") or 2025
            years[year] = HistoryYear(year, declared.id, None, "declared")
    return [years[y] for y in sorted(years)]


def _crop(catalog: Catalog, crop_id: str | None) -> Crop | None:
    return catalog.crops.get(crop_id) if crop_id else None


def history_facts(history: list[HistoryYear], candidate: Crop, catalog: Catalog) -> dict:
    known = [y for y in history if y.crop]
    newest_first = [_crop(catalog, y.crop) for y in reversed(known)]
    recent = newest_first[:HISTORY_WINDOW]
    facts: dict = {"history.years": len(known)}

    prev1 = newest_first[0] if newest_first else None
    facts["history.prev1.crop"] = prev1.id if prev1 else None
    facts["history.prev1.group"] = prev1.group.id if prev1 else None
    for name in ("family", "n_fixer", "hosts", "n_demand", "humus_balance", "n_credit_kg_ha"):
        facts[f"history.prev1.{name}"] = prev1.value(name) if prev1 else None

    consecutive_crop = 0
    for crop in newest_first:
        if crop.id != candidate.id:
            break
        consecutive_crop += 1
    consecutive_family = 0
    family = candidate.value("family")
    for crop in newest_first:
        if crop.value("family") != family:
            break
        consecutive_family += 1
    since_family = None
    for index, crop in enumerate(newest_first, start=1):
        if crop.value("family") == family:
            since_family = index
            break
    alternation = 0
    for index, crop in enumerate(newest_first):
        if crop.id not in ("corn", "soybeans"):
            break
        if index > 0 and newest_first[index - 1].id == crop.id:
            break
        alternation += 1

    candidate_hosts = set(candidate.value("hosts") or ())
    prev_hosts = set(prev1.value("hosts") or ()) if prev1 else set()
    facts.update(
        {
            "history.consecutive_same_crop": consecutive_crop,
            "history.consecutive_same_family": consecutive_family,
            "history.years_since_same_family": since_family,
            "history.distinct_groups_5y": len({c.group.id for c in recent}),
            "history.share_same_crop_5y": (
                sum(c.id == candidate.id for c in recent) / len(recent) if recent else 0.0
            ),
            "history.corn_soy_alternation_years": alternation,
            "history.shared_hosts_prev1": sorted(candidate_hosts & prev_hosts),
            "history.candidate_group_in_5y": any(c.group.id == candidate.group.id for c in recent),
        }
    )
    return facts


def candidate_facts(crop: Crop) -> dict:
    facts = {"candidate.crop": crop.id, "candidate.group": crop.group.id}
    for name, trait in crop.all_traits().items():
        facts[f"candidate.{name}"] = trait.value
    return facts


COUNTY_SHARES = ("drought", "excess_moisture", "heat", "freeze", "hail")


def county_facts(seasons: list[SeasonSummary]) -> dict:
    latest = seasons[-1] if seasons else None
    facts = {}
    for cause in COUNTY_SHARES:
        value = latest.scalars.get(f"rma_lag1_{cause}_share") if latest else None
        if value is not None:
            facts[f"county.rma_{cause}_share_lag1"] = float(value)
    return facts


FIELD_INPUTS = {"soil": "field.soil.", "practices": "field.practice."}


def _snake(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", str(name)).lower()


WET_CLASSES = {"poorly_drained": "wet", "very_poorly_drained": "wet"}
SOMEWHAT_WET_CLASSES = {"somewhat_poorly_drained": "somewhat_wet"}
ENUM_FACTS = ("field.soil.drainage_class", "field.practice.tillage", "field.practice.cover_crop")
NO_COVER = ("none", "no", "")
# derived fact -> the input it is computed from (reported in data gaps instead of the derived name)
DERIVED_FROM = {"field.soil.wetness": "field.soil.drainage_class"}


def _token(value) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def field_facts(field: dict, history: list[HistoryYear], seasons: list[SeasonSummary]) -> dict:
    """Field-level facts. `field["soil"]` (survey properties) and `field["practices"]`
    (farmer-declared management) are passed through as field.soil.* / field.practice.*;
    keys may be camelCase or snake_case, and None values are treated as not provided.

    Derived: field.soil.wetness (wet | somewhat_wet | not_wet | tiled) from the natural drainage
    class and the declared tile drainage, and field.practice.cover_planned (always present).
    """
    facts = {"field.has_history": bool(history), "field.has_seasons": bool(seasons)}
    for key, prefix in FIELD_INPUTS.items():
        for name, value in (field.get(key) or {}).items():
            if value is not None:
                facts[prefix + _snake(name)] = value
    for name in ENUM_FACTS:
        if name in facts:
            facts[name] = _token(facts[name])
    drainage = facts.get("field.soil.drainage_class")
    if drainage is not None:
        wetness = WET_CLASSES.get(drainage) or SOMEWHAT_WET_CLASSES.get(drainage) or "not_wet"
        if wetness != "not_wet" and facts.get("field.practice.tile_drained") is True:
            wetness = "tiled"  # SSURGO describes the natural, undrained condition
        facts["field.soil.wetness"] = wetness
    cover = facts.get("field.practice.cover_crop")
    facts["field.practice.cover_planned"] = cover is not None and cover not in NO_COVER
    return facts


@dataclass(frozen=True)
class HazardResult:
    seasons_total: int
    seasons_hit: int
    worst_year: int | None
    worst_value: float | None
    window: tuple[int, int]
    stage_doy: int
    calendar_kind: str
    per_season: tuple[tuple[int, float, bool], ...] = ()  # (year, aggregated value, hit)

    @property
    def share(self) -> float:
        return self.seasons_hit / self.seasons_total if self.seasons_total else 0.0


def hazard_result(
    hazard: Hazard, calendar: StageCalendar, seasons: list[SeasonSummary]
) -> HazardResult | None:
    """Evaluate a timed hazard over every season with data. None when the stage is unknown."""
    stage_doy = calendar.stages.get(hazard.stage)
    if stage_doy is None:
        return None
    start, end = stage_doy + hazard.window_days[0], stage_doy + hazard.window_days[1]
    total = hits = 0
    worst_year = worst_value = None
    per_season = []
    for season in seasons:
        value = season.window(hazard.metric, start, end, hazard.aggregate)
        if value is None:
            continue
        total += 1
        hit = value >= hazard.threshold if hazard.compare == "ge" else value <= hazard.threshold
        if hit:
            hits += 1
        per_season.append((season.year, float(value), bool(hit)))
        better = worst_value is None or (
            value > worst_value if hazard.compare == "ge" else value < worst_value
        )
        if better:
            worst_year, worst_value = season.year, float(value)
    return HazardResult(
        total,
        hits,
        worst_year,
        worst_value,
        (start, end),
        stage_doy,
        calendar.kind,
        tuple(per_season),
    )
