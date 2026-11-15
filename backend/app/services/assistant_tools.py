"""Tools the assistant can call on demand, instead of loading all data into every prompt.

A tool is a function ``handler(ChatContext, args) -> dict | None`` with a name, a description
the model reads to decide when to call it, and an optional JSON-schema ``parameters`` object.
ML integrations register themselves at startup:

    app.state.assistant_tools.register(
        Tool("get_crop_zones", "Crop zones of the selected field ...", crop_zones_tool)
    )

Tools run while the response is streaming, after the request's database session is gone. A
handler must therefore only use ``ChatContext`` (plain data resolved before streaming starts)
and app services from ``ctx.state``; it must not touch the database session.

``ToolRegistry.call`` never raises: failures become ``{"error"|"status": ...}`` results the model
can explain to the user. These services are shared with the frontend endpoints; tools only call
them and never change them.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from functools import cached_property

from fastapi import HTTPException

from app.services.crop_conditions import assessment_context, field_location
from app.services.rotation_advice import InvalidAdviceRequest
from app.services.weather_insight import forecast_insight_input

logger = logging.getLogger(__name__)

MAX_RESULT_CHARS = 20_000
NO_FIELD = {
    "status": "unavailable",
    "reason": "No field is selected. Ask the user to select a field.",
}


class ChatContext:
    """Per-request inputs shared by all tools. Plain data only; see the module docstring."""

    def __init__(
        self,
        state,
        location,
        field,
        locale: str,
        fields=(),
        calendar_date: date | None = None,
        weather_date: date | None = None,
    ):
        self.state = state
        self.location = location  # snapshot of the account's saved location and units
        self.field = field  # selected field dict, or None
        self.locale = locale
        self.fields = list(fields)  # snapshot of all the account's fields (calendar tool)
        self.calendar_date = calendar_date  # day selected on the calendar page, or None
        self.weather_date = weather_date  # forecast day open on the weather page, or None

    @cached_property
    def series(self):
        """Forecast for the field point (or saved account location) with crop assessment."""
        location = field_location(self.location, self.field) if self.field else self.location
        series = self.state.weather.forecast(location)
        context = assessment_context(series, self.field) if self.field else None
        if context is not None:
            return self.state.crop_model.predict(series, context)
        return series


ToolHandler = Callable[[ChatContext, dict], dict | None]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    handler: ToolHandler
    parameters: dict | None = None  # JSON schema of the arguments; None = no arguments

    def declaration(self) -> dict:
        declaration = {"name": self.name, "description": self.description}
        if self.parameters:
            declaration["parameters"] = self.parameters
        return declaration


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Assistant tool {tool.name!r} is already registered")
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return list(self._tools)

    def describe(self) -> list[dict]:
        return [{"name": t.name, "description": t.description} for t in self._tools.values()]

    def declarations(self, names: list[str] | None = None) -> list[dict]:
        """Function declarations for the model; all tools when names is None."""
        return [t.declaration() for t in self._tools.values() if names is None or t.name in names]

    def call(self, name: str, ctx: ChatContext, args: dict) -> dict:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"Unknown tool {name!r}"}
        try:
            result = tool.handler(ctx, args)
        except HTTPException as error:
            return {"status": "unavailable", "reason": str(error.detail)}
        except Exception as error:
            logger.warning("Assistant tool %r failed: %s", name, type(error).__name__)
            return {"error": "The tool failed, so this data is unavailable right now."}
        if result is None:
            return {"status": "unavailable", "reason": "No data for this request."}
        if not isinstance(result, dict):
            result = {"result": result}
        text = json.dumps(result, ensure_ascii=False, default=str)
        if len(text) > MAX_RESULT_CHARS:
            logger.warning("Assistant tool %r result truncated (%d chars)", name, len(text))
            return {
                "status": "truncated",
                "note": "Result too large; only the start is shown.",
                "preview": text[:MAX_RESULT_CHARS],
            }
        return json.loads(text)  # guarantees a JSON-safe result


def weather_forecast_tool(ctx: ChatContext, args: dict) -> dict | None:
    records = ctx.series.get("records")
    if not records:
        return None
    day = args.get("date") or (ctx.weather_date.isoformat() if ctx.weather_date else None)
    day = day if isinstance(day, str) else records[0]["date"]
    result = forecast_insight_input(ctx.series, day, ctx.locale)
    if result is None:
        first, last = records[0]["date"], records[-1]["date"]
        return {
            "status": "unavailable",
            "reason": f"No forecast for {day}; the forecast covers {first} to {last}.",
        }
    return result


def m3_insights_tool(ctx: ChatContext, args: dict) -> dict | None:
    if not ctx.field:
        return NO_FIELD
    lon, lat = ctx.field["geometry"]["coordinates"]
    with_delay = args.get("include_delay_scan") is True
    result = ctx.state.m3_advice.lookup(lat, lon, include_delay_scan=with_delay)
    if not result.get("ok"):
        return {"status": "unavailable", "error": result.get("error")}
    # Drop the echoed query and file bookkeeping; keep what answers agronomic questions.
    keep = ("match", "windows", "risk", "fallow_zero", "delay_scan", "warnings")
    return {"status": "ready", **{key: result[key] for key in keep if result.get(key)}}


def soil_depletion_tool(ctx: ChatContext, args: dict) -> dict | None:
    """Never waits: the index is computed in the background and can take ~100 s."""
    if not ctx.field:
        return NO_FIELD
    from app.services.crop_history import analysis_point  # heavy import, as in the fields API

    result = ctx.state.soil_assessments.get(analysis_point(ctx.field, 0))
    if result.status != "ready":
        # get() has started (or is already running) the calculation, so a later turn can use it.
        return {
            "status": result.status,
            "note": (
                "The calculation is still running and there is no result yet. Do not estimate "
                "it and do not call this tool again in this answer; tell the user to ask again "
                "in a minute or two."
            ),
        }
    return {
        "status": "ready",
        "assessment": result.assessment.model_dump(mode="json", exclude_none=True),
    }


def m2_evidence_tool(ctx: ChatContext, args: dict) -> dict | None:
    if not ctx.field:
        return NO_FIELD
    lon, lat = ctx.field["geometry"]["coordinates"]
    crop = args.get("crop") if args.get("crop") in ("corn", "soybeans") else None
    treatments = [t for t in args.get("treatments") or [] if t in ("T1", "T2", "T3", "T4", "T5")]
    result = ctx.state.m2_evidence.lookup(lat, lon, crop, treatments or None)
    if not result.get("ok"):
        return {"status": "unavailable", "error": result.get("error")}
    # Per-outcome tables and file bookkeeping are large; the headline and summary answer
    # agronomic questions.
    region = {
        crop_name: {
            name: {key: value for key, value in block.items() if key != "outcomes"}
            for name, block in blocks.items()
        }
        for crop_name, blocks in result["region"].items()
    }
    keep = ("evidence_label", "match", "field", "neighbourhood", "summary", "warnings")
    return {
        "status": "ready",
        **{key: result[key] for key in keep if result.get(key)},
        "region": region,
    }


def soil_moisture_tool(ctx: ChatContext, args: dict) -> dict | None:
    if not ctx.field:
        return NO_FIELD
    from app.services import soil_moisture
    from app.services.crop_history import analysis_point  # heavy import, as in the fields API

    weather = ctx.state.weather
    coordinates = analysis_point(ctx.field, 0)
    current = soil_moisture.current(weather, coordinates)
    result = {"status": "ready", "current": current.model_dump(mode="json", exclude_none=True)}
    if args.get("compare_to_past_years") is True:
        comparison = soil_moisture.compare_to_history(weather, coordinates, current)
        result["comparison"] = comparison.model_dump(mode="json", exclude_none=True)
    return result


MAX_CALENDAR_EVENTS = 30
MAX_CALENDAR_DAYS = 14
EVENT_KEYS = (
    "date",
    "fieldName",
    "category",
    "title",
    "description",
    "priority",
    "duration",
    "rationale",
)


def calendar_events_tool(ctx: ChatContext, args: dict) -> dict | None:
    """Calendar events (rotation dates and weather or drought warnings) for one day or a short range."""
    try:
        start = date.fromisoformat(args["date"]) if args.get("date") else ctx.calendar_date
    except (TypeError, ValueError):
        return {"status": "unavailable", "error": "date must be YYYY-MM-DD"}
    start = start or ctx.state.weather.today(ctx.location)
    days = args.get("days")
    days = days if isinstance(days, int) and 1 <= days <= MAX_CALENDAR_DAYS else 1
    fields = [ctx.field] if ctx.field else ctx.fields
    if not fields:
        return {"status": "unavailable", "reason": "The account has no fields."}
    end = start + timedelta(days=days)
    events = [
        event
        for event in ctx.state.calendar.for_fields(fields, ctx.location)
        if start.isoformat() <= event["date"] < end.isoformat()
    ]
    return {
        "status": "ready",
        "from": start.isoformat(),
        "to": (end - timedelta(days=1)).isoformat(),
        "total": len(events),
        "events": [
            {key: event[key] for key in EVENT_KEYS} for event in events[:MAX_CALENDAR_EVENTS]
        ],
    }


def _field_point(field) -> tuple[float, float]:
    lng, lat = field["geometry"]["coordinates"]
    return lat, lng


def _optional_number(value) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def crop_production_tool(ctx: ChatContext, args: dict) -> dict | None:
    """Past-year crop production of the selected field or of counties/a state, from USDA NASS."""
    from app.services import crop_production
    from app.services.nass import NassUnavailable

    nass = ctx.state.nass
    try:
        year = int(args["year"])
    except (KeyError, TypeError, ValueError):
        return {"status": "unavailable", "reason": "year is required (a past crop year)"}
    try:
        if args.get("counties") or args.get("state"):
            counties = args.get("counties")
            result = crop_production.region_production(
                nass,
                year,
                counties if isinstance(counties, list) else None,
                args.get("state"),
                [args["crop"]] if args.get("crop") else None,
            )
        else:
            if not ctx.field:
                return NO_FIELD
            lat, lng = _field_point(ctx.field)
            result = crop_production.field_production(
                nass,
                year,
                lat,
                lng,
                args.get("crop"),
                ctx.field["area"],
                min(_optional_number(args.get("snap_m")) or 0.0, 500.0),
            )
    except (NassUnavailable, ValueError) as error:
        return {"status": "unavailable", "reason": str(error)}
    return {"status": "ready", **result}


def _overrides(rows) -> dict:
    """[{crop, value}] from the model as {crop: value}."""
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("crop")): row.get("value")
        for row in rows
        if isinstance(row, dict) and row.get("crop")
    }


def crop_revenue_tool(ctx: ChatContext, args: dict) -> dict | None:
    """Expected gross revenue and ROI of a crop plan for the selected field, from USDA NASS."""
    from app.services import crop_revenue

    if not ctx.field:
        return NO_FIELD
    plan = args.get("plan")
    if not isinstance(plan, list) or not plan:
        return {"status": "unavailable", "reason": "plan is required: [{startDate, crop}, ...]"}
    crops = {
        str(entry.get("startDate")): entry.get("crop") for entry in plan if isinstance(entry, dict)
    }
    investment = args.get("investment")
    if isinstance(investment, list):
        investment = {
            str(row.get("year")): row.get("amount") for row in investment if isinstance(row, dict)
        }
    lat, lng = _field_point(ctx.field)
    result = crop_revenue.forecast(
        ctx.state.nass,
        lat,
        lng,
        crops,
        area_ha=ctx.field["area"],
        investment=investment,
        attribute="harvest" if args.get("attribute") == "harvest" else "start",
        price_override=_overrides(args.get("prices")),
        yield_override=_overrides(args.get("yields")),
    )
    return {"status": "ready" if result["crops"] else "unavailable", **result}


PRIORITIES = ("water", "soil", "erosion", "income", "pest_break")
DETAILED_CANDIDATES = 3  # the intended crop and the best-ranked crops get full detail


def _finding(finding: dict) -> dict:
    keep = ("ruleId", "title", "category", "level", "points", "yieldFactor", "evidenceStrength")
    return {key: finding[key] for key in keep if finding.get(key) is not None}


def _candidate(candidate: dict, detailed: bool) -> dict:
    result = {
        key: candidate[key]
        for key in ("crop", "label", "group", "rank", "isIntended", "score", "scoreBreakdown")
    }
    for kind in ("risks", "benefits", "advisories"):
        result[kind] = [_finding(item) for item in candidate[kind]]
    if detailed:
        for key in ("yield", "revenue", "calendar", "soil", "dataGaps", "needsLocalReview"):
            if candidate.get(key):
                result[key] = candidate[key]
    return result


def rotation_advice_tool(ctx: ChatContext, args: dict) -> dict | None:
    """The data behind the crop recommendation page for one crop (``/recommendation/<crop>``)."""
    if not ctx.field:
        return NO_FIELD
    crop = args.get("crop") if isinstance(args.get("crop"), str) else None
    priorities = [p for p in args.get("priorities") or [] if p in PRIORITIES]
    advise = ctx.state.rotation.advise
    try:
        advice = advise(ctx.field, crop, priorities, ctx.location.units)
    except InvalidAdviceRequest as error:
        if crop is None:
            return {"status": "unavailable", "error": str(error)}
        # Let the model correct itself: list the crops it may ask for.
        options = advise(ctx.field, None, [], ctx.location.units)["cropOptions"]
        return {
            "status": "unavailable",
            "error": str(error),
            "cropOptions": [option["id"] for option in options],
        }
    candidates = [
        _candidate(item, item["isIntended"] or item["rank"] <= DETAILED_CANDIDATES)
        for item in advice["candidates"]
    ]
    keep = (
        "intendedCrop",
        "intendedCropSource",
        "region",
        "asOf",
        "areaHa",
        "units",
        "priorities",
        "historySource",
        "history",
        "weatherRecord",
        "offSeason",
        "scoring",
        "dataGaps",
    )
    return {
        "status": "ready",
        **{key: advice[key] for key in keep if advice.get(key) is not None},
        "cropOptions": [option["id"] for option in advice["cropOptions"]],
        "candidates": candidates,
    }


def default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            "get_weather_forecast",
            "Daily weather forecast for the next 3 days at the selected field, or at the user's "
            "saved location when no field is selected: conditions, temperature, overnight low, "
            "rainfall, rain chance, soil moisture, humidity, wind, plus crop-risk level and "
            "rule alerts (e.g. frost, heat, waterlogging) for the field's crop. Use for "
            "questions about upcoming weather, frost or rain, or short-term crop risk. Starts "
            "at the day open on the weather page when there is one, else today.",
            weather_forecast_tool,
            {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "First day, YYYY-MM-DD, within the 14-day forecast. "
                        "Defaults to the day open on the weather page, else today.",
                    }
                },
            },
        )
    )
    registry.register(
        Tool(
            "get_m3_insights",
            "Climate-based crop timing and risk for the selected field from precomputed models: "
            "typical planting, harvest and frost date windows now and under future climate "
            "scenarios, heat and frost risk probabilities per crop, and cover-crop (Fallow-Zero) "
            "water-shortfall estimates. Use for planting dates, season length, climate risk or "
            "fallow and cover-crop decisions. Needs a selected field.",
            m3_insights_tool,
            {
                "type": "object",
                "properties": {
                    "include_delay_scan": {
                        "type": "boolean",
                        "description": "Also include how heat and frost risk change if sowing "
                        "is delayed by several days. Large; set true only when the user asks "
                        "about delaying planting.",
                    }
                },
            },
        )
    )
    registry.register(
        Tool(
            "get_soil_depletion",
            "Soil depletion screening index (0-100, higher means more depletion risk) for the "
            "selected field, with level, component scores (rotation, greenness, soil, county "
            "yield), main drivers and supporting metrics. Use for questions about soil health, "
            "crop rotation load or nutrient depletion. It can take a minute on first use: the "
            "result may say pending. Needs a selected field.",
            soil_depletion_tool,
        )
    )
    registry.register(
        Tool(
            "get_neighbour_evidence",
            "Observational evidence from neighbouring fields on whether crop-rotation practices "
            "(continuous cropping, diverse rotation, small grain or hay, winter cover, "
            "host-crop return interval) changed drought resilience, measured from satellite "
            "greenness under the same weather. Returns a verdict, the extra effect in drought "
            "with intervals, and a what-if for this field or nearby fields. Report the evidence tier "
            "and confidence; below the full tier there is no drought-specific number. It is an "
            "adjusted association, not a guaranteed effect: state that and any warnings. Use "
            "for questions about rotation, drought resilience or what neighbours' practices "
            "suggest. Needs a selected field.",
            m2_evidence_tool,
            {
                "type": "object",
                "properties": {
                    "crop": {
                        "type": "string",
                        "enum": ["corn", "soybeans"],
                        "description": "Limit the answer to one crop.",
                    },
                    "treatments": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["T1", "T2", "T3", "T4", "T5"]},
                        "description": "Limit to practices: T1 continuous crop, T2 diverse "
                        "rotation, T3 small grain or hay, T4 winter cover, T5 host-crop "
                        "return interval.",
                    },
                },
            },
        )
    )
    registry.register(
        Tool(
            "get_calendar_events",
            "Planned calendar events of the user's fields on one day or a short range: rotation "
            "dates (harvest, cover crop, soil check, field preparation, sowing, scouting) and "
            "weather warnings (heatwave, storms, frost, heavy rain, wind, drought), each with "
            "its description, priority, duration and the reason it is scheduled. Covers the "
            "selected field, or all fields when none is selected. Defaults to the day selected "
            "on the calendar page. Use it to explain what is planned and why.",
            calendar_events_tool,
            {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "First day, YYYY-MM-DD. Defaults to the selected calendar "
                        "day, else today.",
                    },
                    "days": {
                        "type": "integer",
                        "description": f"Number of days from date, 1 to {MAX_CALENDAR_DAYS}. "
                        "Default 1.",
                    },
                },
            },
        )
    )
    registry.register(
        Tool(
            "get_soil_moisture",
            "Modelled soil moisture at the selected field's reference point: latest value per "
            "soil layer (m3/m3) and the profile mean. Optionally compares it with the same "
            "time of year in past years (anomaly and percentile). Use for questions about how "
            "wet or dry the soil is now, irrigation or field access. Needs a selected field.",
            soil_moisture_tool,
            {
                "type": "object",
                "properties": {
                    "compare_to_past_years": {
                        "type": "boolean",
                        "description": "Also compare with past years. Slower; set true only "
                        "when the user asks whether it is wetter or drier than usual.",
                    }
                },
            },
        )
    )
    registry.register(
        Tool(
            "get_rotation_advice",
            "Ranked next-crop advice for the selected field from the rotation rule engine: "
            "score per candidate crop (lower means less risk) with its breakdown, risks, "
            "benefits and advisories (rotation, disease, weather, soil), yield and gross revenue "
            "estimates, sowing calendar, soil indicators, off-season cover-crop options, the "
            "crop history it used (satellite-estimated, not farmer records) and the data gaps. "
            "This is what the crop recommendation page shows for a crop. Use it to explain why a "
            "crop ranks where it does, to compare crops, or to suggest what to grow next. "
            "Explain rankings from the returned findings only. Needs a selected field.",
            rotation_advice_tool,
            {
                "type": "object",
                "properties": {
                    "crop": {
                        "type": "string",
                        "description": "Crop id to assess as the intended crop (the page's "
                        "crop). Defaults to the field's crop. If rejected, the "
                        "error returns the valid crop ids in cropOptions.",
                    },
                    "priorities": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(PRIORITIES)},
                        "description": "What the user cares about most; it reweights the "
                        "scores. Set only when the user states priorities.",
                    },
                },
            },
        )
    )
    registry.register(
        Tool(
            "get_crop_production",
            "How much crop the selected field, or counties or a state, produced in a PAST year, "
            "from USDA NASS (U.S. only; needs the server's NASS key). For the field it is its "
            "area x the county-average yield of that year, in bushels or tons, short tons and "
            "tonnes: an expected value, never a harvest record. Crop defaults to the "
            "satellite crop map (CDL) at the field point; pass crop to override. For a region "
            "give counties (5-digit FIPS) or a state (2-digit FIPS) to get NASS production "
            "totals. Unpublished (current-season) years have no data.",
            crop_production_tool,
            {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "Past crop year, e.g. 2023."},
                    "crop": {
                        "type": "string",
                        "description": "corn, soybeans, winter wheat, spring wheat, oats, "
                        "barley, rye, sorghum, alfalfa hay, other hay. Field: overrides the "
                        "map crop. Region: limits the result to one crop (default all).",
                    },
                    "counties": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "5-digit county FIPS codes for a region result.",
                    },
                    "state": {
                        "type": "string",
                        "description": "2-digit state FIPS for a whole-state region result.",
                    },
                    "snap_m": {
                        "type": "number",
                        "description": "Field only: if the point is not a crop pixel, look "
                        "this many metres around it (max 500) for the crop.",
                    },
                },
                "required": ["year"],
            },
        )
    )
    registry.register(
        Tool(
            "get_crop_revenue",
            "Expected gross revenue (low, base, high) of a crop plan on the selected field, and "
            "ROI when an investment is given, from USDA NASS yield trends and prices received "
            "(U.S. only; nominal dollars; county-average yields; no costs except the given "
            "investment). Use it to compare what crops could earn or to judge a plan. The plan "
            "is the sowing date and crop of each season; the field area is used. Report the "
            "returned warnings and say the figures are estimates from past years. Needs a "
            "selected field.",
            crop_revenue_tool,
            {
                "type": "object",
                "properties": {
                    "plan": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "startDate": {"type": "string", "description": "YYYY-MM-DD"},
                                "crop": {"type": "string"},
                            },
                            "required": ["startDate", "crop"],
                        },
                        "description": "Planned crops with the start day of growing.",
                    },
                    "investment": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "year": {"type": "integer"},
                                "amount": {"type": "number"},
                            },
                        },
                        "description": "Money spent on growing the whole field, per year "
                        "([{year, amount}]); one entry for a single total.",
                    },
                    "attribute": {
                        "type": "string",
                        "enum": ["start", "harvest"],
                        "description": "Book revenue to the sowing year (default) or harvest year.",
                    },
                    "prices": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"crop": {"type": "string"}, "value": {"type": "number"}},
                        },
                        "description": "The user's own price per crop ($/bu, $/cwt sorghum, "
                        "$/ton hay), e.g. a contract. Only when the user gives one.",
                    },
                    "yields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"crop": {"type": "string"}, "value": {"type": "number"}},
                        },
                        "description": "The user's own yield per acre (bu or tons). Only when "
                        "the user gives one.",
                    },
                },
                "required": ["plan"],
            },
        )
    )
    return registry
