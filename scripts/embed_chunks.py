from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "enriched_chunks" / "all_enriched_chunks.json"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "embeddings"

EMBEDDINGS_NPY_PATH = OUTPUT_DIR / "chunk_embeddings.npy"
CHUNKS_METADATA_PATH = OUTPUT_DIR / "chunks_metadata.json"
EMBEDDING_LOG_PATH = OUTPUT_DIR / "embedding_log.json"

MODEL_NAME = "intfloat/multilingual-e5-base"
BATCH_SIZE = 8


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def project_relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def require_sentence_transformer():
    try:
        from sentence_transformers import SentenceTransformer
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: sentence-transformers. "
            "Install dependencies into the same Python environment you use to run this script.\n"
            "Run:\n"
            "  python -m pip install -r requirements.txt\n"
            "Then run again:\n"
            "  python scripts\\embed_chunks.py"
        ) from exc
    return SentenceTransformer


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def build_embedding_text(chunk: dict[str, Any]) -> str:
    """E5 retrieval models expect document inputs to be prefixed with 'passage:'."""
    text = clean_text(chunk.get("text"))
    metadata = chunk.get("metadata") or {}

    document_type = clean_text(metadata.get("document_type"))
    document_number = clean_text(metadata.get("document_number"))
    document_title = clean_text(
        metadata.get("document_title") or metadata.get("document_name") or metadata.get("title")
    )
    issuing_authority = clean_text(metadata.get("issuing_authority"))
    article = clean_text(metadata.get("article"))
    article_title = clean_text(metadata.get("article_title"))
    paragraph_start = metadata.get("paragraph_start")
    paragraph_end = metadata.get("paragraph_end")

    parts: list[str] = []

    document_line = " ".join(
        part for part in [document_type, document_number, document_title] if part
    )
    if document_line:
        parts.append(f"Văn bản: {document_line}")

    if issuing_authority:
        parts.append(f"Cơ quan ban hành: {issuing_authority}")

    location_line = " ".join(part for part in [article, article_title] if part)
    if location_line:
        parts.append(f"Vị trí: {location_line}")
    elif paragraph_start is not None and paragraph_end is not None:
        parts.append(f"Vị trí: đoạn {paragraph_start}-{paragraph_end}")

    if text:
        parts.append(text)

    content = "\n".join(part for part in parts if part.strip())
    return f"passage: {content}"


def load_chunks(input_path: Path) -> tuple[list[dict[str, Any]], int]:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {project_relative(input_path)}")

    chunks = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(chunks, list):
        raise ValueError("Input JSON must be a list of enriched chunks.")

    nonempty_chunks = [chunk for chunk in chunks if clean_text(chunk.get("text"))]
    skipped_empty_count = len(chunks) - len(nonempty_chunks)
    return nonempty_chunks, skipped_empty_count


def build_chunks_metadata(
    chunks: list[dict[str, Any]],
    embedding_texts: list[str],
) -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "chunk_id": chunk.get("chunk_id"),
            "document_id": chunk.get("document_id"),
            "chunk_type": chunk.get("chunk_type"),
            "text": chunk.get("text"),
            "char_count": chunk.get("char_count"),
            "metadata": chunk.get("metadata") or {},
            "embedding_text": embedding_texts[index],
        }
        for index, chunk in enumerate(chunks)
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Embed enriched tax-law chunks with E5.")
    parser.add_argument(
        "--input-path",
        type=Path,
        default=INPUT_PATH,
        help=f"Input enriched chunks JSON. Default: {project_relative(INPUT_PATH)}.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help=f"Output directory. Default: {project_relative(OUTPUT_DIR)}.",
    )
    parser.add_argument(
        "--model-name",
        default=MODEL_NAME,
        help=f"SentenceTransformer model name. Default: {MODEL_NAME}.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"Embedding batch size. Default: {BATCH_SIZE}.",
    )
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="Load the model from the local Hugging Face cache without network access.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input_path.resolve()
    output_dir = args.output_dir.resolve()
    embeddings_path = output_dir / EMBEDDINGS_NPY_PATH.name
    chunks_metadata_path = output_dir / CHUNKS_METADATA_PATH.name
    embedding_log_path = output_dir / EMBEDDING_LOG_PATH.name

    output_dir.mkdir(parents=True, exist_ok=True)

    chunks, skipped_empty_count = load_chunks(input_path)
    embedding_texts = [build_embedding_text(chunk) for chunk in chunks]

    print(f"Loaded chunks: {len(chunks)}")
    print(f"Skipped empty chunks: {skipped_empty_count}")
    print(f"Embedding model: {args.model_name}")
    print(f"Batch size: {args.batch_size}")

    SentenceTransformer = require_sentence_transformer()
    model = SentenceTransformer(args.model_name, local_files_only=args.local_files_only)

    embeddings = model.encode(
        embedding_texts,
        batch_size=args.batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    embeddings = np.asarray(embeddings, dtype=np.float32)

    np.save(embeddings_path, embeddings)
    chunks_metadata = build_chunks_metadata(chunks, embedding_texts)
    chunks_metadata_path.write_text(
        json.dumps(chunks_metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    log = {
        "model_name": args.model_name,
        "input_path": project_relative(input_path),
        "chunk_count": len(chunks),
        "skipped_empty_count": skipped_empty_count,
        "embedding_shape": list(embeddings.shape),
        "normalized": True,
        "batch_size": args.batch_size,
        "local_files_only": args.local_files_only,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "embeddings_path": project_relative(embeddings_path),
        "chunks_metadata_path": project_relative(chunks_metadata_path),
    }
    embedding_log_path.write_text(
        json.dumps(log, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n===== EMBEDDING SUMMARY =====")
    print(f"Chunks: {len(chunks)}")
    print(f"Embedding shape: {embeddings.shape}")
    print(f"Embeddings: {embeddings_path}")
    print(f"Metadata: {chunks_metadata_path}")
    print(f"Log: {embedding_log_path}")


if __name__ == "__main__":
    main()
