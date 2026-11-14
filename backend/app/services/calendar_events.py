"""Calendar events for fields: rotation dates and weather warnings.

Two sources feed the calendar, and both reuse existing services:

* Rotation: the ranked advice from ``rotation_advice.py`` carries stage calendars (already moved
  to the local sowing date by ``season_timing.py``) and the off-season cover-crop options. From
  them come the harvest of the crop now in the field, an autumn cover-crop sowing, the soil check
  and field preparation before sowing, sowing of the best-ranked crop, a scouting visit at
  flowering and the harvest of that crop. These dates are medians of past years, not forecasts.
* Warnings: the 14-day forecast from ``weather.py`` with the crop alerts of
  ``crop_conditions.py`` (heat, cold, heavy rain, wind, dry soil), multi-day heatwaves,
  thunderstorms and extreme rain or wind, and the county drought level from ``drought.py``.

Nothing here is stored. Event ids are derived from the field and the event, so they stay the same
between requests. A failing source removes only its own events.
"""

import logging
from datetime import date, timedelta
from threading import Lock
from time import monotonic
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException

from app.services.crop_conditions import assessment_context, field_location
from app.services.drought import NAMES as DROUGHT_NAMES
from app.services.drought import DroughtMonitor

logger = logging.getLogger(__name__)

ROTATION_TTL_SECONDS = 6 * 3600
WEATHER_CATEGORY = "Weather alert"
HEATWAVE_C = 32.0  # daily high, three days in a row
HEATWAVE_DAYS = 3
SEVERE_HEAT_C = 35.0
EXTREME_RAIN_MM = 50.0
EXTREME_WIND_KMH = 60.0
FROST_C = -2.0
FROST_MONTHS = range(4, 11)  # outside April-October a frost is the normal state
SOIL_CHECK_LEAD_DAYS = 21
PREPARATION_LEAD_DAYS = 10
CROP_ALERTS = {
    "heat_stress": ("Heat stress", WEATHER_CATEGORY),
    "cold_stress": ("Cold stress", WEATHER_CATEGORY),
    "heavy_precipitation": ("Heavy rain", WEATHER_CATEGORY),
    "strong_wind": ("Strong wind", WEATHER_CATEGORY),
    "dry_soil": ("Dry soil", "Irrigation"),
}
ADVICE = {
    "heat_stress": "Check irrigation and avoid field work in the afternoon heat.",
    "cold_stress": "Protect or inspect frost-sensitive crops before the cold night.",
    "heavy_precipitation": "Check drainage and postpone spraying and field work.",
    "strong_wind": "Secure equipment and postpone spraying.",
    "dry_soil": "Check soil moisture and plan irrigation.",
}


def _event_id(field_id: str, key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"fieldsense:{field_id}:{key}")


def _event(field, key, day, category, title, description, priority, duration, rationale):
    return {
        "kind": key.split(":")[0],  # not part of the API; the strategy reads it
        "id": _event_id(field["id"], key),
        "fieldId": field["id"],
        "fieldName": field["name"],
        "date": day.isoformat(),
        "category": category,
        "title": title,
        "description": description,
        "priority": priority,
        "duration": duration,
        "rationale": rationale,
    }


def _from_doy(doy: int, today: date, year: int | None = None) -> date:
    """The next date on or after today with this day of year (or in the given year)."""
    # The calendars count days in a non-leap year (2025 crop progress), so a day of year keeps
    # the same month and day in every year instead of drifting by one after a leap day.
    base = date(2001, 1, 1) + timedelta(days=min(doy, 365) - 1)
    if year is not None:
        return date(year, base.month, base.day)
    day = date(today.year, base.month, base.day)
    return day if day >= today else date(today.year + 1, base.month, base.day)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


def _runs(flags: list[tuple[str, bool]]) -> list[tuple[int, int]]:
    """Index ranges (first, last) of consecutive days whose flag is set."""
    runs, start = [], None
    for index, (_, flag) in enumerate(flags):
        if flag and start is None:
            start = index
        if not flag and start is not None:
            runs.append((start, index - 1))
            start = None
    if start is not None:
        runs.append((start, len(flags) - 1))
    return runs


