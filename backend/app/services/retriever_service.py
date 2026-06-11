from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import unicodedata
from typing import Any

import numpy as np

from backend.app.core.config import Settings
from backend.app.repositories.rag_chunk_repository import RagChunkRepository
from backend.app.schemas.rag import Citation
from backend.app.schemas.retrieval import (
    RetrievalFilters,
    RetrievalResult,
    RetrievalStrategy,
)
from backend.app.services.embedding_service import EmbeddingService


@dataclass(frozen=True)
class RetrievalPayload:
    citations: list[Citation]
    result: RetrievalResult


class RetrieverService:
    def __init__(self, settings: Settings, embedding_service: EmbeddingService) -> None:
        self.embedding_service = embedding_service
        self.repository = RagChunkRepository(settings)

    def retrieve(
        self,
        question: str,
        top_k: int,
        filter_metadata: dict[str, Any] | None = None,
        status: str | None = None,
        effective_date: date | None = None,
    ) -> list[Citation]:
        query_embedding = self.embedding_service.encode_query(question)
        return self.retrieve_by_embedding(
            query_embedding=query_embedding,
            top_k=top_k,
            filter_metadata=filter_metadata,
            status=status,
            effective_date=effective_date,
        )

    def retrieve_by_embedding(
        self,
        query_embedding: np.ndarray,
        top_k: int,
        filter_metadata: dict[str, Any] | None = None,
        status: str | None = None,
        effective_date: date | None = None,
    ) -> list[Citation]:
        return self.retrieve_semantic(
            query_embedding=query_embedding,
            top_k=top_k,
            filter_metadata=filter_metadata,
            status=status,
            effective_date=effective_date,
        ).citations

    def retrieve_semantic(
        self,
        query_embedding: np.ndarray,
        top_k: int,
        filter_metadata: dict[str, Any] | None = None,
        status: str | None = None,
        effective_date: date | None = None,
        topic_hint: str | None = None,
    ) -> RetrievalPayload:
        resolved_effective_date = effective_date or date.today()
        resolved_filter_metadata = filter_metadata or {}
        rows = self.repository.search(
            query_embedding=query_embedding,
            top_k=top_k,
            filter_metadata=resolved_filter_metadata,
            status=status,
            effective_date=resolved_effective_date,
        )
        if _is_personal_deduction_topic(topic_hint):
            priority_rows = self.repository.search_personal_deduction(
                top_k=min(2, top_k),
                status=status,
                effective_date=resolved_effective_date,
            )
            rows = _merge_priority_rows(priority_rows, rows, top_k)

        citations = [self._row_to_citation(index, row) for index, row in enumerate(rows, start=1)]
        similarities = [citation.similarity for citation in citations]
        result = RetrievalResult(
            strategy=RetrievalStrategy.SEMANTIC_SEARCH,
            source="supabase_pgvector",
            table="rag.chunks",
            requested_top_k=top_k,
            returned_count=len(citations),
            filters=RetrievalFilters(
                status=status,
                effective_date=resolved_effective_date,
                filter_metadata=resolved_filter_metadata,
                topic_hint=topic_hint,
            ),
            similarity_min=min(similarities) if similarities else None,
            similarity_max=max(similarities) if similarities else None,
            similarity_avg=(sum(similarities) / len(similarities)) if similarities else None,
            note=(
                "Semantic search over pgvector cosine similarity. topic_hint is informational "
                "until topic metadata is normalized for hard filtering."
            ),
        )
        return RetrievalPayload(citations=citations, result=result)

    @staticmethod
    def _row_to_citation(index: int, row: dict[str, Any]) -> Citation:
        metadata = row.get("metadata") or {}
        return Citation(
            citation_id=f"SOURCE_{index}",
            chunk_id=str(row.get("chunk_id") or ""),
            document_id=row.get("document_id"),
            document_title=row.get("document_title"),
            document_number=row.get("document_number"),
            document_type=row.get("document_type"),
            issuing_authority=row.get("issuing_authority"),
            article=row.get("article"),
            article_number=row.get("article_number"),
            article_title=row.get("article_title"),
            chapter=row.get("chapter"),
            section=row.get("section"),
            source_url=_first_http_url(row.get("source_url"), metadata.get("source_url")),
            local_path=row.get("local_path"),
            status=row.get("status"),
            issue_date=row.get("issue_date"),
            effective_date=row.get("effective_date"),
            expiry_date=row.get("expiry_date"),
            similarity=float(row.get("similarity") or 0.0),
            content=str(row.get("content") or ""),
            metadata=metadata,
            retrieval_rank=index,
        )


def _is_personal_deduction_topic(topic_hint: str | None) -> bool:
    if not topic_hint:
        return False
    normalized = unicodedata.normalize("NFD", topic_hint.casefold())
    ascii_text = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return "giam tru gia canh" in ascii_text


def _merge_priority_rows(
    priority_rows: list[dict[str, Any]],
    semantic_rows: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in [*priority_rows, *semantic_rows]:
        chunk_id = str(row.get("chunk_id") or "")
        if chunk_id and chunk_id in seen:
            continue
        if chunk_id:
            seen.add(chunk_id)
        merged.append(row)
        if len(merged) >= top_k:
            break

    return merged


def _first_http_url(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue

        text = str(value).strip()
        if text.startswith(("https://", "http://")):
            return text

    return None
