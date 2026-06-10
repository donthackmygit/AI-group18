from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from docx import Document
from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.ERROR)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import fitz  # type: ignore
except ImportError:  # PyMuPDF is optional; pypdf is used as fallback.
    fitz = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "data" / "metadata" / "document_registry.xlsx"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "extracted_text"
LOG_PATH = PROJECT_ROOT / "data" / "processed" / "document_loader_log.csv"


@dataclass
class ExtractedDocument:
    text: str
    extractor: str
    page_count: int | None = None
    warning: str = ""


def extract_text_from_pdf(file_path: Path) -> ExtractedDocument:
    """Extract raw text from a PDF, preserving page boundaries."""
    if fitz is not None:
        text_parts: list[str] = []
        with fitz.open(file_path) as pdf:
            for page_index, page in enumerate(pdf, start=1):
                text_parts.append(f"\n\n===== PAGE {page_index} =====\n")
                text_parts.append(page.get_text("text") or "")
            page_count = len(pdf)
        return ExtractedDocument(
            text="\n".join(text_parts),
            extractor="pymupdf",
            page_count=page_count,
        )

    reader = PdfReader(str(file_path))
    text_parts = []
    for page_index, page in enumerate(reader.pages, start=1):
        text_parts.append(f"\n\n===== PAGE {page_index} =====\n")
        try:
            text_parts.append(page.extract_text() or "")
        except Exception as exc:  # Keep processing other pages.
            text_parts.append("")
            text_parts.append(f"\n[PAGE_EXTRACTION_ERROR] {exc}\n")

    return ExtractedDocument(
        text="\n".join(text_parts),
        extractor="pypdf",
        page_count=len(reader.pages),
        warning="PyMuPDF is not installed; used pypdf fallback.",
    )


def extract_text_from_docx(file_path: Path) -> ExtractedDocument:
    """Extract text from a DOCX file, including simple table content."""
    document = Document(file_path)
    parts: list[str] = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if text:
            parts.append(text)

    for table_index, table in enumerate(document.tables, start=1):
        parts.append(f"\n===== TABLE {table_index} =====")
        for row in table.rows:
            values = [cell.text.strip() for cell in row.cells]
            if any(values):
                parts.append("\t".join(values))

    return ExtractedDocument(
        text="\n".join(parts),
        extractor="python-docx",
        page_count=None,
    )


def _is_useful_doc_line(line: str) -> bool:
    if len(line) < 2:
        return False

    binary_markers = (
        "Root Entry",
        "WordDocument",
        "SummaryInformation",
        "DocumentSummaryInformation",
        "CompObj",
        "Ole10Native",
        "ObjectPool",
        "ObjInfo",
    )
    if any(marker in line for marker in binary_markers):
        return False
    if line.count("ÿ") >= 3 or line.count("\ufffd") >= 1:
        return False

    letters = [char for char in line if char.isalpha()]
    latin_letters = [
        char for char in letters if "LATIN" in unicodedata.name(char, "")
    ]
    digits = sum(1 for char in line if char.isdigit())
    punctuation = sum(1 for char in line if char in ".,;:/()-[]% \"'“”‘’+-=_")
    useful = len(latin_letters) + digits + punctuation

    if letters and len(latin_letters) / len(letters) < 0.8:
        return False

    return useful / max(len(line), 1) >= 0.55 and len(latin_letters) + digits >= 2


def extract_text_from_legacy_doc(file_path: Path) -> ExtractedDocument:
    """Best-effort text extraction for old binary .doc files.

    python-docx does not support .doc. This fallback reads the UTF-16 text
    stream often embedded in Word 97-2003 files and filters binary noise.
    """
    raw = file_path.read_bytes()
    decoded = raw.decode("utf-16le", errors="ignore")
    decoded = decoded.replace("\x00", "")

    cleaned_chars = []
    for char in decoded:
        category = unicodedata.category(char)
        if char in "\r\n\t":
            cleaned_chars.append(char)
        elif category.startswith("C"):
            cleaned_chars.append("\n")
        else:
            cleaned_chars.append(char)

    cleaned = "".join(cleaned_chars)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    start_candidates = [
        cleaned.find("BỘ "),
        cleaned.find("TỔNG "),
        cleaned.find("CỘNG HÒA"),
        cleaned.find("Số:"),
    ]
    starts = [pos for pos in start_candidates if pos >= 0]
    if starts:
        cleaned = cleaned[min(starts) :]

    lines = [line.strip() for line in cleaned.splitlines()]
    lines = [line for line in lines if _is_useful_doc_line(line)]

    return ExtractedDocument(
        text="\n".join(lines),
        extractor="legacy-doc-utf16le",
        page_count=None,
        warning="Legacy .doc file extracted with best-effort UTF-16 fallback.",
    )


