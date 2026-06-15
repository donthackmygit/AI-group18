from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from backend.app.schemas.query_route import QueryClassificationResult, QueryIntent
from backend.app.schemas.question_processing import ProcessedQuestion
from backend.app.schemas.rag import Citation
from backend.app.schemas.reranking import (
    RerankedCandidate,
    RerankingResult,
    RerankingStrategy,
)


STOPWORDS = {
    "và",
    "là",
    "có",
    "thì",
    "cho",
    "của",
    "về",
    "trong",
    "theo",
    "một",
    "các",
    "này",
    "được",
    "người",
    "thuế",
    "tncn",
}

PERSONAL_DEDUCTION_DOCUMENT_NUMBERS = {
    "109/2025/QH15",
    "954/2020/UBTVQH14",
}


@dataclass(frozen=True)
class ScoredCitation:
    citation: Citation
    candidate: RerankedCandidate


class RerankerService:
    def rerank(
        self,
        citations: list[Citation],
        processed_question: ProcessedQuestion,
        classification: QueryClassificationResult,
        top_k: int,
    ) -> tuple[list[Citation], RerankingResult]:
        if not citations:
            return [], RerankingResult(
                strategy=RerankingStrategy.HEURISTIC,
                applied=False,
                input_count=0,
                output_count=0,
                requested_top_k=top_k,
                note="No retrieved candidates to re-rank.",
            )

        query_text = " ".join(
            [
                processed_question.standalone_question,
                processed_question.retrieval_query,
                processed_question.topic or "",
            ]
        )
        query_tokens = _tokenize(query_text)
        article_numbers = _extract_article_numbers(query_text)

        scored = [
            self._score_citation(
                citation=citation,
                query_tokens=query_tokens,
                article_numbers=article_numbers,
                processed_question=processed_question,
                classification=classification,
            )
            for citation in citations
        ]

        scored.sort(
            key=lambda item: (
                item.candidate.rerank_score,
                item.citation.similarity,
                -(item.citation.retrieval_rank or 9999),
            ),
            reverse=True,
        )

        output_count = min(top_k, len(scored))
        selected = scored[:output_count]
        reranked_citations: list[Citation] = []
        candidates: list[RerankedCandidate] = []

        for rank, item in enumerate(selected, start=1):
            candidate = item.candidate.model_copy(update={"rerank_rank": rank})
            candidates.append(candidate)
            reranked_citations.append(
                item.citation.model_copy(
                    update={
                        "citation_id": f"SOURCE_{rank}",
                        "rerank_rank": rank,
                        "rerank_score": candidate.rerank_score,
                    }
                )
            )

        scores = [candidate.rerank_score for candidate in candidates]
        return reranked_citations, RerankingResult(
            strategy=RerankingStrategy.HEURISTIC,
            applied=True,
            input_count=len(citations),
            output_count=len(reranked_citations),
            requested_top_k=top_k,
            score_min=min(scores) if scores else None,
            score_max=max(scores) if scores else None,
            score_avg=(sum(scores) / len(scores)) if scores else None,
            candidates=candidates,
            note=(
                "Heuristic re-ranking combines vector similarity, keyword overlap, topic match, "
                "legal metadata boosts, effective document status, and personal deduction authority boosts."
            ),
        )

    def _score_citation(
        self,
        citation: Citation,
        query_tokens: set[str],
        article_numbers: set[str],
        processed_question: ProcessedQuestion,
        classification: QueryClassificationResult,
    ) -> ScoredCitation:
        candidate_text = _citation_text(citation)
        candidate_tokens = _tokenize(candidate_text)
        keyword_overlap = _overlap_score(query_tokens, candidate_tokens)
        topic_score = _topic_score(processed_question.topic, candidate_tokens)
        metadata_boost, reasons = _metadata_boost(citation, article_numbers)

        if classification.intent == QueryIntent.TAX_CALCULATION:
            tax_score = _overlap_score(
                {
                    "giảm",
                    "trừ",
                    "gia",
                    "cảnh",
                    "phụ",
                    "thuộc",
                    "bảo",
                    "hiểm",
                    "biểu",
                    "lũy",
                    "tiến",
                    "tính",
                },
                candidate_tokens,
            )
            metadata_boost += min(tax_score * 0.06, 0.06)
            if tax_score:
                reasons.append("tax_calculation_terms")

        if _is_personal_deduction_topic(processed_question.topic):
            personal_boost, personal_reasons = _personal_deduction_metadata_boost(
                citation
            )
            metadata_boost += personal_boost
            reasons.extend(personal_reasons)

        score = (
            0.65 * citation.similarity
            + 0.22 * keyword_overlap
            + 0.08 * topic_score
            + metadata_boost
        )
        score = max(0.0, min(score, 1.0))

        candidate = RerankedCandidate(
            chunk_id=citation.chunk_id,
            retrieval_rank=citation.retrieval_rank or 0,
            rerank_rank=0,
            similarity=citation.similarity,
            semantic_rank=citation.semantic_rank,
            keyword_rank=citation.keyword_rank,
            keyword_score=citation.keyword_score,
            hybrid_score=citation.hybrid_score,
            rerank_score=score,
            keyword_overlap=keyword_overlap,
            topic_score=topic_score,
            metadata_boost=metadata_boost,
            reasons=reasons,
        )
        return ScoredCitation(citation=citation, candidate=candidate)


