from __future__ import annotations

import re
from datetime import date
from typing import Any

from backend.app.schemas.context import ContextBuildResult, ContextSource
from backend.app.schemas.llm import LLMGenerationResult
from backend.app.schemas.query_route import QueryRoutingResult
from backend.app.schemas.response_validation import (
    ResponseValidationIssue,
    ResponseValidationResult,
    ResponseValidationSeverity,
    ResponseValidationStatus,
)
from backend.app.schemas.tax_calculation import TaxCalculationResult


SOURCE_REF_RE = re.compile(r"\[(SOURCE_\d+)\]")
DOCUMENT_NUMBER_RE = re.compile(r"\b\d{1,4}/\d{4}/[A-Z0-9Đ/-]+\b", flags=re.IGNORECASE)
LOW_CONFIDENCE_ANSWER = (
    "Hệ thống chưa tìm thấy đủ căn cứ pháp lý để đưa ra kết luận chắc chắn. "
    "Bạn nên kiểm tra lại tại cơ quan thuế hoặc cung cấp thêm thông tin."
)


class ResponseValidationService:
    @staticmethod
    def _has_valid_calculation(calculation: TaxCalculationResult | None) -> bool:
        return bool(calculation and calculation.applied and calculation.tax_amount is not None)

    def validate(
        self,
        llm_result: LLMGenerationResult,
        context: ContextBuildResult | None,
        calculation: TaxCalculationResult | None,
        routing: QueryRoutingResult,
        effective_date: date | None = None,
    ) -> ResponseValidationResult:
        issues: list[ResponseValidationIssue] = []
        source_map = _source_map(context)
        allowed_source_ids = set(source_map)
        answer = (llm_result.answer or llm_result.raw_text or "").strip()
        validation_date = effective_date or date.today()

        if not answer:
            issues.append(
                _issue(
                    code="EMPTY_ANSWER",
                    severity=ResponseValidationSeverity.ERROR,
                    message="LLM did not produce an answer.",
                    field="answer",
                )
            )

        if llm_result.parsed_output is None:
            issues.append(
                _issue(
                    code="UNPARSED_LLM_JSON",
                    severity=ResponseValidationSeverity.WARNING,
                    message="LLM response is not a valid JSON object in the expected format.",
                    field="parsed_output",
                )
            )

        cited_source_ids = _extract_cited_source_ids(answer, llm_result.citations)
        invalid_source_ids = sorted(source_id for source_id in cited_source_ids if source_id not in allowed_source_ids)

        if routing.retrieval_required and allowed_source_ids and not cited_source_ids:
            issues.append(
                _issue(
                    code="MISSING_CITATION",
                    severity=ResponseValidationSeverity.ERROR,
                    message="Answer does not cite any retrieved source.",
                    field="citations",
                )
            )

        if routing.retrieval_required and not allowed_source_ids:
            issues.append(
                _issue(
                    code="NO_CONTEXT_SOURCES",
                    severity=ResponseValidationSeverity.WARNING,
                    message="No context sources were available for response validation.",
                    field="context.sources",
                )
            )

        for source_id in invalid_source_ids:
            issues.append(
                _issue(
                    code="INVALID_CITATION_SOURCE",
                    severity=ResponseValidationSeverity.ERROR,
                    message=f"Cited source {source_id} does not exist in the built context.",
                    citation_id=source_id,
                    field="citations",
                )
            )

        issues.extend(_validate_citation_metadata(llm_result.citations, source_map))
        issues.extend(_validate_document_references(answer, source_map))
        issues.extend(
            _validate_effective_sources(
                cited_source_ids,
                source_map,
                validation_date,
            )
        )
        calculation_issues = _validate_calculation_output(llm_result, calculation, routing)
        issues.extend(calculation_issues)

        has_errors = any(issue.severity == ResponseValidationSeverity.ERROR for issue in issues)
        has_warnings = any(issue.severity == ResponseValidationSeverity.WARNING for issue in issues)
        status = (
            ResponseValidationStatus.FAILED
            if has_errors
            else ResponseValidationStatus.WARNING
            if has_warnings
            else ResponseValidationStatus.PASSED
        )

        warning = _warning_text(issues)
        return ResponseValidationResult(
            applied=True,
            status=status,
            is_valid=not has_errors,
            issues=issues,
            cited_source_ids=cited_source_ids,
            invalid_source_ids=invalid_source_ids,
            checked_source_ids=sorted(allowed_source_ids),
            calculation_valid=not any(issue.field == "calculation" for issue in calculation_issues),
            safe_answer=LOW_CONFIDENCE_ANSWER if has_errors and not _has_valid_calculation(calculation) else None,
            warning=warning,
            note=(
                "Response Validation checks citations, source metadata, effective status, "
                "context-bound references, and tax calculation shape before returning the answer."
            ),
        )


