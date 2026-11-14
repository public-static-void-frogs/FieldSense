from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.api.auth import CurrentUser
from app.api.dependencies import Store
from app.schemas.maps import MapSummary, MapView
from app.schemas.resources import (
    DemoSource,
    FarmProfile,
    Notification,
    Overview,
    TeamMember,
)
from app.schemas.weather import CurrentWeather, WeatherSeries
from app.services import maps
from app.services import resources as service
from app.services.crop_conditions import assessment_context, field_location
from app.services.overview import charts
from app.services.weather_insight import forecast_insight_input, stream_weather_insight

router = APIRouter()


@router.get("/farm/profile", response_model=FarmProfile, tags=["farm"])
def farm(store: Store, user: CurrentUser):
    return service.farm_profile(store, user)


@router.get("/weather/current", response_model=CurrentWeather, tags=["weather"])
def current_weather(request: Request, user: CurrentUser):
    return request.app.state.weather.current(user.settings)


@router.get(
    "/weather/history",
    response_model=WeatherSeries,
    tags=["weather"],
    description=(
        "Completed daily model estimates, newest first. Uses saved coordinates, time zone and units. "
        "Provide both dates for a custom period of up to 366 days; otherwise days selects a trailing range. "
        "Missing readings remain null. Soil moisture is modeled volumetric water content at 0–7 cm. "
        "An optional field_id selects field coordinates and returns growing-season limits and daily rule "
        "assessments for a supported crop. Field soil inputs refine the limits when available. "
        "Climate context summarizes the requested history window."
    ),
    responses={
        422: {"description": "Missing location or invalid date range"},
        503: {"description": "Provider unavailable or malformed response; no demo fallback"},
    },
)
def weather_history(
    request: Request,
    user: CurrentUser,
    store: Store,
    field_id: UUID | None = Query(
        default=None,
        description="Assess this field's crop using weather at its field point and the caller's saved time zone. Omit for unassessed weather at the saved account location.",
    ),
    days: Literal["7", "30", "90"] = "30",
    start_date: date | None = None,
    end_date: date | None = None,
):
    field = store.require_field(field_id) if field_id else None
    location = user.settings
    if field:
        location = field_location(user.settings, field)
    series = request.app.state.weather.history(location, int(days), start_date, end_date)
    context = assessment_context(series, field) if field else None
    if context is not None:
        return request.app.state.crop_model.predict(series, context)
    return series


@router.get(
    "/weather/forecast",
    response_model=WeatherSeries,
    tags=["weather"],
    description=(
        "14 daily forecasts, oldest first, starting today in the saved time zone. Shares a 10-minute "
        "upstream cache with current weather. Metrics are nullable, wind is the daily maximum and soil "
        "moisture is the daily mean at 0–1 cm. An optional field_id selects field coordinates and adds "
        "growing-season limits, suitability scores and rule alerts for a supported crop. Field soil inputs "
        "refine the limits when available. Climate context summarizes the forecast window. "
        "Omitting field_id returns account-location weather with null cropAssessment."
    ),
    responses={
        422: {"description": "Missing saved coordinates"},
        503: {"description": "Provider unavailable; no demo fallback"},
    },
)
def weather_forecast(
    request: Request,
    user: CurrentUser,
    store: Store,
    field_id: UUID | None = Query(
        default=None,
        description="Assess this field's crop using weather at its field point and the caller's saved time zone. Omit for unassessed weather at the saved account location.",
    ),
):
    field = store.require_field(field_id) if field_id else None
    location = user.settings
    if field:
        location = field_location(user.settings, field)
    series = request.app.state.weather.forecast(location)
    context = assessment_context(series, field) if field else None
    if context is not None:
        return request.app.state.crop_model.predict(series, context)
    return series


@router.post(
    "/weather/forecast/insight",
    tags=["weather"],
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "NDJSON text deltas followed by a done event on success.",
            "content": {"application/x-ndjson": {"schema": {"type": "string"}}},
        },
        404: {"description": "Field or forecast date unavailable"},
        503: {"description": "Weather summaries are unavailable"},
    },
)
def weather_forecast_insight(
    request: Request,
    user: CurrentUser,
    store: Store,
    day: date,
    locale: str = Query(
        default="en", max_length=64, pattern=r"^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$"
    ),
    field_id: UUID | None = None,
):
    config = request.app.state.config
    if not config.gemini_enabled or not config.gemini_api_key.strip():
        raise HTTPException(503, "Weather summaries are unavailable")
    series = weather_forecast(request, user, store, field_id)
    forecast = forecast_insight_input(series, day.isoformat(), locale)
    if forecast is None:
        raise HTTPException(404, "This date is outside the available forecast")
    return StreamingResponse(
        stream_weather_insight(config, forecast),
        media_type="application/x-ndjson",
    )


@router.get("/maps/summary", response_model=MapSummary, tags=["maps"])
def map_summary(store: Store):
    """Catalog extent and default view without downloading the catalog."""
    return maps.summary(store.session)


@router.get(
    "/maps/geojson", response_model=MapView, response_model_exclude_none=True, tags=["maps"]
)
def geojson(
    store: Store,
    bbox: str = Query(
        description="west,south,east,north in WGS84; antimeridian views must be split"
    ),
    zoom: float = Query(ge=0, le=20),
):
    """Return at most 600 visible features. Wide/dense views use preaggregated count groups; close views use indexed point containment. Field features represent source interior points."""
    import math

    try:
        bounds = tuple(float(value) for value in bbox.split(","))
        west, south, east, north = bounds
        if not all(math.isfinite(value) for value in bounds):
            raise ValueError()
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError()
    except ValueError as error:
        raise HTTPException(
            status_code=422, detail="bbox must be west,south,east,north in WGS84"
        ) from error
    return maps.viewport(store, bounds, zoom)


@router.get("/help/team", response_model=list[TeamMember], tags=["help"])
def team(store: Store):
    return []


@router.get("/help/sources", response_model=list[DemoSource], tags=["help"])
def sources(store: Store):
    return []


@router.get(
    "/notifications",
    response_model=list[Notification],
    response_model_exclude_unset=True,
    tags=["notifications"],
)
def list_notifications(store: Store):
    return service.notifications(store)


@router.get("/overview/charts", response_model=Overview, tags=["overview"])
def overview(
    store: Store,
    days: int = Query(default=30, ge=1, le=365),
    metric: Literal["health", "moisture"] = "health",
):
    return charts(store, days, metric)