def rotation_events(field: dict, advice: dict, today: date) -> list[dict]:
    """Dates implied by the ranked rotation advice for one field."""
    candidates = sorted(advice["candidates"], key=lambda item: item["rank"])
    if not candidates:
        return []
    best = candidates[0]
    intended = next((item for item in candidates if item["isIntended"]), None)
    events = []
    stages = (best.get("calendar") or {}).get("stages") or {}
    changed = intended is not None and intended["crop"] != best["crop"]
    top_findings = [item["title"] for item in best.get("risks", [])[:2]] + [
        item["title"] for item in best.get("benefits", [])[:2]
    ]

    if intended and field.get("crop"):
        harvest = (intended.get("calendar") or {}).get("stages", {}).get("harvested")
        if harvest and (when := _from_doy(harvest, today, today.year)) >= today:
            events.append(
                _event(
                    field, f"harvest-current:{intended['crop']}:{when.year}", when, "Harvest",
                    f"Harvest {intended['label']}",
                    f"Typical harvest date for {intended['label']} in this region"
                    + (" moved to local conditions." if intended["calendar"].get("localShiftDays") else "."),
                    "Routine", "1-2 weeks",
                    "Median harvest date of past seasons from the crop calendar; the real date "
                    "depends on this year's weather and crop moisture.",
                )
            )  # fmt: skip

    off_season = advice.get("offSeason") or {}
    options = [o for o in off_season.get("options", []) if o["level"] in ("reliable", "marginal")]
    if off_season.get("status") == "ok" and options and off_season.get("seedingDoy"):
        when = _from_doy(off_season["seedingDoy"], today, today.year)
        option = max(options, key=lambda o: (o["level"] == "reliable", o["share"]))
        if when >= today:
            events.append(
                _event(
                    field, f"off-season:{option['id']}:{when.year}", when, "Field preparation",
                    f"Seed {option['label'].lower()}",
                    f"Establish {option['label'].lower()} after harvest of "
                    f"{off_season.get('afterCrop') or 'the previous crop'}.",
                    "Routine" if option["level"] == "reliable" else "Important", "1 day",
                    f"Established in {option['seasonsMet']} of {option['seasonsTotal']} past "
                    f"autumns ({option['level']}); the date is one week after typical harvest.",
                )
            )  # fmt: skip

    planted = stages.get("planted")
    if not planted:
        return events
    sow = _from_doy(planted, today)
    if sow - today > timedelta(days=400):
        return events
    score_note = f"score {best['score']:g}"
    if changed:
        score_note += f" against {intended['score']:g} for {intended['label']}"
    reasons = "; ".join(top_findings) if top_findings else "see the crop recommendation"
    key = f"{best['crop']}:{sow.year}"

    soil_day = max(today, sow - timedelta(days=SOIL_CHECK_LEAD_DAYS))
    events.append(
        _event(
            field, f"soil-check:{key}", soil_day, "Soil check",
            f"Soil check before sowing {best['label']}",
            "Sample the soil and review moisture, pH and nutrient status before field work.",
            "Routine", "2 hours",
            f"Planned {SOIL_CHECK_LEAD_DAYS} days before the typical sowing date of "
            f"{best['label']} ({sow.isoformat()}).",
        )
    )  # fmt: skip
    prep_day = max(today, sow - timedelta(days=PREPARATION_LEAD_DAYS))
    events.append(
        _event(
            field, f"preparation:{key}", prep_day, "Field preparation",
            f"Prepare the field for {best['label']}",
            "Seedbed preparation, residue management and equipment check.",
            "Routine", "1-2 days",
            f"Planned {PREPARATION_LEAD_DAYS} days before sowing; start only when the soil is "
            "workable.",
        )
    )  # fmt: skip
    timing = (advice.get("seasonTiming") or {}).get("crops", {}).get(best["crop"], {})
    window = (timing.get("stages") or {}).get("sow")
    window_text = (
        f" Early to late window in past years: {window['early']} to {window['late']}."
        if window
        else ""
    )
    events.append(
        _event(
            field, f"sow:{key}", sow, "Crop rotation",
            f"Sow {best['label']}",
            f"Best-ranked crop for the coming season ({score_note}; lower is less risk)."
            + window_text,
            "High priority" if changed else "Important", "1-3 days",
            f"Typical sowing date from the rotation advice. Main factors: {reasons}.",
        )
    )  # fmt: skip

    flowering = stages.get("flowering")
    if flowering:
        when = _from_doy(flowering, today, sow.year)
        vulnerable = (timing.get("heatAtFlowering") or {}).get("vulnerable")
        events.append(
            _event(
                field, f"scout-flowering:{key}", when, "Crop inspection",
                f"Scout {best['label']} at flowering",
                "Check flowering, pests and water stress; flowering is the most heat-sensitive stage."
                + (" Heat at flowering is a recognised risk for this location." if vulnerable else ""),
                "Important" if vulnerable else "Routine", "2 hours",
                "Median flowering date of past seasons from the crop calendar.",
            )
        )  # fmt: skip
    harvested = stages.get("harvested")
    if harvested:
        when = _from_doy(harvested, today, sow.year + (1 if harvested < planted else 0))
        events.append(
            _event(
                field, f"harvest-next:{key}", when, "Harvest",
                f"Harvest {best['label']}",
                f"Typical harvest date for {best['label']} sown on {sow.isoformat()}.",
                "Routine", "1-2 weeks",
                "Median harvest date of past seasons; the real date follows the season's weather.",
            )
        )  # fmt: skip
    return events


