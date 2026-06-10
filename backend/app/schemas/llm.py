from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class LLMProvider(str, Enum):
    GEMINI = "gemini"


class LLMGenerationResult(BaseModel):
    provider: LLMProvider
    model: str
    applied: bool
    temperature: float
    max_output_tokens: int
    prompt_estimated_tokens: int | None = None
    raw_text: str
    parsed_output: dict[str, Any] | None = None
    answer: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    confidence_label: str | None = None
    warning: str | None = None
    note: str | None = None
