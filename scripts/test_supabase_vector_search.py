from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
CACHE_DIR = PROJECT_ROOT / ".cache"

MODEL_NAME = "intfloat/multilingual-e5-base"
DEFAULT_QUERY = "Mức giảm trừ gia cảnh cho bản thân và người phụ thuộc là bao nhiêu?"


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def project_relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def require_sentence_transformer() -> Any:
    configure_model_cache()
    try:
        from sentence_transformers import SentenceTransformer
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: sentence-transformers. Run:\n"
            "  python -m pip install -r requirements.txt"
        ) from exc
    return SentenceTransformer


def configure_model_cache() -> None:
    import os

    hf_home = CACHE_DIR / "huggingface"
    sentence_transformers_home = CACHE_DIR / "sentence_transformers"

    os.environ.setdefault("HF_HOME", str(hf_home))
    os.environ.setdefault("HF_HUB_CACHE", str(hf_home / "hub"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_home / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(hf_home / "transformers"))
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(sentence_transformers_home))


def require_runtime_dependency(package_name: str, install_name: str | None = None) -> Any:
    try:
        return __import__(package_name)
    except ModuleNotFoundError as exc:
        name = install_name or package_name
        raise SystemExit(
            f"Missing dependency: {name}. Run:\n"
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


def encode_query(query: str, model_name: str, local_files_only: bool) -> np.ndarray:
    SentenceTransformer = require_sentence_transformer()
    model = SentenceTransformer(model_name, local_files_only=local_files_only)
    embedding = model.encode([f"query: {query}"], normalize_embeddings=True)[0]
    return np.asarray(embedding, dtype=np.float32)


def search_supabase(query_embedding: np.ndarray, top_k: int, env: dict[str, str]) -> list[dict[str, Any]]:
    require_runtime_dependency("psycopg", "psycopg[binary]")
    from psycopg.rows import dict_row

    sql = """
        select
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
            1 - (c.embedding OPERATOR(public.<=>) %s) as similarity
        from rag.chunks as c
        where c.embedding is not null
        order by c.embedding OPERATOR(public.<=>) %s
        limit %s;
    """

    conn = connect_database(env)
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (query_embedding, query_embedding, top_k))
            return list(cur.fetchall())
    finally:
        conn.close()


def format_article(row: dict[str, Any]) -> str:
    parts = [row.get("article"), row.get("article_title")]
    return " - ".join(str(part) for part in parts if part)


def print_results(query: str, rows: list[dict[str, Any]]) -> None:
    print(f"\nQUERY: {query}\n")
    if not rows:
        print("No results returned.")
        return

    for rank, row in enumerate(rows, start=1):
        print("=" * 80)
        print(f"Rank {rank} | Similarity: {float(row['similarity']):.4f}")
        print(f"Chunk ID: {row.get('chunk_id')}")
        print(f"Document: {row.get('document_number') or ''} - {row.get('document_title') or ''}")
        print(f"Type: {row.get('document_type') or ''}")
        article = format_article(row)
        if article:
            print(f"Article: {article}")
        elif row.get("paragraph_start") is not None:
            print(f"Paragraphs: {row.get('paragraph_start')}-{row.get('paragraph_end')}")
        if row.get("source_url"):
            print(f"Source: {row.get('source_url')}")
        print("-" * 80)
        print((row.get("content") or "")[:1000])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test semantic search against Supabase pgvector."
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=DEFAULT_QUERY,
        help="Vietnamese tax question to search for.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Number of matches to return.")
    parser.add_argument(
        "--model-name",
        default=MODEL_NAME,
        help=f"SentenceTransformer model name. Default: {MODEL_NAME}.",
    )
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="Load the model from the local Hugging Face cache without network access.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = load_environment()
    query_embedding = encode_query(args.query, args.model_name, args.local_files_only)
    rows = search_supabase(query_embedding, args.top_k, env)
    print_results(args.query, rows)


if __name__ == "__main__":
    main()
