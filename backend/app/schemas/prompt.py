from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class PromptBuilderStrategy(str, Enum):
    STRUCTURED_MESSAGES = "STRUCTURED_MESSAGES"


class PromptMessage(BaseModel):
    role: Literal["system", "user"]
    content: str


class PromptBuildResult(BaseModel):
    strategy: PromptBuilderStrategy
    applied: bool
    input_question: str
    context_source_count: int
    source_ids: list[str] = Field(default_factory=list)
    requires_tax_calculation: bool
    estimated_tokens: int
    system_instruction: str
    answer_rules: list[str] = Field(default_factory=list)
    output_format: dict[str, Any] = Field(default_factory=dict)
    messages: list[PromptMessage] = Field(default_factory=list)
    prompt_text: str
    note: str | None = None
