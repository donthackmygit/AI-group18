from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class ContextBuilderStrategy(str, Enum):
    SOURCE_BLOCKS = "SOURCE_BLOCKS"


class ContextSource(BaseModel):
    citation_id: str
    chunk_id: str
    document_id: str | None = None
    document_title: str | None = None
    document_number: str | None = None
    document_type: str | None = None
    article: str | None = None
    article_number: str | None = None
    article_title: str | None = None
    clause: str | None = None
    point: str | None = None
    source_url: str | None = None
    local_path: str | None = None
    status: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    similarity: float
    rerank_score: float | None = None
    retrieval_rank: int | None = None
    rerank_rank: int | None = None
    estimated_tokens: int
    truncated: bool = False


class ContextBuildResult(BaseModel):
    strategy: ContextBuilderStrategy
    applied: bool
    max_tokens: int
    estimated_tokens: int
    input_count: int
    unique_count: int
    included_count: int
    duplicate_removed_count: int
    skipped_by_token_limit_count: int
    truncated_count: int
    context_text: str
    sources: list[ContextSource] = Field(default_factory=list)
    rag_framework: str | None = None
    framework_document_count: int | None = None
    note: str | None = None
