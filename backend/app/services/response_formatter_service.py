from __future__ import annotations
import json
import re
from typing import Any

from backend.app.schemas.context import ContextBuildResult
from backend.app.schemas.llm import LLMGenerationResult
from backend.app.schemas.prompt import PromptBuildResult
from backend.app.schemas.query_embedding import QueryEmbeddingResult
from backend.app.schemas.question_processing import ProcessedQuestion
from backend.app.schemas.query_route import QueryClassificationResult, QueryRoutingResult
from backend.app.schemas.rag import ChatResponse, Citation
from backend.app.schemas.reranking import RerankingResult
from backend.app.schemas.response_formatter import (
    FormattedCalculation,
    FormattedCitation,
    ResponseFormatResult,
)
from backend.app.schemas.response_validation import ResponseValidationResult
from backend.app.schemas.retrieval import RetrievalResult
from backend.app.schemas.tax_calculation import TaxCalculationResult, TaxCalculationStep


FORMAT_VERSION = "backend_chat_response_v1"
MAX_CITATION_CONTENT_CHARS = 700
ADVISORY_WARNING = (
    "Kết quả chỉ mang tính tham khảo, không thay thế ý kiến của cơ quan thuế "
    "hoặc chuyên gia thuế."
)
EMPTY_ANSWER = "Hệ thống chưa tạo được câu trả lời phù hợp."
CONFIDENCE_LABELS = {
    "low": 0.35,
    "medium": 0.65,
    "high": 0.85,
}


class ResponseFormatterService:
    def format_chat_response(
        self,
        *,
        answer: str | None,
        conversation_id: str | None,
        mode: str,
        assistant_message_id: str | None = None,
        citations: list[Citation] | None = None,
        calculation: TaxCalculationResult | None = None,
        confidence: float | None = None,
        warning: str | None = None,
        processed_question: ProcessedQuestion | None = None,
        classification: QueryClassificationResult | None = None,
        routing: QueryRoutingResult | None = None,
        query_embedding: QueryEmbeddingResult | None = None,
        retrieval: RetrievalResult | None = None,
        reranking: RerankingResult | None = None,
        context: ContextBuildResult | None = None,
        prompt: PromptBuildResult | None = None,
        llm: LLMGenerationResult | None = None,
        response_validation: ResponseValidationResult | None = None,
    ) -> ChatResponse:
        source_citations = citations or []
        formatted_citations = [_format_citation(citation) for citation in source_citations]
        formatted_calculation = _format_calculation(calculation)
        formatted_confidence = _format_confidence(confidence, llm)
        formatted_warnings = _format_warnings(
            warning,
            calculation.warnings if calculation else [],
            include_advisory=mode in {"llm", "llm_fallback"},
        )

        return ChatResponse(
            answer=_format_answer(answer),
            conversation_id=conversation_id,
            assistant_message_id=assistant_message_id,
            mode=mode,
            citations=formatted_citations,
            confidence=formatted_confidence,
            warnings=formatted_warnings,
            calculation=formatted_calculation,
            processed_question=processed_question,
            classification=classification,
            routing=routing,
            query_embedding=query_embedding,
            retrieval=retrieval,
            reranking=reranking,
            tax_calculation=calculation,
            context=context,
            prompt=prompt,
            llm=llm,
            response_validation=response_validation,
            response_formatter=ResponseFormatResult(
                applied=True,
                format_version=FORMAT_VERSION,
                citation_count=len(formatted_citations),
                calculation_included=formatted_calculation is not None,
                confidence=formatted_confidence,
                warning_count=len(formatted_warnings),
                note=(
                    "Response Formatter normalizes the final backend response into answer, "
                    "conversation_id, citations, calculation, confidence, and warning fields."
                ),
            ),
            debug=(
                {
                    "response_validation": response_validation.model_dump(mode="json")
                    if response_validation
                    else None
                }
                if settings.expose_debug_payload
                else None
            ),
        )


def _format_answer(answer: str | None) -> str:
    if answer is None:
        return EMPTY_ANSWER

    normalized = answer.strip()
    if not normalized:
        return EMPTY_ANSWER

    parsed_answer = _extract_answer_from_json(normalized)
    return parsed_answer or normalized


def _extract_answer_from_json(value: str) -> str | None:
    candidates = [
        value,
        _strip_json_markdown_fence(value),
    ]

    for candidate in candidates:
        if not candidate:
            continue

        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        if not isinstance(parsed, dict):
            continue

        answer = parsed.get("answer")
        if isinstance(answer, str) and answer.strip():
            return answer.strip()

    return None


