from __future__ import annotations

from pydantic import BaseModel, Field


class FormattedCitation(BaseModel):
    citation_id: str
    chunk_id: str
    document_id: str | None = None
    document_name: str | None = None
    document_number: str | None = None
    document_type: str | None = None
    issuing_authority: str | None = None
    article: str | None = None
    clause: str | None = None
    content: str
    source_url: str | None = None
    status: str | None = None


class FormattedCalculation(BaseModel):
    taxable_income: int | None = None
    personal_deduction: int | None = None
    dependent_deduction: int | None = None
    tax_amount: int | None = None
    calculation_steps: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResponseFormatResult(BaseModel):
    applied: bool
    format_version: str
    citation_count: int
    calculation_included: bool
    confidence: float | None = None
    warning_count: int = 0
    note: str | None = None