def load_document(file_path: Path) -> ExtractedDocument:
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return extract_text_from_pdf(file_path)
    if suffix == ".docx":
        return extract_text_from_docx(file_path)
    if suffix == ".doc":
        return extract_text_from_legacy_doc(file_path)

    raise ValueError(f"Unsupported file format: {suffix}")


def safe_filename(document_id: str) -> str:
    cleaned = document_id.strip().replace("/", "_").replace("\\", "_")
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", cleaned).strip("_")


def actual_text_length(text: str) -> int:
    without_page_markers = re.sub(r"===== PAGE \d+ =====", "", text)
    without_errors = re.sub(r"\[PAGE_EXTRACTION_ERROR].*", "", without_page_markers)
    return len(without_errors.strip())


def read_registry(registry_path: Path) -> pd.DataFrame:
    df = pd.read_excel(registry_path, dtype=str).fillna("")
    required_columns = ["document_id", "local_path"]
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ValueError(
            "Missing required column(s) in document_registry.xlsx: "
            + ", ".join(missing)
        )
    return df


def write_log(log_path: Path, rows: list[dict[str, object]]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "document_id",
        "local_path",
        "output_path",
        "status",
        "extractor",
        "page_count",
        "char_count",
        "warning",
        "error",
    ]
    with log_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_loader(
    registry_path: Path,
    output_dir: Path,
    log_path: Path,
    skip_existing: bool = False,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    df = read_registry(registry_path)

    logs: list[dict[str, object]] = []
    counters = {"success": 0, "empty": 0, "error": 0, "skipped": 0}

    for row_index, row in df.iterrows():
        document_id = str(row["document_id"]).strip()
        local_path = str(row["local_path"]).strip()

        if not document_id or not local_path:
            print(f"[SKIP] Row {row_index + 2}: missing document_id or local_path")
            counters["skipped"] += 1
            continue

        source_path = PROJECT_ROOT / local_path
        output_path = output_dir / f"{safe_filename(document_id)}.txt"

        if skip_existing and output_path.exists():
            print(f"[SKIP] Existing output: {output_path}")
            counters["skipped"] += 1
            continue

        log_row: dict[str, object] = {
            "document_id": document_id,
            "local_path": local_path,
            "output_path": str(output_path.relative_to(PROJECT_ROOT)),
            "status": "",
            "extractor": "",
            "page_count": "",
            "char_count": 0,
            "warning": "",
            "error": "",
        }

        if not source_path.exists():
            message = f"Source file not found: {source_path}"
            print(f"[ERROR] {document_id}: {message}")
            log_row["status"] = "error"
            log_row["error"] = message
            logs.append(log_row)
            counters["error"] += 1
            continue

        try:
            print(f"[LOAD] {document_id} <- {local_path}")
            extracted = load_document(source_path)
            text = extracted.text
            char_count = actual_text_length(text)

            output_path.write_text(text, encoding="utf-8")

            status = "success" if char_count > 0 else "empty"
            if status == "empty":
                print(f"[WARNING] Empty extracted text: {document_id}")
            else:
                print(f"[OK] {document_id}: {char_count} chars -> {output_path}")

            log_row.update(
                {
                    "status": status,
                    "extractor": extracted.extractor,
                    "page_count": extracted.page_count or "",
                    "char_count": char_count,
                    "warning": extracted.warning,
                }
            )
            logs.append(log_row)
            counters[status] += 1
        except Exception as exc:
            print(f"[ERROR] {document_id}: {exc}")
            log_row["status"] = "error"
            log_row["error"] = str(exc)
            logs.append(log_row)
            counters["error"] += 1

    write_log(log_path, logs)

    print("\n===== DOCUMENT LOADER SUMMARY =====")
    print(f"Success: {counters['success']}")
    print(f"Empty:   {counters['empty']}")
    print(f"Error:   {counters['error']}")
    print(f"Skipped: {counters['skipped']}")
    print(f"Log:     {log_path}")

    return 1 if counters["error"] else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract raw text from files listed in document_registry.xlsx."
    )
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--log-path", type=Path, default=LOG_PATH)
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Do not overwrite existing extracted .txt files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_loader(
        registry_path=args.registry,
        output_dir=args.output_dir,
        log_path=args.log_path,
        skip_existing=args.skip_existing,
    )


if __name__ == "__main__":
    sys.exit(main())