def _celsius(value, units):
    if value is None:
        return None
    return (value - 32) * 5 / 9 if units.get("temperature") == "°F" else value


def _mm(value, units):
    if value is None:
        return None
    return value * 25.4 if units.get("rainfall") == "in" else value


def _kmh(value, units):
    if value is None:
        return None
    return value * 1.609344 if units.get("wind") == "mph" else value


def _span(records, first, last):
    days = last - first + 1
    return records[first]["date"], _plural(days, "day")


def weather_events(field: dict, series: dict) -> list[dict]:
    """Warnings from a forecast series that already carries the crop assessment."""
    records, units = series["records"], series["units"]
    events = []

    def add(key, first, last, category, title, description, priority, rationale):
        day, duration = _span(records, first, last)
        events.append(
            _event(
                field, f"{key}:{day}", date.fromisoformat(day), category, title, description,
                priority, duration, rationale,
            )
        )  # fmt: skip

    highs = [(r["date"], (_celsius(r["temperature"], units) or -99) >= HEATWAVE_C) for r in records]
    heat = [run for run in _runs(highs) if run[1] - run[0] + 1 >= HEATWAVE_DAYS]
    for first, last in heat:
        peak = max(_celsius(r["temperature"], units) for r in records[first : last + 1])
        severe = peak >= SEVERE_HEAT_C
        add(
            "heatwave", first, last, WEATHER_CATEGORY, "Heatwave expected",
            f"Daily highs of {HEATWAVE_C:g} °C or more for {_plural(last - first + 1, 'day')}, "
            f"peaking near {peak:.0f} °C. Plan irrigation and avoid heavy work at midday.",
            "High priority" if severe else "Important",
            f"Forecast highs of at least {HEATWAVE_C:g} °C on {HEATWAVE_DAYS} or more days in a row.",
        )  # fmt: skip
    for index, record in enumerate(records):
        rain = _mm(record["rainfall"], units)
        wind = _kmh(record["wind"], units)
        low = _celsius(record["low"], units)
        month = int(record["date"][5:7])
        if (record.get("weatherCode") or 0) >= 95:
            add(
                "thunderstorm", index, index, WEATHER_CATEGORY, "Thunderstorms expected",
                "Lightning and possible hail. Postpone field work and spraying.", "Important",
                f"Forecast weather code {record['weatherCode']} (thunderstorm).",
            )  # fmt: skip
        if rain is not None and rain >= EXTREME_RAIN_MM:
            add(
                "extreme-rain", index, index, WEATHER_CATEGORY, "Extreme rainfall expected",
                f"About {rain:.0f} mm of rain in one day. Check drainage and erosion risk.",
                "High priority", f"Forecast daily rain of at least {EXTREME_RAIN_MM:g} mm.",
            )  # fmt: skip
        if wind is not None and wind >= EXTREME_WIND_KMH:
            add(
                "extreme-wind", index, index, WEATHER_CATEGORY, "Damaging wind expected",
                f"Gusts of the day up to about {wind:.0f} km/h. Secure equipment and covers.",
                "High priority", f"Forecast wind of at least {EXTREME_WIND_KMH:g} km/h.",
            )  # fmt: skip
        if low is not None and low <= FROST_C and month in FROST_MONTHS:
            add(
                "frost", index, index, WEATHER_CATEGORY, "Hard frost expected",
                f"Night low near {low:.0f} °C during the growing season. Protect sensitive crops.",
                "High priority", f"Forecast low of {FROST_C:g} °C or colder between April and October.",
            )  # fmt: skip

    crop = (series.get("cropAssessment") or {}).get("context", {}).get("crop")
    for rule, (label, category) in CROP_ALERTS.items():
        flags = [
            (
                r["date"],
                any(
                    a["ruleId"] == rule and a["severity"] == "high"
                    for a in (r.get("cropAssessment") or {}).get("alerts", [])
                ),
            )
            for r in records
        ]
        for first, last in _runs(flags):
            if rule == "cold_stress" and int(records[first]["date"][5:7]) not in FROST_MONTHS:
                continue
            if rule == "heat_stress" and any(f <= last and first <= s for f, s in heat):
                continue  # already covered by the heatwave warning
            add(
                f"crop-{rule}", first, last, category, f"{label} risk for {crop}",
                ADVICE[rule], "Important",
                "The crop-weather rules rate the forecast as high risk for this crop and soil.",
            )  # fmt: skip
    return events


