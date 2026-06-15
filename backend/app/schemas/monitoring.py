from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class QueryLogListItem(BaseModel):
    id: str
    created_at: datetime
    status: str
    mode: str | None = None
    conversation_id: str | None = None
    user_id: str | None = None

    original_question: str | None = None
    standalone_question: str | None = None
    intent: str | None = None
    route: str | None = None

    confidence: float | None = None
    response_time_ms: int | None = None
    retrieved_count: int | None = None
    reranked_count: int | None = None

    llm_model: str | None = None
    llm_prompt_tokens: int | None = None
    llm_completion_tokens: int | None = None
    llm_total_tokens: int | None = None
    llm_estimated_cost_usd: float | None = None
    error_message: str | None = None
    warnings: list[str] = Field(default_factory=list)


class QueryLogListResponse(BaseModel):
    items: list[QueryLogListItem]
    limit: int
    offset: int


class TopDocumentItem(BaseModel):
    document: str
    hit_count: int
    avg_similarity: float | None = None
    last_used_at: datetime | None = None


class LowConfidenceItem(BaseModel):
    id: str
    created_at: datetime
    original_question: str | None = None
    confidence: float | None = None
    mode: str | None = None
    warnings: list[str] = Field(default_factory=list)


class FeedbackSummary(BaseModel):
    total_feedback: int = 0
    positive_count: int = 0
    negative_count: int = 0


class MonitoringDashboardResponse(BaseModel):
    days: int

    total_queries: int = 0
    success_count: int = 0
    blocked_count: int = 0
    error_count: int = 0
    llm_fallback_count: int = 0

    avg_response_time_ms: float | None = None
    p95_response_time_ms: float | None = None
    avg_confidence: float | None = None

    total_prompt_estimated_tokens: int = 0
    total_llm_max_output_tokens: int = 0
    total_llm_prompt_tokens: int = 0
    total_llm_completion_tokens: int = 0
    total_llm_tokens: int = 0
    total_llm_estimated_cost_usd: float = 0.0

    feedback: FeedbackSummary = Field(default_factory=FeedbackSummary)
    top_documents: list[TopDocumentItem] = Field(default_factory=list)
    low_confidence_items: list[LowConfidenceItem] = Field(default_factory=list)


class IngestionLogItem(BaseModel):
    id: int
    created_at: datetime
    run_id: str | None = None

    document_id: str | None = None
    step: str
    status: str

    input_path: str | None = None
    output_path: str | None = None

    char_count: int | None = None
    chunk_count: int | None = None
    page_count: int | None = None

    warning: str | None = None
    error_message: str | None = None
    raw_log: dict[str, Any] = Field(default_factory=dict)


class IngestionLogListResponse(BaseModel):
    items: list[IngestionLogItem]
    limit: int
    offset: int
