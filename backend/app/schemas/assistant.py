from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

MAX_MESSAGES = 20
MAX_MESSAGE_CHARS = 4000


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)

    @field_validator("content")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(
        min_length=1,
        max_length=MAX_MESSAGES,
        description="Full conversation so far, oldest first. The server keeps no chat state. Must start and end with a user message.",
    )
    field_id: UUID | None = Field(
        default=None,
        description="Ground the answer in this field and its forecast. Omit for general questions.",
    )
    contexts: list[str] | None = Field(
        default=None,
        max_length=20,
        description="Names of context providers to include (e.g. field, weather_forecast, or registered ML models). Omit to include all.",
    )
    locale: str = Field(
        default="en", max_length=64, pattern=r"^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$"
    )

    @field_validator("messages")
    @classmethod
    def starts_and_ends_with_user(cls, value: list[ChatMessage]) -> list[ChatMessage]:
        if value[0].role != "user" or value[-1].role != "user":
            raise ValueError("conversation must start and end with a user message")
        return value
