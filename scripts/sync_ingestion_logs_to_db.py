from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import get_settings

LOG_DIR = PROJECT_ROOT / "data" / "processed"

LOG_FILES = [
    ("document_loader", LOG_DIR / "document_loader_log.csv"),
    ("text_cleaner", LOG_DIR / "text_cleaner_log.csv"),
    ("structure_parser", LOG_DIR / "structure_parser_log.csv"),
    ("chunker", LOG_DIR / "chunker_log.csv"),
    ("metadata_enricher", LOG_DIR / "metadata_enricher_log.csv"),
]


CREATE_RUN_SQL = """
    insert into rag.ingestion_runs (
        run_name,
        status,
        note
    )
    values (
        %(run_name)s,
        'running',
        %(note)s
    )
    returning id;
"""


INSERT_DOCUMENT_LOG_SQL = """
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
        %(run_id)s,
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


FINISH_RUN_SQL = """
    update rag.ingestion_runs
    set
        status = %(status)s,
        finished_at = now(),
        total_documents = %(total_documents)s,
        success_count = %(success_count)s,
        warning_count = %(warning_count)s,
        error_count = %(error_count)s,
        note = %(note)s
    where id = %(run_id)s::uuid;
"""


def main() -> int:
    settings = get_settings()
    psycopg, dict_row, Jsonb = _load_database_dependencies()

    rows = []
    for step, path in LOG_FILES:
        if not path.exists():
            print(f"[SKIP] Missing log file: {path}")
            continue

        rows.extend(_read_log_file(step, path))

    if not rows:
        print("[WARNING] No ingestion logs found.")
        return 0

    success_count = sum(1 for row in rows if row["status"] in {"success", "ok"})
    warning_count = sum(1 for row in rows if row["status"] in {"warning", "empty"})
    error_count = sum(1 for row in rows if row["status"] == "error")

    final_status = "success"
    if error_count:
        final_status = "error"
    elif warning_count:
        final_status = "warning"

    conn = psycopg.connect(**settings.database_kwargs())
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                CREATE_RUN_SQL,
                {
                    "run_name": "sync_existing_csv_logs",
                    "note": "Imported existing offline pipeline CSV logs.",
                },
            )
            run_id = str(cur.fetchone()["id"])

            db_rows = []
            for row in rows:
                db_rows.append(
                    {
                        **row,
                        "run_id": run_id,
                        "raw_log": Jsonb(row["raw_log"]),
                    }
                )

            cur.executemany(INSERT_DOCUMENT_LOG_SQL, db_rows)

            cur.execute(
                FINISH_RUN_SQL,
                {
                    "run_id": run_id,
                    "status": final_status,
                    "total_documents": len(rows),
                    "success_count": success_count,
                    "warning_count": warning_count,
                    "error_count": error_count,
                    "note": (
                        f"Imported {len(rows)} rows from CSV logs. "
                        f"success={success_count}, warning={warning_count}, error={error_count}"
                    ),
                },
            )

        conn.commit()
    finally:
        conn.close()

    print(f"[OK] Synced {len(rows)} ingestion log rows to DB.")
    return 0


def _read_log_file(step: str, path: Path) -> list[dict[str, Any]]:
    output = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for raw_row in reader:
            normalized_status = _normalize_status(raw_row.get("status", ""))
            warning = raw_row.get("warning") or raw_row.get("note") or ""
            error = raw_row.get("error") or raw_row.get("error_message") or ""

            output.append(
                {
                    "document_id": _resolve_document_id(raw_row),
                    "step": step,
                    "status": normalized_status,
                    "input_path": (
                        raw_row.get("input_path")
                        or raw_row.get("local_path")
                        or raw_row.get("file_name")
                        or raw_row.get("input_path")
                    ),
                    "output_path": raw_row.get("output_path"),
                    "char_count": _safe_int(
                        raw_row.get("char_count")
                        or raw_row.get("output_chars")
                        or raw_row.get("total_chars")
                    ),
                    "chunk_count": _safe_int(raw_row.get("chunk_count")),
                    "page_count": _safe_int(raw_row.get("page_count")),
                    "warning": warning or None,
                    "error_message": error or None,
                    "raw_log": dict(raw_row),
                }
            )

    print(f"[OK] Read {len(output)} rows from {path.name}")
    return output


def _resolve_document_id(row: dict[str, str]) -> str | None:
    document_id = row.get("document_id")
    if document_id:
        return document_id.strip()

    file_name = row.get("file_name")
    if file_name:
        return Path(file_name).stem.strip()

    input_path = row.get("input_path")
    if input_path:
        return Path(input_path).stem.strip()

    return None


def _normalize_status(value: str) -> str:
    status = (value or "").strip().lower()

    if status in {"ok", "success"}:
        return "success"
    if status in {"warning", "empty"}:
        return status
    if status in {"error"}:
        return "error"
    if status in {"skipped", "skip"}:
        return "skipped"

    return "warning"


def _safe_int(value: str | int | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


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


if __name__ == "__main__":
    sys.exit(main())