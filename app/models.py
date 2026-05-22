from typing import Any

from pydantic import BaseModel, Field


class ChatOption(BaseModel):
    label: str
    value: str
    action: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, examples=["Can you get my details for 2016588874?"])
    session_id: str | None = Field(default=None, examples=["web-session-123"])


class ChatResponse(BaseModel):
    answer: str
    intent: str
    delegated: bool = False
    data: dict[str, Any] | None = None
    debug: dict[str, Any] | None = None
    transcript: str | None = None
    options: list[ChatOption] | None = None


class CustomerLookupResult(BaseModel):
    found: bool
    query: str
    customer_id: str | None = None
    loyalty_id: str | None = None
    full_name: str | None = None
    phone: str | None = None
    loyalty_points: int | None = None
    preferred_store: str | None = None
    meal_preference: str | None = None
    coupon: dict[str, Any] | None = None
    message: str | None = None
    raw_record: dict[str, Any] | None = None
