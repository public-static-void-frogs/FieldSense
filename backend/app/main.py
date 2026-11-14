from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import assistant, auth, fields, planning, resources, section_analysis
from app.core.config import Settings
from app.core.database import database_engine, session_factory
from app.core.errors import ResourceConflict, ResourceNotFound
from app.services.assistant_context import default_registry
from app.services.crop_conditions import CropWeatherRuleEngine
from app.services.field_insights import SoilAssessments
from app.services.m3_lookup import M3Advice
from app.services.rotation_advice import InvalidAdviceRequest, RotationAdvice
from app.services.season_timing import SeasonTiming
from app.services.section_analysis import SectionAnalyzer
from app.services.weather import WeatherService


def create_app(config: Settings | None = None) -> FastAPI:
    config = config or Settings()
    engine = database_engine(config.database_url) if config.database_url else None

    @asynccontextmanager
    async def lifespan(app):
        config.validate()
        try:
            yield
        finally:
            app.state.weather.close()
            app.state.soil_assessments.close()
            engine.dispose()

    app = FastAPI(
        lifespan=lifespan,
        title="Field Shift NASA API",
        version="1.0.0",
        description="Authenticated farm API with SQL-backed accounts, shared fields, per-user field selections and live Open-Meteo weather. No demo field data is seeded.",
    )
    app.state.config = config
    app.state.engine = engine
    app.state.sessions = session_factory(engine)
    app.state.weather = WeatherService(config)
    app.state.crop_model = CropWeatherRuleEngine()
    app.state.section_analyzer = SectionAnalyzer()

    app.state.assistant_contexts = default_registry()
    app.state.m3_advice = M3Advice(config.m3_out)
    app.state.rotation = RotationAdvice(
        config.rotation_data_root,
        config.rotation_soil_lookup,
        SeasonTiming(config.m3_out, app.state.m3_advice),
    )
    app.state.soil_assessments = SoilAssessments(config.nass_api_key)

    @app.middleware("http")
    async def browser_security(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and origin not in config.allowed_origins:
                return JSONResponse(status_code=403, content={"detail": "Untrusted request origin"})
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse(
                    status_code=403, content={"detail": "Cross-site requests are not allowed"}
                )
        response = await call_next(request)
        if request.url.path.startswith("/api/v1"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(ResourceNotFound)
    def not_found(request: Request, error: ResourceNotFound):
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(InvalidAdviceRequest)
    def invalid_advice(request: Request, error: InvalidAdviceRequest):
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(ResourceConflict)
    def conflict(request: Request, error: ResourceConflict):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(auth.router, prefix="/api/v1")
    for router in (
        assistant.router,
        fields.router,
        planning.router,
        resources.router,
        section_analysis.router,
    ):
        app.include_router(router, prefix="/api/v1", dependencies=[Depends(auth.current_user)])

    @app.get("/", tags=["health"])
    def root() -> dict[str, str]:
        return {"message": "Hello Frog"}

    return app


app = create_app()
