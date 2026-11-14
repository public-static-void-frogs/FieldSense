"""Pluggable context for the assistant.

Each provider is a function ``(ChatContext) -> dict | None`` registered under a unique name.
Its result becomes one named section of the CONTEXT block sent to the LLM. ML integrations
register themselves at startup:

    app.state.assistant_contexts.register("crop_zones", crop_zones_context)

A provider returns None when it has nothing to say (e.g. no field selected). A provider that
raises is logged and skipped, so one broken model never takes the chat down.
"""

import logging
from collections.abc import Callable
from functools import cached_property

from app.services.crop_conditions import assessment_context, field_location
from app.services.weather_insight import forecast_insight_input

logger = logging.getLogger(__name__)


class ChatContext:
    """Per-request inputs shared by all providers. Expensive lookups are lazy and cached."""

    def __init__(self, state, user, store, field, locale: str):
        self.state = state
        self.user = user
        self.store = store
        self.field = field
        self.locale = locale

    @cached_property
    def series(self):
        """Forecast for the field point (or saved account location) with crop assessment."""
        location = field_location(self.user.settings, self.field) if self.field else self.user.settings
        series = self.state.weather.forecast(location)
        context = assessment_context(series, self.field) if self.field else None
        if context is not None:
            return self.state.crop_model.predict(series, context)
        return series


ContextProvider = Callable[[ChatContext], dict | None]


class ContextRegistry:
    def __init__(self):
        self._providers: dict[str, ContextProvider] = {}

    def register(self, name: str, provider: ContextProvider) -> None:
        if name in self._providers:
            raise ValueError(f"Assistant context {name!r} is already registered")
        self._providers[name] = provider

    def names(self) -> list[str]:
        return list(self._providers)

    def collect(self, ctx: ChatContext, names: list[str] | None = None) -> dict:
        """Run the selected providers (all when names is None); keep non-empty sections."""
        sections = {}
        for name, provider in self._providers.items():
            if names is not None and name not in names:
                continue
            try:
                section = provider(ctx)
            except Exception as error:
                logger.warning("Assistant context %r failed: %s", name, type(error).__name__)
                continue
            if section:
                sections[name] = section
        return sections


def field_context(ctx: ChatContext) -> dict | None:
    if not ctx.field:
        return None
    return {"name": ctx.field.get("name"), "crop": ctx.field.get("crop")}


def weather_forecast_context(ctx: ChatContext) -> dict | None:
    records = ctx.series.get("records")
    if not records:
        return None
    return forecast_insight_input(ctx.series, records[0]["date"], ctx.locale)


def default_registry() -> ContextRegistry:
    registry = ContextRegistry()
    registry.register("field", field_context)
    registry.register("weather_forecast", weather_forecast_context)
    return registry
