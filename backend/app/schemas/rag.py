from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from backend.app.schemas.context import ContextBuildResult
from backend.app.schemas.llm import LLMGenerationResult
from backend.app.schemas.prompt import PromptBuildResult
from backend.app.schemas.query_embedding import QueryEmbeddingResult
from backend.app.schemas.question_processing import ProcessedQuestion
from backend.app.schemas.query_route import QueryClassificationResult, QueryRoutingResult
from backend.app.schemas.retrieval import RetrievalResult
from backend.app.schemas.reranking import RerankingResult
from backend.app.schemas.response_formatter import (
    FormattedCalculation,
    FormattedCitation,
    ResponseFormatResult,
)
from backend.app.schemas.response_validation import ResponseValidationResult
from backend.app.schemas.tax_calculation import TaxCalculationResult


class HealthResponse(BaseModel):
    status: str
    app_name: str
    app_version: str
    embedding_model: str
    database_configured: bool
    supabase_auth_configured: bool


class SearchRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="User question in Vietnamese.",
    )
    top_k: int | None = Field(default=None, ge=1, description="Number of chunks to retrieve.")
    rerank_top_k: int | None = Field(
        default=None,
        ge=1,
        description="Number of chunks to keep after re-ranking.",
    )
    context_max_tokens: int | None = Field(
        default=None,
        ge=100,
        description="Approximate token budget for the LLM context built from re-ranked chunks.",
    )
    filter_metadata: dict[str, Any] = Field(default_factory=dict)
    status: str | None = Field(default="effective", description="Document status filter.")
    effective_date: date | None = Field(default=None, description="Legal effective date filter.")
    gross_income: int | None = Field(default=None, ge=0, description="Override gross income for tax calculation.")
    income_period: str | None = Field(default=None, description="monthly or yearly.")
    mandatory_insurance: int | None = Field(default=None, ge=0)
    tax_exempt_income: int | None = Field(default=None, ge=0)
    dependents: int | None = Field(default=None, ge=0)
    charity_contributions: int | None = Field(default=None, ge=0)
    other_deductions: int | None = Field(default=None, ge=0)
    resident_status: str | None = Field(default=None, description="resident or non_resident.")
    contract_type: str | None = Field(default=None)
    tax_year: int | None = Field(default=None, ge=1900)


class ChatRequest(SearchRequest):
    conversation_id: str | None = Field(default=None)


class Citation(BaseModel):
    citation_id: str
    chunk_id: str
    document_id: str | None = None
    document_title: str | None = None
    document_number: str | None = None
    document_type: str | None = None
    issuing_authority: str | None = None
    article: str | None = None
    article_number: str | None = None
    article_title: str | None = None
    chapter: str | None = None
    section: str | None = None
    source_url: str | None = None
    local_path: str | None = None
    status: str | None = None
    issue_date: date | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    similarity: float
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    retrieval_rank: int | None = None
    rerank_rank: int | None = None
    rerank_score: float | None = None


class SearchResponse(BaseModel):
    question: str
    top_k: int
    citations: list[Citation]
    processed_question: ProcessedQuestion | None = None
    classification: QueryClassificationResult | None = None
    routing: QueryRoutingResult | None = None
    query_embedding: QueryEmbeddingResult | None = None
    retrieval: RetrievalResult | None = None
    reranking: RerankingResult | None = None
    calculation: TaxCalculationResult | None = None
    context: ContextBuildResult | None = None
    prompt: PromptBuildResult | None = None


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str | None = None
    assistant_message_id: str | None = None
    mode: str
    citations: list[FormattedCitation]
    confidence: float | None = None
    warning: str | None = None
    calculation: FormattedCalculation | None = None
    processed_question: ProcessedQuestion | None = None
    classification: QueryClassificationResult | None = None
    routing: QueryRoutingResult | None = None
    query_embedding: QueryEmbeddingResult | None = None
    retrieval: RetrievalResult | None = None
    reranking: RerankingResult | None = None
    tax_calculation: TaxCalculationResult | None = None
    context: ContextBuildResult | None = None
    prompt: PromptBuildResult | None = None
    llm: LLMGenerationResult | None = None
    response_validation: ResponseValidationResult | None = None
    response_formatter: ResponseFormatResult | None = None
