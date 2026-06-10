from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REGISTRY_PATH = PROJECT_ROOT / "data" / "metadata" / "document_registry.xlsx"
INPUT_DIR = PROJECT_ROOT / "data" / "processed" / "chunks"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "enriched_chunks"
ALL_OUTPUT_PATH = OUTPUT_DIR / "all_enriched_chunks.json"
LOG_PATH = PROJECT_ROOT / "data" / "processed" / "metadata_enricher_log.csv"

REGISTRY_FIELDS = [
    "document_id",
    "file_name",
    "title",
    "document_number",
    "document_type",
    "issuing_authority",
    "issue_date",
    "effective_date",
    "expiry_date",
    "status",
    "source_type",
    "source_url",
    "local_path",
    "download_date",
    "topics",
    "version",
    "notes",
]

REQUIRED_REGISTRY_FIELDS = [
    "document_id",
    "title",
    "document_number",
    "document_type",
    "issuing_authority",
    "issue_date",
    "effective_date",
    "status",
    "source_url",
    "local_path",
]

DOCUMENT_LEVEL_KEYS = set(REGISTRY_FIELDS) | {
    "document_name",
    "document_title",
}


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def project_relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and not value.strip()


def normalize_value(value: Any) -> Any:
    if is_missing(value):
        return None

    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.date().isoformat()

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, float) and value.is_integer():
        return int(value)

    if isinstance(value, str):
        return value.strip() or None

    return value