def drought_events(field: dict, status: dict | None, today: date) -> list[dict]:
    if not status or not status.get("category"):
        return []
    category = status["category"]
    name = DROUGHT_NAMES[category]
    priority = {"d0": "Routine", "d1": "Important"}.get(category, "High priority")
    worsening = status["trend"] == "worsening"
    share = status["shares"][category]
    return [
        _event(
            field, f"drought:{category}:{status['mapDate']}", today, WEATHER_CATEGORY,
            f"{name} in {status['county'] or 'the county'}",
            f"The U.S. Drought Monitor map of {status['mapDate']} rates {share:.0f}% of the county "
            f"as {name.lower()} or worse ({status['trend']} over the last "
            f"{status['weeksCompared']} weeks). Review irrigation and moisture-saving practices.",
            "High priority" if worsening and priority != "Routine" else priority, "Ongoing",
            "County drought category covering at least 30% of the area, from the weekly "
            "U.S. Drought Monitor.",
        )
    ]  # fmt: skip


class CalendarEvents:
    def __init__(self, weather, crop_model, rotation, drought: DroughtMonitor, clock=monotonic):
        self.weather, self.crop_model, self.rotation = weather, crop_model, rotation
        self.drought, self.clock = drought, clock
        self._rotation_cache: dict[tuple, tuple[float, list[dict]]] = {}
        self._lock = Lock()

    def _rotation(self, field, preferences, today):
        key = (field["id"], today, preferences.units, tuple(field["geometry"]["coordinates"]))
        with self._lock:
            cached = self._rotation_cache.get(key)
            if cached and cached[0] > self.clock():
                return cached[1]
        try:
            advice = self.rotation.advise(field, None, [], preferences.units)
            events = rotation_events(field, advice, today)
        except Exception as error:
            logger.warning("Rotation calendar unavailable: %s", type(error).__name__)
            return []  # not cached, so a later request can retry
        with self._lock:
            self._rotation_cache[key] = (self.clock() + ROTATION_TTL_SECONDS, events)
        return events

    def _weather(self, field, preferences):
        try:
            series = self.weather.forecast(field_location(preferences, field))
            context = assessment_context(series, field)
            if context is not None:
                series = self.crop_model.predict(series, context)
            return weather_events(field, series)
        except HTTPException as error:
            logger.info("Weather warnings unavailable: %s", error.detail)
        except Exception as error:
            logger.warning("Weather warnings failed: %s", type(error).__name__)
        return []

    def _drought(self, field, today):
        lon, lat = field["geometry"]["coordinates"]
        try:
            return drought_events(field, self.drought.status(lat, lon, today), today)
        except Exception as error:
            logger.info("Drought status unavailable: %s", type(error).__name__)
            return []

    def for_field(self, field: dict, preferences) -> list[dict]:
        today = self.weather.today(preferences)
        events = [
            *self._rotation(field, preferences, today),
            *self._weather(field, preferences),
            *self._drought(field, today),
        ]
        return sorted(events, key=lambda event: (event["date"], event["title"]))

    def for_fields(self, fields: list[dict], preferences) -> list[dict]:
        events = [event for field in fields for event in self.for_field(field, preferences)]
        return sorted(events, key=lambda event: (event["date"], event["fieldName"], event["title"]))
