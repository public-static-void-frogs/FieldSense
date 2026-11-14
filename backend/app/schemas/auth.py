from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, from_attributes=True, extra="forbid"
    )


class AccountInput(ApiModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr = Field(max_length=254)

    @field_validator("full_name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return str(value).lower()


class LocationInput(ApiModel):
    location: str = Field(default="", max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90, strict=True)
    longitude: float | None = Field(default=None, ge=-180, le=180, strict=True)

    @model_validator(mode="after")
    def paired_coordinates(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be provided together")
        return self


class RegisterInput(AccountInput, LocationInput):
    password: str = Field(min_length=8, max_length=128)
    farm_name: str = Field(default="", max_length=120)
    location: str = Field(default="", max_length=200)
    language: Literal["en", "uk"] = "en"

    @field_validator("farm_name", "location", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class LoginInput(ApiModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return str(value).lower()


class PublicUser(ApiModel):
    id: str
    full_name: str
    email: str


class SettingsInput(LocationInput):
    farm_name: str = Field(default="", max_length=120)
    location: str = Field(max_length=200)
    season: Literal["2026", "2025"]
    time_zone: str = Field(min_length=1, max_length=100)
    units: Literal["metric", "imperial"]
    theme: Literal["light", "dark", "system"]
    language: Literal["en", "uk"]
    session_lifetime_hours: int = Field(default=24, ge=1, le=720, strict=True)

    @field_validator("farm_name", "location", "time_zone", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("time_zone")
    @classmethod
    def valid_time_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError("Unknown time zone") from error
        return value
