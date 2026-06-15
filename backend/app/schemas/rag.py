from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

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
    top_k: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Number of chunks to retrieve.",
    )
    rerank_top_k: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Number of chunks to keep after re-ranking.",
    )
    context_max_tokens: int | None = Field(
        default=None,
        ge=100,
        le=12000,
        description="Approximate token budget for the LLM context.",
    )
    filter_metadata: dict[str, Any] = Field(default_factory=dict)
    status: str | None = Field(default="effective")
    effective_date: date | None = None

    gross_income: int | None = Field(default=None, ge=0)
    income_period: Literal["monthly", "yearly"] | None = None
    mandatory_insurance: int | None = Field(default=None, ge=0)
    tax_exempt_income: int | None = Field(default=None, ge=0)
    dependents: int | None = Field(default=None, ge=0, le=100)
    charity_contributions: int | None = Field(default=None, ge=0)
    other_deductions: int | None = Field(default=None, ge=0)
    resident_status: Literal["resident", "non_resident"] | None = None
    contract_type: str | None = Field(default=None, max_length=100)
    tax_year: int | None = Field(default=None, ge=1900, le=2200)

    @field_validator("filter_metadata")
    @classmethod
    def validate_filter_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 20:
            raise ValueError("filter_metadata must contain at most 20 keys.")

        for key, item in value.items():
            if len(str(key)) > 100:
                raise ValueError("filter_metadata key is too long.")
            if isinstance(item, (dict, list)):
                raise ValueError(
                    "filter_metadata only accepts scalar values in this API."
                )
            if item is not None and len(str(item)) > 500:
                raise ValueError("filter_metadata value is too long.")
        return value


class ChatRequest(SearchRequest):
    conversation_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )


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
    semantic_rank: int | None = None
    keyword_rank: int | None = None
    keyword_score: float | None = None
    hybrid_score: float | None = None
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
    warnings: list[str] = Field(default_factory=list)
    calculation: FormattedCalculation | None = None
    debug: dict[str, Any] | None = None

    # Internal diagnostics. They stay available inside Python, but are excluded
    # from normal API serialization unless a separate debug response is built.
    processed_question: ProcessedQuestion | None = Field(default=None, exclude=True)
    classification: QueryClassificationResult | None = Field(default=None, exclude=True)
    routing: QueryRoutingResult | None = Field(default=None, exclude=True)
    query_embedding: QueryEmbeddingResult | None = Field(default=None, exclude=True)
    retrieval: RetrievalResult | None = Field(default=None, exclude=True)
    reranking: RerankingResult | None = Field(default=None, exclude=True)
    tax_calculation: TaxCalculationResult | None = Field(default=None, exclude=True)
    context: ContextBuildResult | None = Field(default=None, exclude=True)
    prompt: PromptBuildResult | None = Field(default=None, exclude=True)
    llm: LLMGenerationResult | None = Field(default=None, exclude=True)
    response_validation: ResponseValidationResult | None = Field(default=None, exclude=True)
    response_formatter: ResponseFormatResult | None = Field(default=None, exclude=True)
