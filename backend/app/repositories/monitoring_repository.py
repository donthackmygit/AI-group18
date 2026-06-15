from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.core.config import Settings
from backend.app.core.database import get_database_connection
from backend.app.schemas.monitoring import (
    FeedbackSummary,
    IngestionLogItem,
    IngestionLogListResponse,
    LowConfidenceItem,
    MonitoringDashboardResponse,
    QueryLogListItem,
    QueryLogListResponse,
    TopDocumentItem,
)
from backend.app.schemas.rag import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)


INSERT_QUERY_LOG_SQL = """
    insert into rag.query_logs (
        conversation_id,
        user_id,
        assistant_message_id,
        status,
        mode,
        original_question,
        normalized_question,
        standalone_question,
        retrieval_query,
        intent,
        route,
        confidence,
        top_k,
        retrieved_count,
        reranked_count,
        prompt_estimated_tokens,
        llm_provider,
        llm_model,
        llm_prompt_estimated_tokens,
        llm_max_output_tokens,
        llm_prompt_tokens,
        llm_completion_tokens,
        llm_total_tokens,
        llm_estimated_cost_usd,
        response_time_ms,
        answer,
        warnings,
        request_payload,
        processed_question,
        classification,
        routing,
        query_embedding,
        retrieval,
        reranking,
        tax_calculation,
        context_metadata,
        prompt_metadata,
        llm,
        response_validation,
        citations
    )
    values (
        %(conversation_id)s,
        %(user_id)s,
        %(assistant_message_id)s,
        %(status)s,
        %(mode)s,
        %(original_question)s,
        %(normalized_question)s,
        %(standalone_question)s,
        %(retrieval_query)s,
        %(intent)s,
        %(route)s,
        %(confidence)s,
        %(top_k)s,
        %(retrieved_count)s,
        %(reranked_count)s,
        %(prompt_estimated_tokens)s,
        %(llm_provider)s,
        %(llm_model)s,
        %(llm_prompt_estimated_tokens)s,
        %(llm_max_output_tokens)s,
        %(llm_prompt_tokens)s,
        %(llm_completion_tokens)s,
        %(llm_total_tokens)s,
        %(llm_estimated_cost_usd)s,
        %(response_time_ms)s,
        %(answer)s,
        %(warnings)s,
        %(request_payload)s,
        %(processed_question)s,
        %(classification)s,
        %(routing)s,
        %(query_embedding)s,
        %(retrieval)s,
        %(reranking)s,
        %(tax_calculation)s,
        %(context_metadata)s,
        %(prompt_metadata)s,
        %(llm)s,
        %(response_validation)s,
        %(citations)s
    )
    returning id;
"""


INSERT_QUERY_ERROR_SQL = """
    insert into rag.query_logs (
        conversation_id,
        user_id,
        status,
        original_question,
        response_time_ms,
        error_type,
        error_message,
        request_payload
    )
    values (
        %(conversation_id)s,
        %(user_id)s,
        'error',
        %(original_question)s,
        %(response_time_ms)s,
        %(error_type)s,
        %(error_message)s,
        %(request_payload)s
    )
    returning id;
"""


INSERT_QUERY_CHUNK_SQL = """
    insert into rag.query_log_chunks (
        query_log_id,
        citation_id,
        chunk_id,
        document_id,
        document_number,
        document_name,
        document_type,
        article,
        source_url,
        retrieval_rank,
        rerank_rank,
        similarity,
        rerank_score,
        content_preview,
        metadata
    )
    values (
        %(query_log_id)s,
        %(citation_id)s,
        %(chunk_id)s,
        %(document_id)s,
        %(document_number)s,
        %(document_name)s,
        %(document_type)s,
        %(article)s,
        %(source_url)s,
        %(retrieval_rank)s,
        %(rerank_rank)s,
        %(similarity)s,
        %(rerank_score)s,
        %(content_preview)s,
        %(metadata)s
    );
"""


class MonitoringRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def insert_query_log(
        self,
        *,
        request: ChatRequest,
        response: ChatResponse,
        user_id: str | None,
        response_time_ms: int,
    ) -> str:
        psycopg, dict_row, Jsonb = self._load_database_dependencies()
        processed_question = response.processed_question
        classification = response.classification
        routing = response.routing
        query_embedding = response.query_embedding
        retrieval = response.retrieval
        reranking = response.reranking
        prompt = response.prompt
        llm = response.llm
        response_validation = response.response_validation

        params = {
            "conversation_id": response.conversation_id or request.conversation_id,
            "user_id": user_id,
            "assistant_message_id": response.assistant_message_id,
            "status": _status_from_response(response),
            "mode": response.mode,
            "original_question": request.question,
            "normalized_question": getattr(processed_question, "normalized_question", None),
            "standalone_question": getattr(processed_question, "standalone_question", None),
            "retrieval_query": getattr(processed_question, "retrieval_query", None),
            "intent": _enum_or_value(getattr(classification, "intent", None)),
            "route": _enum_or_value(getattr(routing, "route", None)),
            "confidence": response.confidence,
            "top_k": getattr(retrieval, "requested_top_k", None),
            "retrieved_count": getattr(retrieval, "returned_count", None),
            "reranked_count": getattr(reranking, "output_count", None),
            "prompt_estimated_tokens": getattr(prompt, "estimated_tokens", None),
            "llm_provider": _enum_or_value(getattr(llm, "provider", None)),
            "llm_model": getattr(llm, "model", None),
            "llm_prompt_estimated_tokens": getattr(llm, "prompt_estimated_tokens", None),
            "llm_max_output_tokens": getattr(llm, "max_output_tokens", None),
            "llm_prompt_tokens": getattr(llm, "prompt_tokens", None),
            "llm_completion_tokens": getattr(llm, "completion_tokens", None),
            "llm_total_tokens": getattr(llm, "total_tokens", None),
            "llm_estimated_cost_usd": getattr(llm, "estimated_cost_usd", None),
            "response_time_ms": response_time_ms,
            "answer": response.answer,
            "warnings": Jsonb(response.warnings),
            "request_payload": Jsonb(_dump_model(request)),
            "processed_question": Jsonb(_dump_model(processed_question)),
            "classification": Jsonb(_dump_model(classification)),
            "routing": Jsonb(_dump_model(routing)),
            "query_embedding": Jsonb(_dump_model(query_embedding)),
            "retrieval": Jsonb(_dump_model(retrieval)),
            "reranking": Jsonb(_dump_model(reranking)),
            "tax_calculation": Jsonb(_dump_model(response.tax_calculation)),
            "context_metadata": Jsonb(_dump_model(response.context)),
            "prompt_metadata": Jsonb(_dump_model(prompt)),
            "llm": Jsonb(_dump_model(llm)),
            "response_validation": Jsonb(_dump_model(response_validation)),
            "citations": Jsonb([_dump_model(citation) for citation in response.citations]),
        }

        with get_database_connection(self.settings) as conn:
            self._ensure_usage_columns(conn)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(INSERT_QUERY_LOG_SQL, params)
                row = cur.fetchone()
                query_log_id = str(row["id"])

                chunk_rows = self._build_chunk_rows(
                    query_log_id=query_log_id,
                    response=response,
                    Jsonb=Jsonb,
                )
                if chunk_rows:
                    cur.executemany(INSERT_QUERY_CHUNK_SQL, chunk_rows)

            conn.commit()
            return query_log_id

    def insert_query_error(
        self,
        *,
        request: ChatRequest,
        user_id: str | None,
        response_time_ms: int,
        exc: Exception,
    ) -> str:
        psycopg, dict_row, Jsonb = self._load_database_dependencies()
        params = {
            "conversation_id": request.conversation_id,
            "user_id": user_id,
            "original_question": request.question,
            "response_time_ms": response_time_ms,
            "error_type": exc.__class__.__name__,
            "error_message": str(exc),
            "request_payload": Jsonb(_dump_model(request)),
        }

        with get_database_connection(self.settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(INSERT_QUERY_ERROR_SQL, params)
                row = cur.fetchone()
            conn.commit()
            return str(row["id"])

    def list_query_logs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        days: int | None = None,
    ) -> QueryLogListResponse:
        psycopg, dict_row, _ = self._load_database_dependencies()

        clauses = []
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }

        if status:
            clauses.append("status = %(status)s")
            params["status"] = status

        if days:
            clauses.append("created_at >= %(since)s")
            params["since"] = _since(days)

        where_sql = f"where {' and '.join(clauses)}" if clauses else ""

        sql = f"""
            select
                id::text,
                created_at,
                status,
                mode,
                conversation_id,
                user_id,
                original_question,
                standalone_question,
                intent,
                route,
                confidence,
                response_time_ms,
                retrieved_count,
                reranked_count,
                llm_model,
                llm_prompt_tokens,
                llm_completion_tokens,
                llm_total_tokens,
                llm_estimated_cost_usd,
                error_message,
                warnings
            from rag.query_logs
            {where_sql}
            order by created_at desc
            limit %(limit)s
            offset %(offset)s;
        """

        with get_database_connection(self.settings) as conn:
            self._ensure_usage_columns(conn)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        return QueryLogListResponse(
            items=[
                QueryLogListItem(
                    **{
                        **row,
                        "warnings": row.get("warnings") or [],
                    }
                )
                for row in rows
            ],
            limit=limit,
            offset=offset,
        )

    def dashboard(self, *, days: int = 7) -> MonitoringDashboardResponse:
        psycopg, dict_row, _ = self._load_database_dependencies()
        since = _since(days)

        metrics_sql = """
            select
                count(*)::int as total_queries,
                count(*) filter (where status = 'success')::int as success_count,
                count(*) filter (where status in ('blocked', 'rejected'))::int as blocked_count,
                count(*) filter (where status = 'error')::int as error_count,
                count(*) filter (where status = 'llm_fallback')::int as llm_fallback_count,
                avg(response_time_ms)::float as avg_response_time_ms,
                percentile_cont(0.95) within group (order by response_time_ms)::float
                    as p95_response_time_ms,
                avg(confidence)::float as avg_confidence,
                coalesce(sum(prompt_estimated_tokens), 0)::int
                    as total_prompt_estimated_tokens,
                coalesce(sum(llm_max_output_tokens), 0)::int
                    as total_llm_max_output_tokens,
                coalesce(sum(llm_prompt_tokens), 0)::int
                    as total_llm_prompt_tokens,
                coalesce(sum(llm_completion_tokens), 0)::int
                    as total_llm_completion_tokens,
                coalesce(sum(llm_total_tokens), 0)::int
                    as total_llm_tokens,
                coalesce(sum(llm_estimated_cost_usd), 0)::double precision
                    as total_llm_estimated_cost_usd
            from rag.query_logs
            where created_at >= %(since)s;
        """

        top_documents_sql = """
            select
                coalesce(document_number, document_id, 'unknown') as document,
                count(*)::int as hit_count,
                avg(similarity)::float as avg_similarity,
                max(created_at) as last_used_at
            from rag.query_log_chunks
            where created_at >= %(since)s
            group by coalesce(document_number, document_id, 'unknown')
            order by hit_count desc, last_used_at desc
            limit 10;
        """

        low_confidence_sql = """
            select
                id::text,
                created_at,
                original_question,
                confidence,
                mode,
                warnings
            from rag.query_logs
            where created_at >= %(since)s
              and confidence is not null
              and confidence < 0.55
            order by created_at desc
            limit 10;
        """

        feedback_sql = """
            select
                count(*)::int as total_feedback,
                count(*) filter (where rating = 1)::int as positive_count,
                count(*) filter (where rating = -1)::int as negative_count
            from public.feedback
            where created_at >= %(since)s;
        """

        with get_database_connection(self.settings) as conn:
            self._ensure_usage_columns(conn)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(metrics_sql, {"since": since})
                metrics = cur.fetchone() or {}

                cur.execute(top_documents_sql, {"since": since})
                top_documents = cur.fetchall()

                cur.execute(low_confidence_sql, {"since": since})
                low_confidence_items = cur.fetchall()

                cur.execute(feedback_sql, {"since": since})
                feedback = cur.fetchone() or {}

        return MonitoringDashboardResponse(
            days=days,
            **metrics,
            feedback=FeedbackSummary(**feedback),
            top_documents=[TopDocumentItem(**row) for row in top_documents],
            low_confidence_items=[
                LowConfidenceItem(
                    **{
                        **row,
                        "warnings": row.get("warnings") or [],
                    }
                )
                for row in low_confidence_items
            ],
        )

    def list_ingestion_logs(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        document_id: str | None = None,
        status: str | None = None,
    ) -> IngestionLogListResponse:
        psycopg, dict_row, _ = self._load_database_dependencies()

        clauses = []
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }

        if document_id:
            clauses.append("document_id = %(document_id)s")
            params["document_id"] = document_id

        if status:
            clauses.append("status = %(status)s")
            params["status"] = status

        where_sql = f"where {' and '.join(clauses)}" if clauses else ""

        sql = f"""
            select
                id,
                created_at,
                run_id::text,
                document_id,
                step,
                status,
                input_path,
                output_path,
                char_count,
                chunk_count,
                page_count,
                warning,
                error_message,
                raw_log
            from rag.ingestion_document_logs
            {where_sql}
            order by created_at desc, id desc
            limit %(limit)s
            offset %(offset)s;
        """

        with get_database_connection(self.settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        return IngestionLogListResponse(
            items=[IngestionLogItem(**row) for row in rows],
            limit=limit,
            offset=offset,
        )

    def _build_chunk_rows(
        self,
        *,
        query_log_id: str,
        response: ChatResponse,
        Jsonb: Any,
    ) -> list[dict[str, Any]]:
        candidate_by_chunk_id = {}
        if response.reranking:
            for candidate in response.reranking.candidates:
                candidate_by_chunk_id[candidate.chunk_id] = candidate

        rows = []
        for index, citation in enumerate(response.citations, start=1):
            candidate = candidate_by_chunk_id.get(citation.chunk_id)
            content_preview = citation.content
            if len(content_preview) > 700:
                content_preview = content_preview[:700].rsplit(" ", 1)[0].rstrip() + "..."

            rows.append(
                {
                    "query_log_id": query_log_id,
                    "citation_id": citation.citation_id,
                    "chunk_id": citation.chunk_id,
                    "document_id": citation.document_id,
                    "document_number": citation.document_number,
                    "document_name": citation.document_name,
                    "document_type": citation.document_type,
                    "article": citation.article,
                    "source_url": citation.source_url,
                    "retrieval_rank": getattr(candidate, "retrieval_rank", index),
                    "rerank_rank": getattr(candidate, "rerank_rank", index),
                    "similarity": getattr(candidate, "similarity", None),
                    "rerank_score": getattr(candidate, "rerank_score", None),
                    "content_preview": content_preview,
                    "metadata": Jsonb(
                        {
                            "hybrid_score": getattr(candidate, "hybrid_score", None),
                            "keyword_rank": getattr(candidate, "keyword_rank", None),
                            "keyword_score": getattr(candidate, "keyword_score", None),
                            "semantic_rank": getattr(candidate, "semantic_rank", None),
                        }
                    ),
                }
            )

        return rows

    @staticmethod
    def _ensure_usage_columns(conn: Any) -> None:
        statements = [
            "alter table rag.query_logs add column if not exists llm_prompt_tokens integer;",
            "alter table rag.query_logs add column if not exists llm_completion_tokens integer;",
            "alter table rag.query_logs add column if not exists llm_total_tokens integer;",
            "alter table rag.query_logs add column if not exists llm_estimated_cost_usd double precision;",
        ]
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)

    @staticmethod
    def _load_database_dependencies() -> tuple[Any, Any, Any]:
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg.types.json import Jsonb
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Missing database dependency. Install project requirements first: "
                "python -m pip install -r requirements.txt"
            ) from exc

        return psycopg, dict_row, Jsonb


def _status_from_response(response: ChatResponse) -> str:
    if response.mode == "blocked":
        return "blocked"
    if response.mode == "rejected":
        return "rejected"
    if response.mode == "clarification_required":
        return "clarification_required"
    if response.mode == "llm_fallback":
        return "llm_fallback"
    return "success"


def _dump_model(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_dump_model(item) for item in value]
    if isinstance(value, dict):
        return {key: _dump_model(item) for key, item in value.items()}
    return value


def _enum_or_value(value: Any) -> Any:
    if value is None:
        return None
    return getattr(value, "value", value)

def _since(days: int) -> datetime:
    safe_days = max(1, min(days, 365))
    return datetime.now(timezone.utc) - timedelta(days=safe_days)
