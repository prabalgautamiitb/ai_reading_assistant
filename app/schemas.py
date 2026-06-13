from typing import Literal

from pydantic import BaseModel, Field

ExplainMode = Literal["simple", "summary", "technical", "example"]


class ExplainRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=12000)
    mode: ExplainMode = "simple"
    provider: str | None = None


class ExplainResponse(BaseModel):
    answer: str
    mode: ExplainMode
    provider: str
    model: str


class HealthResponse(BaseModel):
    status: str
