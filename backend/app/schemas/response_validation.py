from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ResponseValidationStatus(str, Enum):
    PASSED = "PASSED"
    WARNING = "WARNING"
    FAILED = "FAILED"


class ResponseValidationSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class ResponseValidationIssue(BaseModel):
    code: str
    severity: ResponseValidationSeverity
    message: str
    citation_id: str | None = None
    field: str | None = None


class ResponseValidationResult(BaseModel):
    applied: bool
    status: ResponseValidationStatus
    is_valid: bool
    issues: list[ResponseValidationIssue] = Field(default_factory=list)
    cited_source_ids: list[str] = Field(default_factory=list)
    invalid_source_ids: list[str] = Field(default_factory=list)
    checked_source_ids: list[str] = Field(default_factory=list)
    calculation_valid: bool | None = None
    safe_answer: str | None = None
    warning: str | None = None
    note: str | None = None