def load_document_registry(registry_path: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if not registry_path.exists():
        raise FileNotFoundError(f"Registry file not found: {project_relative(registry_path)}")

    df = pd.read_excel(registry_path)
    missing_columns = [field for field in REQUIRED_REGISTRY_FIELDS if field not in df.columns]
    if missing_columns:
        raise ValueError(
            "document_registry.xlsx is missing required columns: "
            + ", ".join(missing_columns)
        )

    registry: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []

    for _, row in df.iterrows():
        document_id = normalize_value(row.get("document_id"))
        if not document_id:
            continue

        document_id = str(document_id)
        if document_id in registry:
            duplicates.append(document_id)

        metadata = {
            field: normalize_value(row.get(field)) if field in df.columns else None
            for field in REGISTRY_FIELDS
        }
        registry[document_id] = metadata

    return registry, sorted(set(duplicates))


def registry_or_existing(
    field: str,
    registry_metadata: dict[str, Any],
    existing_metadata: dict[str, Any],
) -> Any:
    value = registry_metadata.get(field)
    if value is not None:
        return value
    return normalize_value(existing_metadata.get(field))


def build_document_metadata(
    chunk: dict[str, Any],
    registry_metadata: dict[str, Any],
) -> dict[str, Any]:
    existing_metadata = chunk.get("metadata") or {}
    document_id = (
        normalize_value(chunk.get("document_id"))
        or registry_metadata.get("document_id")
        or normalize_value(existing_metadata.get("document_id"))
    )

    metadata: dict[str, Any] = {"document_id": document_id}
    for field in REGISTRY_FIELDS:
        if field == "document_id":
            continue
        metadata[field] = registry_or_existing(field, registry_metadata, existing_metadata)

    title = (
        registry_or_existing("title", registry_metadata, existing_metadata)
        or normalize_value(existing_metadata.get("document_title"))
        or normalize_value(existing_metadata.get("document_name"))
    )
    metadata["title"] = title
    metadata["document_title"] = title
    metadata["document_name"] = title

    # Preserve chunk-level structure while keeping document-level fields canonical.
    for key, value in existing_metadata.items():
        if key in DOCUMENT_LEVEL_KEYS:
            continue
        metadata[key] = normalize_value(value)

    if not metadata.get("source_structure"):
        metadata["source_structure"] = chunk.get("chunk_type")

    return metadata


def enrich_chunk(chunk: dict[str, Any], registry_metadata: dict[str, Any]) -> dict[str, Any]:
    enriched_chunk = dict(chunk)
    enriched_chunk["metadata"] = build_document_metadata(chunk, registry_metadata)
    enriched_chunk["embedding_text"] = normalize_value(chunk.get("text")) or ""
    return enriched_chunk


def load_chunks(input_file: Path) -> list[dict[str, Any]]:
    data = json.loads(input_file.read_text(encoding="utf-8"))
    chunks = data.get("chunks", [])
    if not isinstance(chunks, list):
        raise ValueError("Input chunks payload must contain a list at key 'chunks'")
    return chunks


def missing_required_metadata(metadata: dict[str, Any]) -> list[str]:
    required_output_fields = [
        "document_id",
        "document_title",
        "document_number",
        "document_type",
        "issuing_authority",
        "issue_date",
        "effective_date",
        "status",
        "source_url",
        "local_path",
    ]
    return [field for field in required_output_fields if is_missing(metadata.get(field))]


def write_log(log_rows: list[dict[str, Any]], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "document_id",
        "input_path",
        "output_path",
        "chunk_count",
        "registry_status",
        "missing_required_fields",
        "duplicate_chunk_ids",
        "status",
        "note",
    ]
    with log_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(log_rows)


def process_file(
    input_file: Path,
    output_dir: Path,
    registry_path: Path,
    registry: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    document_id = input_file.name.removesuffix("_chunks.json")
    registry_metadata = registry.get(document_id, {})
    registry_status = "OK" if registry_metadata else "MISSING_REGISTRY_METADATA"

    chunks = load_chunks(input_file)
    enriched_chunks = [enrich_chunk(chunk, registry_metadata) for chunk in chunks]

    missing_fields = sorted(
        {
            field
            for chunk in enriched_chunks[:1]
            for field in missing_required_metadata(chunk.get("metadata") or {})
        }
    )
    duplicate_chunk_ids = sorted(
        chunk_id
        for chunk_id, count in Counter(chunk.get("chunk_id") for chunk in enriched_chunks).items()
        if chunk_id and count > 1
    )

    status = "OK"
    notes: list[str] = []
    if registry_status != "OK":
        status = "WARNING"
        notes.append("document_id not found in document_registry.xlsx")
    if missing_fields:
        status = "WARNING"
        notes.append("missing required metadata fields")
    if duplicate_chunk_ids:
        status = "WARNING"
        notes.append("duplicate chunk_id values")

    output_file = output_dir / f"{document_id}_enriched_chunks.json"
    output_data = {
        "document_id": document_id,
        "source_file": project_relative(input_file),
        "registry_file": project_relative(registry_path),
        "enriched_at": datetime.now().isoformat(timespec="seconds"),
        "chunk_count": len(enriched_chunks),
        "registry_status": registry_status,
        "chunks": enriched_chunks,
    }
    output_file.write_text(
        json.dumps(output_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    log_row = {
        "document_id": document_id,
        "input_path": project_relative(input_file),
        "output_path": project_relative(output_file),
        "chunk_count": len(enriched_chunks),
        "registry_status": registry_status,
        "missing_required_fields": ";".join(missing_fields),
        "duplicate_chunk_ids": ";".join(duplicate_chunk_ids),
        "status": status,
        "note": "; ".join(notes),
    }

    return enriched_chunks, log_row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich chunk metadata for RAG ingestion.")
    parser.add_argument(
        "--registry-path",
        type=Path,
        default=REGISTRY_PATH,
        help=f"Path to document registry. Default: {project_relative(REGISTRY_PATH)}.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=INPUT_DIR,
        help=f"Directory containing *_chunks.json files. Default: {project_relative(INPUT_DIR)}.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help=f"Directory for enriched chunk files. Default: {project_relative(OUTPUT_DIR)}.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=LOG_PATH,
        help=f"CSV log path. Default: {project_relative(LOG_PATH)}.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry_path = args.registry_path.resolve()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    log_path = args.log_path.resolve()
    all_output_path = output_dir / ALL_OUTPUT_PATH.name

    output_dir.mkdir(parents=True, exist_ok=True)
    registry, duplicate_registry_ids = load_document_registry(registry_path)

    input_files = sorted(input_dir.glob("*_chunks.json"))
    if not input_files:
        raise FileNotFoundError(f"No *_chunks.json files found in {project_relative(input_dir)}")

    all_enriched_chunks: list[dict[str, Any]] = []
    log_rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}

    for input_file in input_files:
        document_id = input_file.name.removesuffix("_chunks.json")
        try:
            enriched_chunks, log_row = process_file(input_file, output_dir, registry_path, registry)
            all_enriched_chunks.extend(enriched_chunks)
            log_rows.append(log_row)
            status_counts[log_row["status"]] = status_counts.get(log_row["status"], 0) + 1
            print(f"[{log_row['status']}] {document_id}: {len(enriched_chunks)} chunks")
        except Exception as exc:
            status_counts["ERROR"] = status_counts.get("ERROR", 0) + 1
            log_rows.append(
                {
                    "document_id": document_id,
                    "input_path": project_relative(input_file),
                    "output_path": "",
                    "chunk_count": 0,
                    "registry_status": "",
                    "missing_required_fields": "",
                    "duplicate_chunk_ids": "",
                    "status": "ERROR",
                    "note": str(exc),
                }
            )
            print(f"[ERROR] {document_id}: {exc}")

    all_output_path.write_text(
        json.dumps(all_enriched_chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_log(log_rows, log_path)

    print("\n===== METADATA ENRICHMENT SUMMARY =====")
    print(f"Documents: {len(input_files)}")
    print(f"Registry rows: {len(registry)}")
    print(f"Duplicate registry IDs: {len(duplicate_registry_ids)}")
    print(f"Total chunks: {len(all_enriched_chunks)}")
    for status, count in sorted(status_counts.items()):
        print(f"{status}: {count}")
    print(f"Output: {output_dir}")
    print(f"All chunks: {all_output_path}")
    print(f"Log: {log_path}")


if __name__ == "__main__":
    main()
