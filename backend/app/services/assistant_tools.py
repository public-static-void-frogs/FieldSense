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
from functools import cached_property

from fastapi import HTTPException

from app.services.crop_conditions import assessment_context, field_location
from app.services.weather_insight import forecast_insight_input

logger = logging.getLogger(__name__)

MAX_RESULT_CHARS = 20_000
NO_FIELD = {
    "status": "unavailable",
    "reason": "No field is selected. Ask the user to select a field.",
}


class ChatContext:
    """Per-request inputs shared by all tools. Plain data only; see the module docstring."""

    def __init__(self, state, location, field, locale: str):
        self.state = state
        self.location = location  # snapshot of the account's saved location and units
        self.field = field  # selected field dict, or None
        self.locale = locale

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
    return forecast_insight_input(ctx.series, records[0]["date"], ctx.locale)


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


def default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            "get_weather_forecast",
            "Daily weather forecast for the next 3 days at the selected field, or at the user's "
            "saved location when no field is selected: conditions, temperature, overnight low, "
            "rainfall, rain chance, soil moisture, humidity, wind, plus crop-risk level and "
            "rule alerts (e.g. frost, heat, waterlogging) for the field's crop. Use for "
            "questions about upcoming weather, frost or rain, or short-term crop risk.",
            weather_forecast_tool,
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
    return registry
