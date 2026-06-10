from __future__ import annotations

from pydantic import BaseModel, Field


class QueryEmbeddingResult(BaseModel):
    model_name: str
    input_text: str
    input_source: str
    dimension: int
    normalized: bool
    vector_norm: float | None = None
    vector_preview: list[float] = Field(default_factory=list)
