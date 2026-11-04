from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
    )


class ChatSource(BaseModel):
    kind: Literal["database", "document"]
    name: str
    page: int | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]