def _tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[\w]+", text.casefold(), flags=re.UNICODE)
    return {token for token in tokens if len(token) >= 2 and token not in STOPWORDS}


def _overlap_score(query_tokens: set[str], candidate_tokens: set[str]) -> float:
    if not query_tokens or not candidate_tokens:
        return 0.0

    return len(query_tokens & candidate_tokens) / len(query_tokens)


def _topic_score(topic: str | None, candidate_tokens: set[str]) -> float:
    if not topic:
        return 0.0

    topic_tokens = _tokenize(topic)
    return _overlap_score(topic_tokens, candidate_tokens)


def _extract_article_numbers(text: str) -> set[str]:
    return set(re.findall(r"(?:điều|dieu)\s*(\d+)", text.casefold()))


def _is_personal_deduction_topic(topic: str | None) -> bool:
    if not topic:
        return False

    normalized = unicodedata.normalize("NFD", topic.casefold())
    ascii_text = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return "giam tru gia canh" in ascii_text


def _personal_deduction_metadata_boost(citation: Citation) -> tuple[float, list[str]]:
    boost = 0.0
    reasons: list[str] = []

    text = _ascii_text(_citation_text(citation))
    document_number = citation.document_number or ""

    if document_number in PERSONAL_DEDUCTION_DOCUMENT_NUMBERS:
        boost += 0.08
        reasons.append("personal_deduction_authority_document")

    if "giam tru gia canh" in text:
        boost += 0.06
        reasons.append("personal_deduction_content_match")

    if "nguoi phu thuoc" in text:
        boost += 0.03
        reasons.append("dependent_deduction_content_match")

    if citation.status == "effective":
        boost += 0.02
        reasons.append("personal_deduction_effective_status")

    effective_year = _date_year(citation.effective_date)
    if effective_year and effective_year >= 2026:
        boost += 0.04
        reasons.append("personal_deduction_newer_effective_rule")

    return min(boost, 0.18), reasons


def _citation_text(citation: Citation) -> str:
    metadata = citation.metadata or {}
    metadata_text = " ".join(
        str(metadata.get(key) or "")
        for key in [
            "topics",
            "topic",
            "title",
            "document_title",
            "document_name",
            "article_title",
            "article",
        ]
    )
    return " ".join(
        [
            citation.content,
            citation.document_title or "",
            citation.document_number or "",
            citation.document_type or "",
            citation.article or "",
            citation.article_title or "",
            citation.chapter or "",
            citation.section or "",
            metadata_text,
        ]
    )


def _metadata_boost(citation: Citation, article_numbers: set[str]) -> tuple[float, list[str]]:
    boost = 0.0
    reasons: list[str] = []

    if citation.status == "effective":
        boost += 0.03
        reasons.append("effective_status")

    if citation.article_number and citation.article_number in article_numbers:
        boost += 0.08
        reasons.append("article_number_match")

    if citation.document_number and citation.document_number.casefold() in _citation_text(citation).casefold():
        boost += 0.01
        reasons.append("document_number_present")

    if citation.source_url:
        boost += 0.01
        reasons.append("source_url_present")

    return min(boost, 0.15), reasons


def _ascii_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.casefold())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _date_year(value: object) -> int | None:
    if isinstance(value, date):
        return value.year

    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value[:10]).year
        except ValueError:
            return None

    return None
