from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RetrievalStrategy(str, Enum):
    SEMANTIC_SEARCH = "SEMANTIC_SEARCH"
    HYBRID_SEARCH = "HYBRID_SEARCH"


class RetrievalFilters(BaseModel):
    status: str | None = None
    effective_date: date | None = None
    filter_metadata: dict[str, Any] = Field(default_factory=dict)
    topic_hint: str | None = None


class RetrievalResult(BaseModel):
    strategy: RetrievalStrategy
    source: str
    table: str
    requested_top_k: int
    returned_count: int
    filters: RetrievalFilters
    semantic_count: int | None = None
    keyword_count: int | None = None
    similarity_min: float | None = None
    similarity_max: float | None = None
    similarity_avg: float | None = None
    note: str | None = None
