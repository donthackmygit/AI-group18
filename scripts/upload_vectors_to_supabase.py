from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]

EMBEDDING_DIR = PROJECT_ROOT / "data" / "processed" / "embeddings"
EMBEDDINGS_PATH = EMBEDDING_DIR / "chunk_embeddings.npy"
METADATA_PATH = EMBEDDING_DIR / "chunks_metadata.json"
UPLOAD_LOG_PATH = EMBEDDING_DIR / "supabase_upload_log.json"
ENV_PATH = PROJECT_ROOT / ".env"

VECTOR_DIMENSION = 768
DEFAULT_BATCH_SIZE = 100
TABLE_NAME = "rag.chunks"


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


UPSERT_SQL = """
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
)
on conflict (chunk_id) do update set
    document_id = excluded.document_id,
    chunk_type = excluded.chunk_type,
    content = excluded.content,
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
    article = excluded.article,
    article_number = excluded.article_number,
    article_title = excluded.article_title,
    chapter = excluded.chapter,
    section = excluded.section,
    paragraph_start = excluded.paragraph_start,
    paragraph_end = excluded.paragraph_end,
    metadata = excluded.metadata,
    embedding = excluded.embedding;
"""


def project_relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def clean_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = clean_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def require_runtime_dependency(package_name: str, install_name: str | None = None) -> Any:
    try:
        return __import__(package_name)
    except ModuleNotFoundError as exc:
        name = install_name or package_name
        raise SystemExit(
            f"Missing dependency: {name}. Install dependencies into the same Python "
            "environment you use to run this script.\n"
            "Run:\n"
            "  python -m pip install -r requirements.txt"
        ) from exc


def load_environment() -> dict[str, str]:
    dotenv = require_runtime_dependency("dotenv", "python-dotenv")
    dotenv.load_dotenv(ENV_PATH)

    import os

    env = {
        "host": os.getenv("SUPABASE_DB_HOST", "").strip(),
        "port": os.getenv("SUPABASE_DB_PORT", "5432").strip(),
        "dbname": os.getenv("SUPABASE_DB_NAME", "postgres").strip(),
        "user": os.getenv("SUPABASE_DB_USER", "").strip(),
        "password": os.getenv("SUPABASE_DB_PASSWORD", "").strip(),
        "sslmode": os.getenv("SUPABASE_DB_SSLMODE", "require").strip() or "require",
    }

    missing = [
        env_name
        for env_name, key in [
            ("SUPABASE_DB_HOST", "host"),
            ("SUPABASE_DB_PORT", "port"),
            ("SUPABASE_DB_NAME", "dbname"),
            ("SUPABASE_DB_USER", "user"),
            ("SUPABASE_DB_PASSWORD", "password"),
        ]
        if not env[key]
    ]
    if missing:
        missing_text = ", ".join(missing)
        raise SystemExit(
            f"Missing Supabase database environment values in {project_relative(ENV_PATH)}: "
            f"{missing_text}"
        )

    return env


def connect_database(env: dict[str, str]) -> Any:
    psycopg = require_runtime_dependency("psycopg", "psycopg[binary]")
    try:
        from pgvector.psycopg import register_vector
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: pgvector. Run:\n"
            "  python -m pip install -r requirements.txt"
        ) from exc

    conn = psycopg.connect(
        host=env["host"],
        port=int(env["port"]),
        dbname=env["dbname"],
        user=env["user"],
        password=env["password"],
        sslmode=env["sslmode"],
    )
    register_vector(conn)
    return conn


def load_payload(
    embeddings_path: Path,
    metadata_path: Path,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    if not embeddings_path.exists():
        raise FileNotFoundError(f"Missing embeddings file: {project_relative(embeddings_path)}")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing chunks metadata file: {project_relative(metadata_path)}")

    embeddings = np.load(embeddings_path)
    chunks = json.loads(metadata_path.read_text(encoding="utf-8"))

    if not isinstance(chunks, list):
        raise ValueError("Chunks metadata JSON must be a list.")
    if embeddings.ndim != 2:
        raise ValueError(f"Embeddings must be a 2D array. Got shape: {embeddings.shape}")
    if embeddings.shape[1] != VECTOR_DIMENSION:
        raise ValueError(
            f"Embedding dimension must be {VECTOR_DIMENSION}. Got shape: {embeddings.shape}"
        )
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"Embedding count ({len(embeddings)}) does not match chunk count ({len(chunks)})."
        )

    return embeddings, chunks


