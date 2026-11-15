"""Rotation plan and strategy of a field, built from the ranked rotation advice.

``rotation_advice.py`` ranks the candidate crops for the coming season with the rule engine. This
module turns that ranking into what the field pages show: the crop to sow next, the crop that
follows it, the dates, the steps with their checkpoints, and what to do if conditions change. It
adds no agronomic rules of its own; every sentence below states a value or a finding the engine
returned.

The crop after the next one comes from a second engine run with the next crop appended to the
field's history. When that is impossible (no satellite crop history) the best-ranked crop of a
different group takes its place, and the plan says so.

Dates are medians of past seasons, not forecasts. The "fit" numbers rescale the engine's risk
score (lower is better) between the best-scoring candidate (100) and the worst (0); they compare
crops for this field and are not a yield or health prediction.
"""

import logging
from datetime import date, timedelta
from threading import Lock
from time import monotonic
from uuid import NAMESPACE_URL, uuid5

from app.core.errors import ResourceNotFound
from app.services.calendar_events import _from_doy, rotation_events
from app.services.rotation_advice import InvalidAdviceRequest

logger = logging.getLogger(__name__)

ADVICE_TTL_SECONDS = 6 * 3600
DEFAULT_WINDOW_DAYS = 14
CHECKPOINTS = {
    "harvest-current": "Harvest is finished and the residue is spread evenly.",
    "off-season": "The cover crop is seeded before the date and the seeding is recorded.",
    "soil-check": "The soil results are in and any lime or nutrient needs are planned.",
    "preparation": "The seedbed is workable, there is no standing water and the equipment is ready.",
    "sow": "The soil is workable and seed is on hand; record the sowing date.",
    "scout-flowering": "Flowering date, pest pressure and water stress are recorded.",
    "harvest-next": "Yield and harvest date are recorded to improve the next plan.",
}


class AdviceCache:
    """Caches the default rotation advice of a field, shared by the calendar and the strategy.

    Only the plain call (no crop, no priorities) is cached; anything else goes straight through.
    Failures are not cached, so a later request can retry.
    """

    def __init__(self, rotation, clock=monotonic):
        self.rotation, self.clock = rotation, clock
        self._cache: dict[tuple, tuple[float, dict]] = {}
        self._lock = Lock()

    def advise(self, field, crop, priorities, units, after=None):
        extra = {"after": after} if after else {}
        if crop is not None or priorities:
            return self.rotation.advise(field, crop, priorities, units, **extra)
        key = (
            field["id"],
            field.get("crop"),
            tuple(field["geometry"]["coordinates"]),
            units,
            after,
        )
        with self._lock:
            cached = self._cache.get(key)
            if cached and cached[0] > self.clock():
                return cached[1]
        advice = self.rotation.advise(field, None, [], units, **extra)
        with self._lock:
            self._cache[key] = (self.clock() + ADVICE_TTL_SECONDS, advice)
        return advice


def _ranked(advice: dict) -> list[dict]:
    return sorted(advice["candidates"], key=lambda item: item["rank"])


def _fit(candidates: list[dict]):
    """Rescale scores so the best candidate is 100 and the worst 0."""
    scores = [c["score"] for c in candidates]
    low, high = min(scores), max(scores)

    def fit(candidate: dict) -> int:
        if high == low:
            return 100
        return round(100 * (high - candidate["score"]) / (high - low))

    return fit


def _following(best: dict, ranked: list[dict], follow: dict | None) -> tuple[dict, bool]:
    """The crop after the best one, and whether it came from the extended-history engine run."""
    if follow and follow["candidates"]:
        return _ranked(follow)[0], True
    others = [c for c in ranked if c["group"] != best["group"]] or ranked[1:] or ranked
    return others[0], False


def _calendar_date(month_day: str, year: int) -> date | None:
    try:
        month, day = (int(part) for part in month_day.split("-"))
        return date(year, month, day)
    except (ValueError, AttributeError):
        return None


