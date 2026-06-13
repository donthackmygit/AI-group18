from __future__ import annotations

from pydantic import BaseModel


class ExtractedEntities(BaseModel):
    income: int | None = None
    income_period: str | None = None
    dependents: int | None = None
    insurance: int | None = None
    resident_status: str | None = None
    nationality: str | None = None
    work_start_month: int | None = None
    days_in_vietnam: int | None = None
    tax_year: int | None = None


class ProcessedQuestion(BaseModel):
    original_question: str
    normalized_question: str
    standalone_question: str
    intent: str
    topic: str | None = None
    entities: ExtractedEntities
    retrieval_query: str
