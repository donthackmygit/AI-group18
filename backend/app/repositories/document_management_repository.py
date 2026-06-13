from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

import numpy as np

from backend.app.core.config import Settings


DOCUMENT_COLUMNS = """
    d.document_id,
    d.file_name,
    d.document_title,
    d.document_number,
    d.document_type,
    d.issuing_authority,
    d.issue_date,
    d.effective_date,
    d.expiry_date,
    d.status,
    d.source_url,
    d.local_path,
    d.version,
    d.topics,
    d.notes,
    d.extractor,
    d.page_count,
    d.extracted_char_count,
    d.extracted_preview,
    d.ingestion_status,
    d.ingestion_error,
    d.search_enabled,
    d.chunk_count,
    coalesce(cc.search_chunk_count, 0)::int as search_chunk_count,
    d.last_ingested_at,
    d.metadata,
    d.created_at,
    d.updated_at
"""


class DocumentManagementRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def list_documents(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        psycopg, dict_row, _ = self._load_database_dependencies()
        managed_sql = f"""
            with chunk_counts as (
                select document_id, count(*)::int as search_chunk_count
                from rag.chunks
                group by document_id
            ),
            managed_documents as (
                select
                    {DOCUMENT_COLUMNS}
                from rag.documents as d
                left join chunk_counts as cc
                  on cc.document_id = d.document_id
            ),
            indexed_only_documents as (
                select
                    c.document_id,
                    max(c.local_path) as file_name,
                    coalesce(max(c.document_title), c.document_id) as document_title,
                    max(c.document_number) as document_number,
                    max(c.document_type) as document_type,
                    max(c.issuing_authority) as issuing_authority,
                    max(c.issue_date) as issue_date,
                    max(c.effective_date) as effective_date,
                    max(c.expiry_date) as expiry_date,
                    coalesce(max(c.status), 'effective') as status,
                    max(c.source_url) as source_url,
                    max(c.local_path) as local_path,
                    null::text as version,
                    null::text as topics,
                    null::text as notes,
                    null::text as extractor,
                    null::integer as page_count,
                    0::integer as extracted_char_count,
                    null::text as extracted_preview,
                    'indexed'::text as ingestion_status,
                    null::text as ingestion_error,
                    true as search_enabled,
                    count(*)::int as chunk_count,
                    count(*)::int as search_chunk_count,
                    max(c.created_at) as last_ingested_at,
                    jsonb_build_object('source', 'rag.chunks') as metadata,
                    min(c.created_at) as created_at,
                    max(c.created_at) as updated_at
                from rag.chunks as c
                where not exists (
                    select 1 from rag.documents as d
                    where d.document_id = c.document_id
                )
                group by c.document_id
            )
            select *
            from managed_documents
            union all
            select *
            from indexed_only_documents
            order by updated_at desc nulls last, document_id
            limit %(limit)s
            offset %(offset)s;
        """
        indexed_only_sql = """
            select
                c.document_id,
                max(c.local_path) as file_name,
                coalesce(max(c.document_title), c.document_id) as document_title,
                max(c.document_number) as document_number,
                max(c.document_type) as document_type,
                max(c.issuing_authority) as issuing_authority,
                max(c.issue_date) as issue_date,
                max(c.effective_date) as effective_date,
                max(c.expiry_date) as expiry_date,
                coalesce(max(c.status), 'effective') as status,
                max(c.source_url) as source_url,
                max(c.local_path) as local_path,
                null::text as version,
                null::text as topics,
                null::text as notes,
                null::text as extractor,
                null::integer as page_count,
                0::integer as extracted_char_count,
                null::text as extracted_preview,
                'indexed'::text as ingestion_status,
                null::text as ingestion_error,
                true as search_enabled,
                count(*)::int as chunk_count,
                count(*)::int as search_chunk_count,
                max(c.created_at) as last_ingested_at,
                jsonb_build_object(
                    'source', 'rag.chunks',
                    'missing_documents_table', true
                ) as metadata,
                min(c.created_at) as created_at,
                max(c.created_at) as updated_at
            from rag.chunks as c
            group by c.document_id
            order by updated_at desc nulls last, document_id
            limit %(limit)s
            offset %(offset)s;
        """
        conn = psycopg.connect(**self.settings.database_kwargs())
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                sql = (
                    managed_sql
                    if self._table_exists(conn, "rag.documents")
                    else indexed_only_sql
                )
                cur.execute(sql, {"limit": limit, "offset": offset})
                return list(cur.fetchall())
        finally:
            conn.close()

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        psycopg, dict_row, _ = self._load_database_dependencies()
        managed_sql = f"""
            with chunk_counts as (
                select document_id, count(*)::int as search_chunk_count
                from rag.chunks
                where document_id = %(document_id)s
                group by document_id
            )
            select
                {DOCUMENT_COLUMNS}
            from rag.documents as d
            left join chunk_counts as cc
              on cc.document_id = d.document_id
            where d.document_id = %(document_id)s;
        """
        indexed_only_sql = """
            select
                c.document_id,
                max(c.local_path) as file_name,
                coalesce(max(c.document_title), c.document_id) as document_title,
                max(c.document_number) as document_number,
                max(c.document_type) as document_type,
                max(c.issuing_authority) as issuing_authority,
                max(c.issue_date) as issue_date,
                max(c.effective_date) as effective_date,
                max(c.expiry_date) as expiry_date,
                coalesce(max(c.status), 'effective') as status,
                max(c.source_url) as source_url,
                max(c.local_path) as local_path,
                null::text as version,
                null::text as topics,
                null::text as notes,
                null::text as extractor,
                null::integer as page_count,
                0::integer as extracted_char_count,
                null::text as extracted_preview,
                'indexed'::text as ingestion_status,
                null::text as ingestion_error,
                true as search_enabled,
                count(*)::int as chunk_count,
                count(*)::int as search_chunk_count,
                max(c.created_at) as last_ingested_at,
                jsonb_build_object('source', 'rag.chunks') as metadata,
                min(c.created_at) as created_at,
                max(c.created_at) as updated_at
            from rag.chunks as c
            where c.document_id = %(document_id)s
            group by c.document_id;
        """
        conn = psycopg.connect(**self.settings.database_kwargs())
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                if self._table_exists(conn, "rag.documents"):
                    cur.execute(managed_sql, {"document_id": document_id})
                    row = cur.fetchone()
                    if row is not None:
                        return row

                cur.execute(indexed_only_sql, {"document_id": document_id})
                return cur.fetchone()
        finally:
            conn.close()

    def upsert_document(self, values: dict[str, Any]) -> dict[str, Any]:
        psycopg, dict_row, Jsonb = self._load_database_dependencies()
        params = {
            **values,
            "metadata": Jsonb(values.get("metadata") or {}),
        }
        sql = """
            insert into rag.documents (
                document_id,
                file_name,
                document_title,
                document_number,
                document_type,
                issuing_authority,
                issue_date,
                effective_date,
                expiry_date,
                status,
                source_url,
                local_path,
                version,
                topics,
                notes,
                extractor,
                page_count,
                extracted_char_count,
                extracted_preview,
                ingestion_status,
                ingestion_error,
                search_enabled,
                chunk_count,
                metadata
            )
            values (
                %(document_id)s,
                %(file_name)s,
                %(document_title)s,
                %(document_number)s,
                %(document_type)s,
                %(issuing_authority)s,
                %(issue_date)s,
                %(effective_date)s,
                %(expiry_date)s,
                %(status)s,
                %(source_url)s,
                %(local_path)s,
                %(version)s,
                %(topics)s,
                %(notes)s,
                %(extractor)s,
                %(page_count)s,
                %(extracted_char_count)s,
                %(extracted_preview)s,
                %(ingestion_status)s,
                %(ingestion_error)s,
                %(search_enabled)s,
                %(chunk_count)s,
                %(metadata)s
            )
            on conflict (document_id) do update set
                file_name = excluded.file_name,
                document_title = excluded.document_title,
                document_number = excluded.document_number,
                document_type = excluded.document_type,
                issuing_authority = excluded.issuing_authority,
                issue_date = excluded.issue_date,
                effective_date = excluded.effective_date,
                expiry_date = excluded.expiry_date,
                status = excluded.status,
                source_url = excluded.source_url,
                local_path = excluded.local_path,
                version = excluded.version,
                topics = excluded.topics,
                notes = excluded.notes,
                extractor = excluded.extractor,
                page_count = excluded.page_count,
                extracted_char_count = excluded.extracted_char_count,
                extracted_preview = excluded.extracted_preview,
                ingestion_status = excluded.ingestion_status,
                ingestion_error = excluded.ingestion_error,
                metadata = excluded.metadata,
                updated_at = now()
            returning document_id;
        """
        conn = psycopg.connect(**self.settings.database_kwargs())
        try:
            self._ensure_management_schema(conn)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
            conn.commit()
        finally:
            conn.close()
        document = self.get_document(values["document_id"])
        if document is None:
            raise RuntimeError("Document was not saved.")
        return document

    def update_document(self, document_id: str, values: dict[str, Any]) -> dict[str, Any]:
        if not values:
            document = self.get_document(document_id)
            if document is None:
                raise KeyError(document_id)
            return document

        psycopg, dict_row, Jsonb = self._load_database_dependencies()
        params: dict[str, Any] = {"document_id": document_id}
        assignments = []

        for key, value in values.items():
            if key == "metadata":
                assignments.append("metadata = %(metadata)s")
                params[key] = Jsonb(value or {})
            else:
                assignments.append(f"{key} = %({key})s")
                params[key] = value

        assignments.append("updated_at = now()")
        sql = f"""
            update rag.documents
            set {", ".join(assignments)}
            where document_id = %(document_id)s
            returning document_id;
        """

        conn = psycopg.connect(**self.settings.database_kwargs())
        try:
            self._ensure_management_schema(conn)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()

        if row is None:
            raise KeyError(document_id)

        document = self.get_document(document_id)
        if document is None:
            raise KeyError(document_id)
        return document

    def create_ingestion_run(self, *, document_id: str, run_name: str) -> str:
        psycopg, dict_row, _ = self._load_database_dependencies()
        run_id = str(uuid4())
        sql = """
            insert into rag.ingestion_runs (
                id,
                run_name,
                status,
                total_documents,
                note
            )
            values (
                %(id)s::uuid,
                %(run_name)s,
                'running',
                1,
                %(note)s
            )
            returning id::text;
        """
        conn = psycopg.connect(**self.settings.database_kwargs())
        try:
            self._ensure_management_schema(conn)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    sql,
                    {
                        "id": run_id,
                        "run_name": run_name,
                        "note": f"Document management ingestion for {document_id}",
                    },
                )
                row = cur.fetchone()
            conn.commit()
            return str(row["id"])
        finally:
            conn.close()

    def finish_ingestion_run(
        self,
        *,
        run_id: str,
        status: str,
        success_count: int,
        warning_count: int,
        error_count: int,
        note: str | None = None,
    ) -> None:
        psycopg, _, _ = self._load_database_dependencies()
        sql = """
            update rag.ingestion_runs
            set
                finished_at = now(),
                status = %(status)s,
                success_count = %(success_count)s,
                warning_count = %(warning_count)s,
                error_count = %(error_count)s,
                note = coalesce(%(note)s, note)
            where id = %(run_id)s::uuid;
        """
        conn = psycopg.connect(**self.settings.database_kwargs())
        try:
            self._ensure_management_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    {
                        "run_id": run_id,
                        "status": status,
                        "success_count": success_count,
                        "warning_count": warning_count,
                        "error_count": error_count,
                        "note": note,
                    },
                )
            conn.commit()
        finally:
            conn.close()

    def insert_ingestion_log(
        self,
        *,
        run_id: str | None,
        document_id: str,
        step: str,
        status: str,
        input_path: str | None = None,
        output_path: str | None = None,
        char_count: int | None = None,
        chunk_count: int | None = None,
        page_count: int | None = None,
        warning: str | None = None,
        error_message: str | None = None,
        raw_log: dict[str, Any] | None = None,
    ) -> None:
        psycopg, _, Jsonb = self._load_database_dependencies()
        sql = """
            insert into rag.ingestion_document_logs (
                run_id,
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
            )
            values (
                %(run_id)s::uuid,
                %(document_id)s,
                %(step)s,
                %(status)s,
                %(input_path)s,
                %(output_path)s,
                %(char_count)s,
                %(chunk_count)s,
                %(page_count)s,
                %(warning)s,
                %(error_message)s,
                %(raw_log)s
            );
        """
        conn = psycopg.connect(**self.settings.database_kwargs())
        try:
            self._ensure_management_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    {
                        "run_id": run_id,
                        "document_id": document_id,
                        "step": step,
                        "status": status,
                        "input_path": input_path,
                        "output_path": output_path,
                        "char_count": char_count,
                        "chunk_count": chunk_count,
                        "page_count": page_count,
                        "warning": warning,
                        "error_message": error_message,
                        "raw_log": Jsonb(raw_log or {}),
                    },
                )
            conn.commit()
        finally:
            conn.close()

    def replace_chunks(
        self,
        *,
        document_id: str,
        chunks: list[dict[str, Any]],
        embeddings: np.ndarray,
    ) -> None:
        psycopg, _, Jsonb = self._load_database_dependencies()
        conn = psycopg.connect(**self.settings.database_kwargs())
        try:
            self._register_vector(conn)
            rows = [
                self._chunk_row(chunk, embeddings[index], Jsonb)
                for index, chunk in enumerate(chunks)
            ]
            with conn.cursor() as cur:
                cur.execute(
                    "delete from rag.chunks where document_id = %(document_id)s;",
                    {"document_id": document_id},
                )
                if rows:
                    cur.executemany(
                        """
                        insert into rag.chunks (
                            chunk_id,
                            document_id,
                            chunk_type,
                            content,
                            document_title,
                            document_number,
                            document_type,
                            issuing_authority,
                            issue_date,
                            effective_date,
                            expiry_date,
                            status,
                            source_url,
                            local_path,
                            article,
                            article_number,
                            article_title,
                            chapter,
                            section,
                            paragraph_start,
                            paragraph_end,
                            metadata,
                            embedding
                        )
                        values (
                            %(chunk_id)s,
                            %(document_id)s,
                            %(chunk_type)s,
                            %(content)s,
                            %(document_title)s,
                            %(document_number)s,
                            %(document_type)s,
                            %(issuing_authority)s,
                            %(issue_date)s,
                            %(effective_date)s,
                            %(expiry_date)s,
                            %(status)s,
                            %(source_url)s,
                            %(local_path)s,
                            %(article)s,
                            %(article_number)s,
                            %(article_title)s,
                            %(chapter)s,
                            %(section)s,
                            %(paragraph_start)s,
                            %(paragraph_end)s,
                            %(metadata)s,
                            %(embedding)s
                        );
                        """,
                        rows,
                    )
            conn.commit()
        finally:
            conn.close()

    def update_indexed_document_state(
        self,
        *,
        document_id: str,
        chunk_count: int,
        ingestion_status: str = "indexed",
        ingestion_error: str | None = None,
    ) -> dict[str, Any]:
        return self.update_document(
            document_id,
            {
                "ingestion_status": ingestion_status,
                "ingestion_error": ingestion_error,
                "search_enabled": chunk_count > 0,
                "chunk_count": chunk_count,
                "last_ingested_at": datetime.now(timezone.utc),
            },
        )

    def mark_expired(self, *, document_id: str, expiry_date: date | None) -> dict[str, Any]:
        psycopg, _, _ = self._load_database_dependencies()
        conn = psycopg.connect(**self.settings.database_kwargs())
        try:
            self._ensure_management_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update rag.documents
                    set
                        status = 'expired',
                        expiry_date = coalesce(%(expiry_date)s, expiry_date),
                        updated_at = now()
                    where document_id = %(document_id)s;
                    """,
                    {
                        "document_id": document_id,
                        "expiry_date": expiry_date,
                    },
                )
                cur.execute(
                    """
                    update rag.chunks
                    set
                        status = 'expired',
                        expiry_date = coalesce(%(expiry_date)s, expiry_date)
                    where document_id = %(document_id)s;
                    """,
                    {
                        "document_id": document_id,
                        "expiry_date": expiry_date,
                    },
                )
            conn.commit()
        finally:
            conn.close()

        document = self.get_document(document_id)
        if document is None:
            raise KeyError(document_id)
        return document

    def remove_from_search(self, document_id: str) -> dict[str, Any]:
        psycopg, _, _ = self._load_database_dependencies()
        conn = psycopg.connect(**self.settings.database_kwargs())
        try:
            self._ensure_management_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "delete from rag.chunks where document_id = %(document_id)s;",
                    {"document_id": document_id},
                )
                cur.execute(
                    """
                    update rag.documents
                    set
                        search_enabled = false,
                        chunk_count = 0,
                        ingestion_status = 'removed_from_search',
                        updated_at = now()
                    where document_id = %(document_id)s;
                    """,
                    {"document_id": document_id},
                )
            conn.commit()
        finally:
            conn.close()

        document = self.get_document(document_id)
        if document is None:
            raise KeyError(document_id)
        return document

    def list_chunks(
        self,
        *,
        document_id: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        psycopg, dict_row, _ = self._load_database_dependencies()
        sql = """
            select
                chunk_id,
                document_id,
                chunk_type,
                content,
                document_title,
                document_number,
                document_type,
                article,
                article_number,
                article_title,
                chapter,
                section,
                status,
                source_url,
                metadata,
                created_at
            from rag.chunks
            where document_id = %(document_id)s
            order by
                coalesce((metadata->>'chunk_index')::int, id::int),
                id
            limit %(limit)s
            offset %(offset)s;
        """
        conn = psycopg.connect(**self.settings.database_kwargs())
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    sql,
                    {
                        "document_id": document_id,
                        "limit": limit,
                        "offset": offset,
                    },
                )
                return list(cur.fetchall())
        finally:
            conn.close()

    @staticmethod
    def _chunk_row(chunk: dict[str, Any], embedding: np.ndarray, Jsonb: Any) -> dict[str, Any]:
        metadata = chunk.get("metadata") or {}
        return {
            "chunk_id": chunk.get("chunk_id"),
            "document_id": chunk.get("document_id"),
            "chunk_type": chunk.get("chunk_type"),
            "content": chunk.get("text") or "",
            "document_title": metadata.get("document_title") or metadata.get("document_name"),
            "document_number": metadata.get("document_number"),
            "document_type": metadata.get("document_type"),
            "issuing_authority": metadata.get("issuing_authority"),
            "issue_date": metadata.get("issue_date"),
            "effective_date": metadata.get("effective_date"),
            "expiry_date": metadata.get("expiry_date"),
            "status": metadata.get("status"),
            "source_url": metadata.get("source_url"),
            "local_path": metadata.get("local_path"),
            "article": metadata.get("article"),
            "article_number": metadata.get("article_number"),
            "article_title": metadata.get("article_title"),
            "chapter": metadata.get("chapter"),
            "section": metadata.get("section"),
            "paragraph_start": _int_or_none(metadata.get("paragraph_start")),
            "paragraph_end": _int_or_none(metadata.get("paragraph_end")),
            "metadata": Jsonb(metadata),
            "embedding": np.asarray(embedding, dtype=np.float32),
        }

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

    @staticmethod
    def _register_vector(conn: Any) -> None:
        try:
            from pgvector.psycopg import register_vector
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Missing pgvector dependency. Install project requirements first: "
                "python -m pip install -r requirements.txt"
            ) from exc

        register_vector(conn)

    @staticmethod
    def _table_exists(conn: Any, table_name: str) -> bool:
        with conn.cursor() as cur:
            cur.execute(
                "select to_regclass(%(table_name)s) is not null;",
                {"table_name": table_name},
            )
            row = cur.fetchone()
        return bool(row and row[0])

    @staticmethod
    def _ensure_management_schema(conn: Any) -> None:
        ddl_statements = [
            "create schema if not exists rag;",
            """
            create table if not exists rag.ingestion_runs (
                id uuid primary key,
                created_at timestamptz not null default now(),
                finished_at timestamptz,
                run_name text not null,
                status text not null default 'running'
                    check (status in ('running', 'success', 'warning', 'error')),
                total_documents integer not null default 0,
                success_count integer not null default 0,
                warning_count integer not null default 0,
                error_count integer not null default 0,
                note text
            );
            """,
            """
            create table if not exists rag.ingestion_document_logs (
                id bigserial primary key,
                created_at timestamptz not null default now(),
                run_id uuid
                    references rag.ingestion_runs(id)
                    on delete cascade,
                document_id text,
                step text not null,
                status text not null
                    check (status in ('success', 'warning', 'empty', 'error', 'skipped')),
                input_path text,
                output_path text,
                char_count integer,
                chunk_count integer,
                page_count integer,
                warning text,
                error_message text,
                raw_log jsonb not null default '{}'::jsonb
            );
            """,
            """
            create table if not exists rag.documents (
                document_id text primary key,
                file_name text,
                document_title text,
                document_number text,
                document_type text,
                issuing_authority text,
                issue_date date,
                effective_date date,
                expiry_date date,
                status text not null default 'draft'
                    check (
                        status in (
                            'draft',
                            'effective',
                            'partially_effective',
                            'expired',
                            'superseded'
                        )
                    ),
                source_url text,
                local_path text,
                version text,
                topics text,
                notes text,
                extractor text,
                page_count integer,
                extracted_char_count integer not null default 0,
                extracted_preview text,
                ingestion_status text not null default 'uploaded'
                    check (
                        ingestion_status in (
                            'uploaded',
                            'extracted',
                            'ingesting',
                            'indexed',
                            'error',
                            'removed_from_search'
                        )
                    ),
                ingestion_error text,
                search_enabled boolean not null default false,
                chunk_count integer not null default 0,
                last_ingested_at timestamptz,
                metadata jsonb not null default '{}'::jsonb,
                created_at timestamptz not null default now(),
                updated_at timestamptz not null default now()
            );
            """,
            "create index if not exists ingestion_runs_created_at_idx on rag.ingestion_runs(created_at desc);",
            "create index if not exists ingestion_runs_status_idx on rag.ingestion_runs(status);",
            "create index if not exists ingestion_document_logs_created_at_idx on rag.ingestion_document_logs(created_at desc);",
            "create index if not exists ingestion_document_logs_run_id_idx on rag.ingestion_document_logs(run_id);",
            "create index if not exists ingestion_document_logs_document_id_idx on rag.ingestion_document_logs(document_id);",
            "create index if not exists ingestion_document_logs_status_idx on rag.ingestion_document_logs(status);",
            "create index if not exists ingestion_document_logs_step_idx on rag.ingestion_document_logs(step);",
            "create index if not exists documents_document_number_idx on rag.documents(document_number);",
            "create index if not exists documents_status_idx on rag.documents(status);",
            "create index if not exists documents_ingestion_status_idx on rag.documents(ingestion_status);",
            "create index if not exists documents_search_enabled_idx on rag.documents(search_enabled);",
            "create index if not exists documents_updated_at_idx on rag.documents(updated_at desc);",
            "create index if not exists documents_metadata_gin_idx on rag.documents using gin(metadata);",
            "alter table rag.ingestion_runs disable row level security;",
            "alter table rag.ingestion_document_logs disable row level security;",
            "alter table rag.documents disable row level security;",
        ]

        with conn.cursor() as cur:
            for statement in ddl_statements:
                cur.execute(statement)


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
