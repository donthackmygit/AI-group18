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

    def retrieve_hybrid(
        self,
        *,
        query_text: str,
        query_embedding: np.ndarray,
        top_k: int,
        filter_metadata: dict[str, Any] | None = None,
        status: str | None = None,
        effective_date: date | None = None,
        topic_hint: str | None = None,
    ) -> RetrievalPayload:
        resolved_effective_date = effective_date or date.today()
        resolved_filter_metadata = filter_metadata or {}
        semantic_limit = max(top_k * 2, top_k)
        keyword_limit = max(top_k * 2, top_k)

        semantic_rows = self.repository.search(
            query_embedding=query_embedding,
            top_k=semantic_limit,
            filter_metadata=resolved_filter_metadata,
            status=status,
            effective_date=resolved_effective_date,
        )
        keyword_rows = self.repository.search_keyword(
            query_text=query_text,
            top_k=keyword_limit,
            filter_metadata=resolved_filter_metadata,
            status=status,
            effective_date=resolved_effective_date,
        )

        fused_rows = _fuse_rows(
            semantic_rows=semantic_rows,
            keyword_rows=keyword_rows,
            top_k=top_k,
        )
        if _is_personal_deduction_topic(topic_hint):
            priority_rows = self.repository.search_personal_deduction(
                top_k=min(2, top_k),
                status=status,
                effective_date=resolved_effective_date,
            )
            fused_rows = _merge_priority_rows(priority_rows, fused_rows, top_k)

        citations = [self._row_to_citation(index, row) for index, row in enumerate(fused_rows, start=1)]
        similarities = [citation.similarity for citation in citations]
        result = RetrievalResult(
            strategy=RetrievalStrategy.HYBRID_SEARCH,
            source="supabase_pgvector_postgres_full_text",
            table="rag.chunks",
            requested_top_k=top_k,
            returned_count=len(citations),
            semantic_count=len(semantic_rows),
            keyword_count=len(keyword_rows),
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
                "Hybrid retrieval fuses pgvector semantic candidates and PostgreSQL full-text keyword "
                "candidates with reciprocal-rank fusion before heuristic re-ranking."
            ),
        )
        return RetrievalPayload(citations=citations, result=result)

    @staticmethod
    def _row_to_citation(index: int, row: dict[str, Any]) -> Citation:
        metadata = row.get("metadata") or {}
        similarity = row.get("similarity")
        if similarity is None:
            similarity = row.get("hybrid_score")
        if similarity is None:
            similarity = row.get("keyword_score")
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
            similarity=float(similarity or 0.0),
            content=str(row.get("content") or ""),
            metadata=metadata,
            retrieval_rank=index,
            semantic_rank=row.get("semantic_rank"),
            keyword_rank=row.get("keyword_rank"),
            keyword_score=(
                float(row["keyword_score"])
                if row.get("keyword_score") is not None
                else None
            ),
            hybrid_score=(
                float(row["hybrid_score"])
                if row.get("hybrid_score") is not None
                else None
            ),
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


def _fuse_rows(
    *,
    semantic_rows: list[dict[str, Any]],
    keyword_rows: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    by_chunk_id: dict[str, dict[str, Any]] = {}
    semantic_count = max(len(semantic_rows), 1)
    keyword_count = max(len(keyword_rows), 1)

    for rank, row in enumerate(semantic_rows, start=1):
        chunk_id = str(row.get("chunk_id") or "")
        if not chunk_id:
            continue
        current = by_chunk_id.setdefault(chunk_id, dict(row))
        current["semantic_rank"] = rank
        current["similarity"] = float(row.get("similarity") or 0.0)
        current["_semantic_rrf"] = 1.0 / (60 + rank)
        current["_semantic_norm"] = max(0.0, (semantic_count - rank + 1) / semantic_count)

    for rank, row in enumerate(keyword_rows, start=1):
        chunk_id = str(row.get("chunk_id") or "")
        if not chunk_id:
            continue
        current = by_chunk_id.setdefault(chunk_id, dict(row))
        current["keyword_rank"] = rank
        current["keyword_score"] = float(row.get("keyword_score") or 0.0)
        current["_keyword_rrf"] = 1.0 / (60 + rank)
        current["_keyword_norm"] = max(0.0, (keyword_count - rank + 1) / keyword_count)

    fused_rows = []
    for row in by_chunk_id.values():
        semantic_rrf = float(row.pop("_semantic_rrf", 0.0))
        keyword_rrf = float(row.pop("_keyword_rrf", 0.0))
        semantic_norm = float(row.pop("_semantic_norm", 0.0))
        keyword_norm = float(row.pop("_keyword_norm", 0.0))
        hybrid_score = (semantic_rrf + keyword_rrf) + (0.12 * semantic_norm) + (0.08 * keyword_norm)
        row["hybrid_score"] = hybrid_score
        metadata = dict(row.get("metadata") or {})
        metadata.update(
            {
                "hybrid_score": hybrid_score,
                "semantic_rank": row.get("semantic_rank"),
                "keyword_rank": row.get("keyword_rank"),
                "keyword_score": row.get("keyword_score"),
            }
        )
        row["metadata"] = metadata
        fused_rows.append(row)

    return sorted(
        fused_rows,
        key=lambda row: (
            -float(row.get("hybrid_score") or 0.0),
            row.get("semantic_rank") or 9999,
            row.get("keyword_rank") or 9999,
            str(row.get("chunk_id") or ""),
        ),
    )[:top_k]


def _first_http_url(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue

        text = str(value).strip()
        if text.startswith(("https://", "http://")):
            return text

    return None
