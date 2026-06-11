from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np

from backend.app.core.config import Settings


SEARCH_SQL = """
    select
        c.chunk_id,
        c.document_id,
        c.chunk_type,
        c.content,
        c.document_title,
        c.document_number,
        c.document_type,
        c.issuing_authority,
        c.issue_date,
        c.effective_date,
        c.expiry_date,
        c.status,
        c.source_url,
        c.local_path,
        c.article,
        c.article_number,
        c.article_title,
        c.chapter,
        c.section,
        c.paragraph_start,
        c.paragraph_end,
        c.metadata,
        1 - (c.embedding OPERATOR(public.<=>) %(query_embedding)s) as similarity
    from rag.chunks as c
    where
        c.embedding is not null
        and (%(status)s::text is null or c.status = %(status)s::text)
        and (
            %(effective_date)s::date is null
            or c.effective_date is null
            or c.effective_date <= %(effective_date)s::date
        )
        and (
            %(effective_date)s::date is null
            or c.expiry_date is null
            or c.expiry_date >= %(effective_date)s::date
        )
        and (%(filter_metadata)s::jsonb = '{}'::jsonb or c.metadata @> %(filter_metadata)s::jsonb)
    order by c.embedding OPERATOR(public.<=>) %(query_embedding)s
    limit %(top_k)s;
"""


PERSONAL_DEDUCTION_SQL = """
    select
        c.chunk_id,
        c.document_id,
        c.chunk_type,
        c.content,
        c.document_title,
        c.document_number,
        c.document_type,
        c.issuing_authority,
        c.issue_date,
        c.effective_date,
        c.expiry_date,
        c.status,
        c.source_url,
        c.local_path,
        c.article,
        c.article_number,
        c.article_title,
        c.chapter,
        c.section,
        c.paragraph_start,
        c.paragraph_end,
        c.metadata,
        1.0::double precision as similarity
    from rag.chunks as c
    where
        (
            c.content ilike '%%giảm trừ gia cảnh%%'
            or c.article_title ilike '%%giảm trừ gia cảnh%%'
            or c.document_title ilike '%%giảm trừ gia cảnh%%'
            or c.content ilike '%%mức giảm trừ đối với%%'
            or c.content ilike '%%người phụ thuộc%%'
            or c.metadata::text ilike '%%giảm trừ gia cảnh%%'
        )
        and (%(status)s::text is null or c.status = %(status)s::text)
        and (
            %(effective_date)s::date is null
            or c.effective_date is null
            or c.effective_date <= %(effective_date)s::date
        )
        and (
            %(effective_date)s::date is null
            or c.expiry_date is null
            or c.expiry_date >= %(effective_date)s::date
        )
    order by
        case
            when c.status = 'effective' then 0
            else 1
        end,
        case
            when c.article_title ilike '%%giảm trừ gia cảnh%%' then 0
            when c.article ilike '%%Điều 10%%' then 1
            when c.article ilike '%%Điều 1%%' then 2
            else 3
        end,
        coalesce(c.effective_date, c.issue_date, date '1900-01-01') desc,
        case
            when c.document_type ilike '%%luật%%' then 0
            when c.document_type ilike '%%nghị quyết%%' then 1
            when c.document_type ilike '%%thông tư%%' then 2
            else 3
        end,
        c.chunk_id
    limit %(top_k)s;
"""


class RagChunkRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int,
        filter_metadata: dict[str, Any] | None = None,
        status: str | None = None,
        effective_date: date | None = None,
    ) -> list[dict[str, Any]]:
        psycopg, dict_row, Jsonb = self._load_database_dependencies()

        params = {
            "query_embedding": np.asarray(query_embedding, dtype=np.float32),
            "top_k": top_k,
            "filter_metadata": Jsonb(filter_metadata or {}),
            "status": status,
            "effective_date": effective_date,
        }

        try:
            conn = psycopg.connect(**self.settings.database_kwargs())
        except Exception as exc:
            raise RuntimeError(
                "Could not connect to Supabase PostgreSQL. Check network access and database settings."
            ) from exc

        try:
            self._register_vector(conn)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(SEARCH_SQL, params)
                return list(cur.fetchall())
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("Supabase vector search failed.") from exc
        finally:
            conn.close()

    def search_personal_deduction(
        self,
        top_k: int,
        status: str | None = None,
        effective_date: date | None = None,
    ) -> list[dict[str, Any]]:
        psycopg, dict_row, _ = self._load_database_dependencies()

        params = {
            "top_k": top_k,
            "status": status,
            "effective_date": effective_date,
        }

        try:
            conn = psycopg.connect(**self.settings.database_kwargs())
        except Exception as exc:
            raise RuntimeError(
                "Could not connect to Supabase PostgreSQL. Check network access and database settings."
            ) from exc

        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(PERSONAL_DEDUCTION_SQL, params)
                return list(cur.fetchall())
        except Exception as exc:
            raise RuntimeError("Supabase personal deduction lookup failed.") from exc
        finally:
            conn.close()

    @staticmethod
    def _load_database_dependencies() -> tuple[Any, Any, Any]:
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg.types.json import Jsonb
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Missing database dependency. Install project requirements before running retrieval: "
                "python -m pip install -r requirements.txt"
            ) from exc

        return psycopg, dict_row, Jsonb

    @staticmethod
    def _register_vector(conn: Any) -> None:
        try:
            from pgvector.psycopg import register_vector
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Missing pgvector dependency. Install project requirements before running retrieval: "
                "python -m pip install -r requirements.txt"
            ) from exc

        register_vector(conn)