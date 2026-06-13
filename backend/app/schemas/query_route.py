from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class QueryIntent(str, Enum):
    LEGAL_LOOKUP = "LEGAL_LOOKUP"
    TAX_CALCULATION = "TAX_CALCULATION"
    DEFINITION = "DEFINITION"
    PROCEDURE_GUIDE = "PROCEDURE_GUIDE"
    GENERAL_TNCN_QUERY = "GENERAL_TNCN_QUERY"
    FOLLOW_UP = "FOLLOW_UP"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    UNCLEAR = "UNCLEAR"


class QueryRoute(str, Enum):
    RAG_ONLY = "RAG_ONLY"
    RAG_WITH_TAX_CALCULATION = "RAG_WITH_TAX_CALCULATION"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    REJECT = "REJECT"


class QueryClassificationResult(BaseModel):
    intent: QueryIntent
    confidence: float
    topic: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    reason: str | None = None


class QueryRoutingResult(BaseModel):
    route: QueryRoute
    intent: QueryIntent
    retrieval_required: bool
    tax_calculation_required: bool
    llm_required: bool
    missing_fields: list[str] = Field(default_factory=list)
    clarification_message: str | None = None
    reject_message: str | None = None
