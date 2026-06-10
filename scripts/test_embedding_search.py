from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]

EMBEDDING_DIR = PROJECT_ROOT / "data" / "processed" / "embeddings"
EMBEDDINGS_PATH = EMBEDDING_DIR / "chunk_embeddings.npy"
METADATA_PATH = EMBEDDING_DIR / "chunks_metadata.json"

MODEL_NAME = "intfloat/multilingual-e5-base"

DEFAULT_QUERIES = [
    "Mức giảm trừ gia cảnh cho bản thân và người phụ thuộc là bao nhiêu?",
    "Thu nhập từ tiền lương tiền công chịu thuế như thế nào?",
    "Cá nhân cư trú được xác định theo điều kiện nào?",
    "Quyết toán thuế thu nhập cá nhân trong trường hợp có thu nhập hai nơi",
]


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


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
            "  python scripts\\test_embedding_search.py"
        ) from exc
    return SentenceTransformer


def load_index(
    embeddings_path: Path,
    metadata_path: Path,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    if not embeddings_path.exists():
        raise FileNotFoundError(f"Missing embeddings file: {embeddings_path}")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing metadata file: {metadata_path}")

    embeddings = np.load(embeddings_path)
    chunks = json.loads(metadata_path.read_text(encoding="utf-8"))

    if len(embeddings) != len(chunks):
        raise ValueError(
            f"Embedding count ({len(embeddings)}) does not match metadata count ({len(chunks)})."
        )

    return embeddings, chunks


def format_source(metadata: dict[str, Any]) -> str:
    document_number = metadata.get("document_number") or ""
    document_title = metadata.get("document_title") or metadata.get("title") or ""
    return " - ".join(part for part in [document_number, document_title] if part)


def search(
    query: str,
    embeddings: np.ndarray,
    chunks: list[dict[str, Any]],
    model: Any,
    top_k: int,
) -> None:
    query_embedding = model.encode(
        [f"query: {query}"],
        normalize_embeddings=True,
    )[0]
    query_embedding = np.asarray(query_embedding, dtype=np.float32)

    scores = embeddings @ query_embedding
    top_indices = np.argsort(scores)[::-1][:top_k]

    print(f"\nQUERY: {query}\n")

    for rank, index in enumerate(top_indices, start=1):
        chunk = chunks[int(index)]
        metadata = chunk.get("metadata") or {}
        article = " - ".join(
            part
            for part in [metadata.get("article"), metadata.get("article_title")]
            if part
        )

        print("=" * 80)
        print(f"Rank {rank} | Score: {scores[index]:.4f}")
        print(f"Chunk ID: {chunk.get('chunk_id')}")
        print(f"Document: {format_source(metadata)}")
        print(f"Type: {metadata.get('document_type') or ''}")
        if article:
            print(f"Article: {article}")
        elif metadata.get("paragraph_start") is not None:
            print(f"Paragraphs: {metadata.get('paragraph_start')}-{metadata.get('paragraph_end')}")
        print("-" * 80)
        print((chunk.get("text") or "")[:1000])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quick semantic-search smoke test for E5 embeddings.")
    parser.add_argument(
        "queries",
        nargs="*",
        help="Optional query or queries. Defaults to four tax QA smoke tests.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Number of results per query.")
    parser.add_argument(
        "--model-name",
        default=MODEL_NAME,
        help=f"SentenceTransformer model name. Default: {MODEL_NAME}.",
    )
    parser.add_argument(
        "--embeddings-path",
        type=Path,
        default=EMBEDDINGS_PATH,
        help=f"Embeddings .npy path. Default: {EMBEDDINGS_PATH}.",
    )
    parser.add_argument(
        "--metadata-path",
        type=Path,
        default=METADATA_PATH,
        help=f"Chunks metadata JSON path. Default: {METADATA_PATH}.",
    )
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="Allow downloading the model if it is not already in the local Hugging Face cache.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    queries = args.queries or DEFAULT_QUERIES

    embeddings, chunks = load_index(args.embeddings_path, args.metadata_path)
    SentenceTransformer = require_sentence_transformer()
    model = SentenceTransformer(args.model_name, local_files_only=not args.allow_download)

    print(f"Loaded embeddings: {embeddings.shape}")
    print(f"Loaded chunks: {len(chunks)}")
    print(f"Model: {args.model_name}")

    for query in queries:
        search(query, embeddings, chunks, model, top_k=args.top_k)


if __name__ == "__main__":
    main()