def build_plan(field: dict, advice: dict, follow: dict | None, today: date) -> dict | None:
    ranked = _ranked(advice)
    if not ranked:
        return None
    best = ranked[0]
    stages = (best.get("calendar") or {}).get("stages") or {}
    if not stages.get("planted"):
        return None
    sow = _from_doy(stages["planted"], today)
    intended = next((c for c in ranked if c["isIntended"]), None)
    following, extended = _following(best, ranked, follow)
    follow_planted = ((following.get("calendar") or {}).get("stages") or {}).get("planted")
    following_date = (
        _from_doy(follow_planted, today, sow.year + 1)
        if follow_planted
        else date(sow.year + 1, sow.month, sow.day)
    )

    timing = (advice.get("seasonTiming") or {}).get("crops", {}).get(best["crop"], {})
    window = (timing.get("stages") or {}).get("sow")
    window_end = _calendar_date(window["late"], sow.year) if window else None
    if window_end is None or window_end < sow:
        window_end = sow + timedelta(days=DEFAULT_WINDOW_DAYS)

    margin = ranked[1]["score"] - best["score"] if len(ranked) > 1 else 0
    span = ranked[-1]["score"] - best["score"]
    lead = max(0, min(100, round(100 * margin / span))) if span > 0 else 0

    changed = intended is not None and intended["crop"] != best["crop"]
    reasons = [
        f"{best['label']} ranks first for {field['name']} with a risk score of {best['score']:g} "
        "(lower means less risk)"
        + (f"; staying with {intended['label']} scores {intended['score']:g}." if changed else ".")
    ]
    reasons += [f"Benefit: {item['title']}." for item in best.get("benefits", [])[:2]]
    reasons += [f"Watch: {item['title']}." for item in best.get("risks", [])[:2]]
    if extended:
        reasons.append(
            f"After {best['label']}, {following['label']} ranks first (risk score "
            f"{following['score']:g}) when {best['label']} is added to the crop history."
        )
    else:
        reasons.append(
            f"{following['label']} is the best-ranked crop of a different crop group, so it "
            f"follows {best['label']}; the history could not be extended to rank it exactly."
        )

    calendar = best.get("calendar") or {}
    if calendar.get("localSource"):
        basis = (
            f"The regional sowing date is moved to your location using the sowing window "
            f"modelled from local weather ({window['early']} early, {window['typical']} typical, "
            f"{window['late']} late)."
            if window
            else "The regional sowing date is moved to your location."
        )
    else:
        basis = "It comes from the regional crop calendar (USDA crop progress, 50% planted)."
    explanation = (
        f"{sow.isoformat()} is the typical sowing date of {best['label']}. {basis} The window "
        f"ends {window_end.isoformat()}. These are medians of past seasons, not a forecast for "
        "this year."
    )

    history = [f"{y['year']} {y['crop']}" for y in advice.get("history", []) if y.get("crop")]
    soil = [
        f"{item['id']} {item['value']}" + (f" {item['unit']}" if item.get("unit") else "")
        for item in best.get("soil", [])[:3]
        if item.get("value") is not None
    ]
    record = advice.get("weatherRecord") or {}
    inputs = [
        ("Crop history", ", ".join(history[-5:]) or "Not available"),
        ("History source", (advice.get("historySource") or {}).get("kind") or "none"),
        ("Soil", ", ".join(soil) or "Not available"),
        ("Weather record", f"{record['seasons']} seasons" if record.get("seasons") else "None"),
        ("Priorities", ", ".join(advice.get("priorities") or []) or "None selected"),
        ("Data gaps", str(len(advice.get("dataGaps") or []) + len(best.get("dataGaps") or []))),
    ]
    return {
        "id": uuid5(NAMESPACE_URL, f"fieldsense:{field['id']}:plan:{best['crop']}"),
        "nextCropId": uuid5(NAMESPACE_URL, f"fieldsense:crop:{best['crop']}"),
        "followingCropId": uuid5(NAMESPACE_URL, f"fieldsense:crop:{following['crop']}"),
        "fieldId": field["id"],
        "currentCrop": field.get("crop") or (intended or best)["label"],
        "nextCrop": best["label"],
        "followingCrop": following["label"],
        "confidence": lead,
        "sowingDate": sow.isoformat(),
        "windowEnd": window_end.isoformat(),
        "followingDate": following_date.isoformat(),
        "dateExplanation": explanation,
        "reasons": reasons,
        "inputs": [{"label": label, "value": value} for label, value in inputs],
        "_best": best,
        "_window": window,
        "_timing": timing,
    }


def _contingencies(plan: dict, best: dict, window: dict | None, timing: dict) -> list[dict]:
    items = []
    if window:
        items.append(
            {
                "condition": "The soil is too wet or cold on the typical sowing date",
                "action": f"Wait for workable soil; {window['late']} is the late end of the "
                f"window in past years. Sowing later than that raises the heat and frost risk.",
            }
        )
    margin = timing.get("sowingDelayMarginDays")
    if margin is not None:
        items.append(
            {
                "condition": "Sowing has to be delayed",
                "action": f"The model finds a safe delay of up to {margin:g} days for "
                f"{best['label']} before the heat-at-flowering risk rises.",
            }
        )
    if (timing.get("heatAtFlowering") or {}).get("vulnerable"):
        items.append(
            {
                "condition": "A heatwave is forecast near flowering",
                "action": "Heat at flowering is a recognised risk here: plan irrigation and "
                "check the calendar for heatwave warnings.",
            }
        )
    items.append(
        {
            "condition": "The county reaches severe drought (D2) before sowing",
            "action": "Check soil moisture, consider a more drought-tolerant crop and open the "
            "crop recommendation again with the water priority.",
        }
    )
    items.append(
        {
            "condition": "You prefer another crop",
            "action": "Open the crop recommendation for that crop to see its risks and "
            "benefits before changing the plan.",
        }
    )
    return items