def build_row(chunk: dict[str, Any], embedding: np.ndarray) -> dict[str, Any]:
    metadata = dict(chunk.get("metadata") or {})
    chunk_id = clean_text(chunk.get("chunk_id"))
    content = clean_text(chunk.get("text"))

    if not chunk_id:
        raise ValueError("Chunk is missing chunk_id.")
    if not content:
        raise ValueError(f"Chunk {chunk_id} is missing text content.")

    metadata_for_storage = dict(metadata)
    metadata_for_storage["chunk_id"] = chunk_id
    metadata_for_storage["chunk_type"] = clean_text(chunk.get("chunk_type"))
    metadata_for_storage["char_count"] = chunk.get("char_count")

    return {
        "chunk_id": chunk_id,
        "document_id": clean_text(chunk.get("document_id") or metadata.get("document_id")),
        "chunk_type": clean_text(chunk.get("chunk_type")),
        "content": content,
        "document_title": clean_text(
            metadata.get("document_title") or metadata.get("document_name") or metadata.get("title")
        ),
        "document_number": clean_text(metadata.get("document_number")),
        "document_type": clean_text(metadata.get("document_type")),
        "issuing_authority": clean_text(metadata.get("issuing_authority")),
        "issue_date": parse_date(metadata.get("issue_date")),
        "effective_date": parse_date(metadata.get("effective_date")),
        "expiry_date": parse_date(metadata.get("expiry_date")),
        "status": clean_text(metadata.get("status")),
        "source_url": clean_text(metadata.get("source_url")),
        "local_path": clean_text(metadata.get("local_path")),
        "article": clean_text(metadata.get("article")),
        "article_number": clean_text(metadata.get("article_number")),
        "article_title": clean_text(metadata.get("article_title")),
        "chapter": clean_text(metadata.get("chapter")),
        "section": clean_text(metadata.get("section")),
        "paragraph_start": parse_int(metadata.get("paragraph_start")),
        "paragraph_end": parse_int(metadata.get("paragraph_end")),
        "metadata": metadata_for_storage,
        "embedding": np.asarray(embedding, dtype=np.float32).tolist(),
    }


def build_rows(chunks: list[dict[str, Any]], embeddings: np.ndarray) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()
    duplicate_ids: list[str] = []

    for index, chunk in enumerate(chunks):
        row = build_row(chunk, embeddings[index])
        if row["chunk_id"] in seen_chunk_ids:
            duplicate_ids.append(row["chunk_id"])
        seen_chunk_ids.add(row["chunk_id"])
        rows.append(row)

    if duplicate_ids:
        preview = ", ".join(duplicate_ids[:5])
        raise ValueError(f"Duplicate chunk_id values detected: {preview}")

    return rows


def prepare_db_row(row: dict[str, Any], jsonb_factory: Any) -> dict[str, Any]:
    db_row = dict(row)
    db_row["metadata"] = jsonb_factory(row["metadata"])
    return db_row


def get_progress(iterable: Any, **kwargs: Any) -> Any:
    try:
        from tqdm import tqdm
    except ModuleNotFoundError:
        return iterable
    return tqdm(iterable, **kwargs)


def upload_rows(rows: list[dict[str, Any]], batch_size: int, env: dict[str, str]) -> None:
    require_runtime_dependency("psycopg", "psycopg[binary]")
    from psycopg.types.json import Jsonb

    conn = connect_database(env)
    try:
        batch_starts = range(0, len(rows), batch_size)
        for start in get_progress(batch_starts, desc="Uploading batches", unit="batch"):
            batch = rows[start : start + batch_size]
            db_batch = [prepare_db_row(row, Jsonb) for row in batch]
            with conn.cursor() as cur:
                cur.executemany(UPSERT_SQL, db_batch)
            conn.commit()
    finally:
        conn.close()


def write_upload_log(
    rows: list[dict[str, Any]],
    embeddings_shape: tuple[int, int],
    embeddings_path: Path,
    metadata_path: Path,
    batch_size: int,
) -> None:
    log = {
        "table": TABLE_NAME,
        "uploaded_count": len(rows),
        "embedding_shape": list(embeddings_shape),
        "embedding_dimension": embeddings_shape[1],
        "batch_size": batch_size,
        "embeddings_path": project_relative(embeddings_path),
        "chunks_metadata_path": project_relative(metadata_path),
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
    }
    UPLOAD_LOG_PATH.write_text(
        json.dumps(log, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def print_summary(rows: list[dict[str, Any]], embeddings_shape: tuple[int, int]) -> None:
    print("\n===== VECTOR DB PAYLOAD SUMMARY =====")
    print(f"Rows: {len(rows)}")
    print(f"Embedding shape: {embeddings_shape}")
    print(f"Target table: {TABLE_NAME}")
    if rows:
        sample = rows[0]
        print(f"Sample chunk_id: {sample['chunk_id']}")
        print(f"Sample document_id: {sample['document_id'] or ''}")
        print(f"Sample document_number: {sample['document_number'] or ''}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload embedded tax-law chunks into Supabase PostgreSQL with pgvector."
    )
    parser.add_argument(
        "--embeddings-path",
        type=Path,
        default=EMBEDDINGS_PATH,
        help=f"Embeddings .npy path. Default: {project_relative(EMBEDDINGS_PATH)}.",
    )
    parser.add_argument(
        "--metadata-path",
        type=Path,
        default=METADATA_PATH,
        help=f"Chunks metadata JSON path. Default: {project_relative(METADATA_PATH)}.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Upload batch size. Default: {DEFAULT_BATCH_SIZE}.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate local embeddings/chunks without connecting to Supabase.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    embeddings_path = args.embeddings_path.resolve()
    metadata_path = args.metadata_path.resolve()

    embeddings, chunks = load_payload(embeddings_path, metadata_path)
    rows = build_rows(chunks, embeddings)

    print_summary(rows, embeddings.shape)

    if args.dry_run:
        print("\nDry run complete. No Supabase connection was opened.")
        return

    env = load_environment()
    upload_rows(rows, args.batch_size, env)
    write_upload_log(rows, embeddings.shape, embeddings_path, metadata_path, args.batch_size)

    print("\n===== SUPABASE UPLOAD SUMMARY =====")
    print(f"Uploaded/upserted rows: {len(rows)}")
    print(f"Log: {UPLOAD_LOG_PATH}")


if __name__ == "__main__":
    main()