def _source_map(context: ContextBuildResult | None) -> dict[str, ContextSource]:
    if not context:
        return {}
    return {source.citation_id: source for source in context.sources}


def _extract_cited_source_ids(answer: str, llm_citations: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    source_ids: list[str] = []
    for source_id in SOURCE_REF_RE.findall(answer):
        if source_id not in seen:
            source_ids.append(source_id)
            seen.add(source_id)
    for citation in llm_citations:
        source_id = citation.get("citation_id")
        if isinstance(source_id, str) and source_id.startswith("SOURCE_") and source_id not in seen:
            source_ids.append(source_id)
            seen.add(source_id)
    return source_ids


def _validate_citation_metadata(
    llm_citations: list[dict[str, Any]],
    source_map: dict[str, ContextSource],
) -> list[ResponseValidationIssue]:
    issues: list[ResponseValidationIssue] = []
    for citation in llm_citations:
        source_id = citation.get("citation_id")
        if not isinstance(source_id, str) or source_id not in source_map:
            continue
        source = source_map[source_id]
        issues.extend(
            _compare_citation_field(
                citation=citation,
                source=source,
                source_id=source_id,
                field="document_number",
            )
        )
        issues.extend(
            _compare_citation_field(
                citation=citation,
                source=source,
                source_id=source_id,
                field="article",
            )
        )
        issues.extend(
            _compare_citation_field(
                citation=citation,
                source=source,
                source_id=source_id,
                field="clause",
            )
        )
    return issues


def _compare_citation_field(
    citation: dict[str, Any],
    source: ContextSource,
    source_id: str,
    field: str,
) -> list[ResponseValidationIssue]:
    cited_value = citation.get(field)
    source_value = getattr(source, field, None)
    if not isinstance(cited_value, str) or not cited_value.strip() or not source_value:
        return []
    if _metadata_matches(cited_value, source_value, field):
        return []
    return [
        _issue(
            code="CITATION_METADATA_MISMATCH",
            severity=ResponseValidationSeverity.WARNING,
            message=f"Citation field {field} does not match metadata for {source_id}.",
            citation_id=source_id,
            field=field,
        )
    ]


def _metadata_matches(cited_value: str, source_value: str, field: str) -> bool:
    cited = _normalize_text(cited_value)
    source = _normalize_text(source_value)
    if cited == source or cited in source or source in cited:
        return True
    if field in {"article", "clause"}:
        cited_number = _first_number(cited)
        source_number = _first_number(source)
        return bool(cited_number and source_number and cited_number == source_number)
    return False


def _validate_document_references(
    answer: str,
    source_map: dict[str, ContextSource],
) -> list[ResponseValidationIssue]:
    allowed_numbers = {
        source.document_number.casefold()
        for source in source_map.values()
        if source.document_number
    }
    if not allowed_numbers:
        return []
    issues: list[ResponseValidationIssue] = []
    for document_number in sorted(set(DOCUMENT_NUMBER_RE.findall(answer))):
        if document_number.casefold() not in allowed_numbers:
            issues.append(
                _issue(
                    code="UNSUPPORTED_DOCUMENT_REFERENCE",
                    severity=ResponseValidationSeverity.WARNING,
                    message=f"Answer mentions document {document_number}, which is not in the retrieved context.",
                    field="answer",
                )
            )
    return issues


def _validate_effective_sources(
    cited_source_ids: list[str],
    source_map: dict[str, ContextSource],
    validation_date: date,
) -> list[ResponseValidationIssue]:
    issues: list[ResponseValidationIssue] = []

    for source_id in cited_source_ids:
        source = source_map.get(source_id)
        if source is None:
            continue

        if source.effective_date and source.effective_date > validation_date:
            issues.append(
                _issue(
                    code="SOURCE_NOT_YET_EFFECTIVE",
                    severity=ResponseValidationSeverity.ERROR,
                    message=(
                        f"Cited source {source_id} becomes effective on "
                        f"{source.effective_date.isoformat()}, after the requested date "
                        f"{validation_date.isoformat()}."
                    ),
                    citation_id=source_id,
                    field="effective_date",
                )
            )

        if source.expiry_date and source.expiry_date < validation_date:
            issues.append(
                _issue(
                    code="SOURCE_EXPIRED_AT_REQUESTED_DATE",
                    severity=ResponseValidationSeverity.ERROR,
                    message=(
                        f"Cited source {source_id} expired on "
                        f"{source.expiry_date.isoformat()}, before the requested date "
                        f"{validation_date.isoformat()}."
                    ),
                    citation_id=source_id,
                    field="expiry_date",
                )
            )

        status = (source.status or "").strip().casefold()
        accepted_statuses = {
            "effective",
            "partially_effective",
            "còn hiệu lực",
            "con hieu luc",
            "một phần hiệu lực",
            "mot phan hieu luc",
        }
        if status and status not in accepted_statuses:
            issues.append(
                _issue(
                    code="SOURCE_STATUS_REQUIRES_REVIEW",
                    severity=ResponseValidationSeverity.WARNING,
                    message=f"Cited source {source_id} has status '{source.status}'.",
                    citation_id=source_id,
                    field="status",
                )
            )

    return issues

def _validate_calculation_output(
    llm_result: LLMGenerationResult,
    calculation: TaxCalculationResult | None,
    routing: QueryRoutingResult,
) -> list[ResponseValidationIssue]:
    if not routing.tax_calculation_required:
        return []

    issues: list[ResponseValidationIssue] = []
    if calculation is None:
        return [
            _issue(
                code="MISSING_TAX_CALCULATION",
                severity=ResponseValidationSeverity.ERROR,
                message="Route requires Tax Calculation Service, but no calculation result is attached.",
                field="calculation",
            )
        ]

    if not calculation.applied:
        issues.append(
            _issue(
                code="TAX_CALCULATION_NOT_APPLIED",
                severity=ResponseValidationSeverity.WARNING,
                message="Tax Calculation Service did not apply because required inputs are missing.",
                field="calculation",
            )
        )
        return issues

    parsed_calculation = None
    if llm_result.parsed_output and isinstance(llm_result.parsed_output.get("calculation"), dict):
        parsed_calculation = llm_result.parsed_output["calculation"]

    if parsed_calculation is None:
        issues.append(
            _issue(
                code="MISSING_LLM_CALCULATION_BLOCK",
                severity=ResponseValidationSeverity.WARNING,
                message="LLM output does not include calculation object in the expected format.",
                field="calculation",
            )
        )
        return issues

    expected_values = {
        "taxable_income": calculation.taxable_income,
        "personal_deduction": calculation.personal_deduction,
        "dependent_deduction": calculation.dependent_deduction,
        "tax_amount": calculation.tax_amount,
    }
    for field, expected_value in expected_values.items():
        if expected_value is None:
            continue
        actual_value = parsed_calculation.get(field)
        if actual_value is None:
            continue
        if _to_int(actual_value) != expected_value:
            issues.append(
                _issue(
                    code="TAX_CALCULATION_MISMATCH",
                    severity=ResponseValidationSeverity.ERROR,
                    message=f"LLM calculation field {field} does not match Tax Calculation Service.",
                    field="calculation",
                )
            )
    return issues


def _issue(
    code: str,
    severity: ResponseValidationSeverity,
    message: str,
    citation_id: str | None = None,
    field: str | None = None,
) -> ResponseValidationIssue:
    return ResponseValidationIssue(
        code=code,
        severity=severity,
        message=message,
        citation_id=citation_id,
        field=field,
    )


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _first_number(value: str) -> str | None:
    match = re.search(r"\d+", value)
    return match.group(0) if match else None


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    if isinstance(value, str):
        digits = re.sub(r"[^\d-]", "", value)
        if not digits or digits == "-":
            return None
        return int(digits)
    return None


def _warning_text(issues: list[ResponseValidationIssue]) -> str | None:
    if not issues:
        return None
    errors = sum(1 for issue in issues if issue.severity == ResponseValidationSeverity.ERROR)
    warnings = len(issues) - errors
    if errors:
        return f"Response validation failed with {errors} error(s) and {warnings} warning(s)."
    return f"Response validation passed with {warnings} warning(s)."