def build_strategy(field: dict, advice: dict, follow: dict | None, today: date) -> dict | None:
    plan = build_plan(field, advice, follow, today)
    if plan is None:
        return None
    best, window, timing = plan.pop("_best"), plan.pop("_window"), plan.pop("_timing")
    events = rotation_events(field, advice, today)
    steps = [
        {"event": event, "checkpoint": CHECKPOINTS.get(event["kind"], "Record what was done.")}
        for event in events
    ]
    ranked = _ranked(advice)
    fit = _fit(ranked)
    intended = next((c for c in ranked if c["isIntended"]), None)
    current = fit(intended) if intended else round(sum(map(fit, ranked)) / len(ranked))
    projected = fit(best)
    stage_dates = [("Today", today), ("Sowing", date.fromisoformat(plan["sowingDate"]))]
    stages = (best.get("calendar") or {}).get("stages") or {}
    sow = stage_dates[1][1]
    for stage, key in (("Flowering", "flowering"), ("Harvest", "harvested")):
        if stages.get(key):
            extra = 1 if stages[key] < stages["planted"] else 0
            stage_dates.append((stage, _from_doy(stages[key], today, sow.year + extra)))
    horizon = max((day - today).days for _, day in stage_dates) or 1
    forecast = [
        {
            "date": day.isoformat(),
            "stage": stage,
            "progress": round((day - today).days / horizon, 3),
            "health": current if stage == "Today" else projected,
            "currentHealth": current,
            "healthImprovement": [current, current if stage == "Today" else projected],
            "range": [min(current, projected), max(current, projected)],
        }
        for stage, day in stage_dates
    ]
    technicals = [
        {
            "key": "history",
            "parameter": "Crop history",
            "value": plan["inputs"][0]["value"],
            "role": "Previous crops set the rotation, disease and nitrogen findings of each candidate.",
        },
        {
            "key": "soil",
            "parameter": "Soil",
            "value": plan["inputs"][2]["value"],
            "role": "Soil indicators feed the water, erosion and soil findings.",
        },
        {
            "key": "sowing",
            "parameter": "Sowing date",
            "value": plan["sowingDate"],
            "role": "Moves the weather hazard windows (frost, heat) that the rules count.",
        },
        {
            "key": "weather",
            "parameter": "Weather record",
            "value": plan["inputs"][3]["value"],
            "role": "Past seasons set how often each hazard hit the sowing and flowering windows.",
        },
        {
            "key": "priorities",
            "parameter": "Priorities",
            "value": plan["inputs"][4]["value"],
            "role": "Selected priorities weight the matching findings in the score.",
        },
    ]
    return {
        "plan": plan,
        "events": events,
        "steps": steps,
        "forecast": forecast,
        "comparison": [{"name": "Rotation fit", "current": current, "projected": projected}],
        "technicals": technicals,
        "contingencies": _contingencies(plan, best, window, timing),
    }


class RotationStrategy:
    def __init__(self, advice: AdviceCache, weather):
        self.advice, self.weather = advice, weather

    def _build(self, field, preferences, builder):
        today = self.weather.today(preferences)
        try:
            advice = self.advice.advise(field, None, [], preferences.units)
        except Exception as error:
            logger.warning("Rotation advice unavailable: %s", type(error).__name__)
            raise ResourceNotFound("Rotation plan not available") from error
        ranked = _ranked(advice)
        follow = None
        if ranked:
            try:
                follow = self.advice.advise(
                    field, None, [], preferences.units, after=ranked[0]["crop"]
                )
            except InvalidAdviceRequest:
                follow = None
            except Exception as error:
                logger.info("Following crop unavailable: %s", type(error).__name__)
        result = builder(field, advice, follow, today)
        if result is None:
            raise ResourceNotFound("Rotation plan not available")
        return result

    def plan(self, field, preferences):
        plan = self._build(field, preferences, build_plan)
        for private in ("_best", "_window", "_timing"):
            plan.pop(private, None)
        return plan

    def strategy(self, field, preferences):
        return self._build(field, preferences, build_strategy)
