import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def cors_origins() -> list[str]:
    return [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip()
    ]


@dataclass
class Settings:
    weather_forecast_url: str = field(
        default_factory=lambda: os.getenv(
            "WEATHER_FORECAST_URL", "https://api.open-meteo.com/v1/forecast"
        )
    )
    weather_archive_url: str = field(
        default_factory=lambda: os.getenv(
            "WEATHER_ARCHIVE_URL", "https://archive-api.open-meteo.com/v1/archive"
        )
    )
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""), repr=False)
    gemini_enabled: bool = field(
        default_factory=lambda: os.getenv("GEMINI_ENABLED", "false").lower() == "true"
    )
    gemini_model: str = field(
        default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    )
    weather_timeout_seconds: float = 5
    weather_forecast_ttl_seconds: int = 600
    weather_history_ttl_seconds: int = 21600
    weather_cache_size: int = 256
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", ""))
    jwt_issuer: str = field(default_factory=lambda: os.getenv("JWT_ISSUER", ""))
    cookie_secure: bool = field(
        default_factory=lambda: os.getenv("COOKIE_SECURE", "false").lower() == "true"
    )
    cookie_name: str = "fieldshift_access"
    allowed_origins: list[str] = field(default_factory=cors_origins)

    def validate(self):
        if not self.database_url:
            raise ValueError("DATABASE_URL must be configured in backend/.env.")
        if not self.jwt_issuer.strip():
            raise ValueError("JWT_ISSUER must be configured in backend/.env.")
        if len(self.jwt_secret.encode()) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 bytes. Set it in backend/.env.")