def _strip_json_markdown_fence(value: str) -> str | None:
    match = re.fullmatch(
        r"\s*```(?:json)?\s*(.*?)\s*```\s*",
        value,
        flags=re.DOTALL | re.IGNORECASE,
    )

    if not match:
        return None

    return match.group(1).strip()


def _format_citation(citation: Citation) -> FormattedCitation:
    metadata = citation.metadata or {}

    return FormattedCitation(
        citation_id=citation.citation_id,
        chunk_id=citation.chunk_id,
        document_id=citation.document_id,
        document_name=_first_text(
            citation.document_title,
            metadata.get("document_name"),
            metadata.get("document_title"),
            citation.document_number,
            citation.document_id,
        ),
        document_number=_first_text(
            citation.document_number,
            metadata.get("document_number"),
        ),
        document_type=_first_text(
            citation.document_type,
            metadata.get("document_type"),
        ),
        issuing_authority=_first_text(
            citation.issuing_authority,
            metadata.get("issuing_authority"),
        ),
        article=_format_article(citation),
        clause=_format_clause(metadata),
        content=_format_content(citation.content),
        source_url=citation.source_url,
        status=citation.status,
    )


def _format_article(citation: Citation) -> str | None:
    article = _first_text(citation.article, citation.article_number)
    if citation.article_title and article and citation.article_title not in article:
        return f"{article} - {citation.article_title}"
    return _first_text(article, citation.article_title)


def _format_clause(metadata: dict[str, Any]) -> str | None:
    value = _range_value(
        metadata.get("clause_start") or metadata.get("clause") or metadata.get("clause_number"),
        metadata.get("clause_end"),
    )
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.casefold().startswith(("khoản", "khoan")):
        return normalized
    if re.fullmatch(r"\d+(?:-\d+)?", normalized):
        return f"Khoản {normalized}"
    return normalized


def _format_content(content: str) -> str:
    normalized = re.sub(r"\s+", " ", content).strip()
    if len(normalized) <= MAX_CITATION_CONTENT_CHARS:
        return normalized
    trimmed = normalized[:MAX_CITATION_CONTENT_CHARS].rstrip()
    if " " in trimmed:
        trimmed = trimmed.rsplit(" ", 1)[0].rstrip()
    return f"{trimmed}..."


def _format_calculation(calculation: TaxCalculationResult | None) -> FormattedCalculation | None:
    if calculation is None:
        return None
    return FormattedCalculation(
        taxable_income=calculation.taxable_income,
        personal_deduction=calculation.personal_deduction,
        dependent_deduction=calculation.dependent_deduction,
        tax_amount=calculation.tax_amount,
        calculation_steps=[
            _format_calculation_step(step) for step in calculation.calculation_steps
        ],
        missing_fields=calculation.missing_fields,
        warnings=calculation.warnings,
    )


def _format_calculation_step(step: TaxCalculationStep) -> str:
    parts = [step.label]
    if step.amount is not None:
        parts.append(f"{_format_money(step.amount)} VND")
    if step.formula:
        parts.append(step.formula)
    return " - ".join(parts)


def _format_money(amount: int) -> str:
    return f"{amount:,}".replace(",", ".")


def _format_confidence(
    confidence: float | None,
    llm: LLMGenerationResult | None,
) -> float | None:
    value = confidence
    if value is None and llm and llm.confidence_label:
        value = CONFIDENCE_LABELS.get(llm.confidence_label.strip().casefold())
    if value is None:
        return None
    return round(min(max(float(value), 0.0), 1.0), 4)


def _format_warnings(
    warning: str | None,
    calculation_warnings: list[str],
    *,
    include_advisory: bool,
) -> list[str]:
    values: list[str] = []

    if warning:
        values.extend(
            part.strip()
            for part in warning.split("|")
            if part.strip()
        )

    values.extend(
        value.strip()
        for value in calculation_warnings
        if value and value.strip()
    )

    if include_advisory:
        values.append(ADVISORY_WARNING)

    return list(dict.fromkeys(values))


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _range_value(start: Any, end: Any) -> str | None:
    if start is None or start == "":
        return None
    if end is None or end == "" or str(end) == str(start):
        return str(start)
    return f"{start}-{end}"
