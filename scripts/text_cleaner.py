from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = PROJECT_ROOT / "data" / "processed" / "extracted_text"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "cleaned_text"
LOG_PATH = PROJECT_ROOT / "data" / "processed" / "text_cleaner_log.csv"


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


PAGE_MARKER_RE = re.compile(r"\n*===== PAGE \d+ =====\n*", re.IGNORECASE)
TABLE_MARKER_RE = re.compile(r"\n*===== TABLE \d+ =====\n*", re.IGNORECASE)
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
VIETNAMESE_COMBINING_MARKS = {
    "\u0300",  # grave
    "\u0301",  # acute
    "\u0303",  # tilde
    "\u0309",  # hook above
    "\u0323",  # dot below
    "\u0302",  # circumflex
    "\u0306",  # breve
    "\u031b",  # horn
}
CONTENT_ANCHORS = (
    "DANH M\u1ee4C",
    "C\u00c1C M\u1eaaU",
    "M\u1eabu s\u1ed1",
    "C\u1ed8NG H\u00d2A",
    "C\u1ed8NG HO\u00c0",
    "T\u1edc KHAI",
    "B\u1ea2NG K\u00ca",
    "\u0110\u01a1n v\u1ecb t\u00ednh",
    "Stt ",
)
LEGAL_START_RE = re.compile(
    r"^("
    r"Chương\b|Mục\b|Phần\b|Điều\b|Khoản\b|Tiết\b|"
    r"\d+[\.)]\s+|[a-zA-ZđĐ]\)\s+|[A-ZĐ]\.\s+|"
    r"[-–•]\s+|\+\s+|"
    r"Số\s*:|V/v\b|Kính gửi[:\s]|Nơi nhận[:\s]|"
    r"Căn cứ\b|Theo\b|Tại\b|"
    r"Hà Nội,\s*ngày|Thành phố\b|TP\.\s*|"
    r"Luật số[:\s]|Nghị định số[:\s]|Nghị quyết số[:\s]|"
    r"Thông tư số[:\s]|Quyết định số[:\s]"
    r")",
    re.IGNORECASE,
)
SENTENCE_ENDS = (".", ":", ";", "?", "!", "”", '"', ")", "…")


@dataclass
class CleaningStats:
    input_chars: int
    output_chars: int
    input_lines: int
    output_lines: int
    warning: str = ""


def normalize_unicode(text: str) -> str:
    """Normalize Vietnamese text to NFC."""
    return unicodedata.normalize("NFC", text)


def repair_common_mojibake(text: str) -> str:
    """Repair common UTF-8-as-Latin-1 mojibake only when clearly present."""
    markers = ("Ã", "Ä", "áº", "á»", "Â")
    marker_count = sum(text.count(marker) for marker in markers)
    if marker_count < 5:
        return text

    try:
        repaired = text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text

    repaired_marker_count = sum(repaired.count(marker) for marker in markers)
    return repaired if repaired_marker_count < marker_count else text


def remove_page_markers(text: str) -> str:
    text = PAGE_MARKER_RE.sub("\n", text)
    text = TABLE_MARKER_RE.sub("\n", text)
    return text


def normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_spaces(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = text.replace("\ufeff", "")
    text = CONTROL_CHAR_RE.sub("\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def is_vietnamese_or_ascii_letter(char: str) -> bool:
    if char in {"\u0110", "\u0111"}:
        return True

    decomposed = unicodedata.normalize("NFD", char)
    if not decomposed:
        return False

    base = decomposed[0]
    if not base.isascii() or not base.isalpha():
        return False

    return all(mark in VIETNAMESE_COMBINING_MARKS for mark in decomposed[1:])


def non_vietnamese_letter_ratio(text: str) -> float:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0

    noisy_letters = [
        char for char in letters if not is_vietnamese_or_ascii_letter(char)
    ]
    return len(noisy_letters) / len(letters)


def strip_leading_artifact_prefix(line: str) -> str:
    for anchor in CONTENT_ANCHORS:
        position = line.find(anchor)
        if 0 < position <= 12 and non_vietnamese_letter_ratio(line[:position]) > 0:
            return line[position:].lstrip()
    return line


def remove_embedded_artifact_spans(text: str) -> str:
    start_markers = (
        "FILE \u0110\u01af\u1ee2C",
        "EMBED Word.Document",
    )

    while True:
        starts = [
            position
            for marker in start_markers
            if (position := text.find(marker)) >= 0
        ]
        if not starts:
            return text

        start = min(starts)
        anchors = [
            position
            for anchor in CONTENT_ANCHORS
            if (position := text.find(anchor, start + 1)) >= 0
        ]
        if not anchors:
            return text

        end = min(anchors)
        if end <= start or end - start > 30000:
            return text

        text = f"{text[:start].rstrip()}\n{text[end:].lstrip()}"


def is_likely_binary_artifact(line: str) -> bool:
    normalized = line.strip()
    if not normalized:
        return False
    if normalized == "PAGE":
        return True
    if normalized in {"Normal", "No List", "Table Normal", "Table Grid"}:
        return True
    if re.fullmatch(r"Heading\s+\d+", normalized):
        return True
    if "\u0100" in normalized or "\u0102\u0102" in normalized:
        return True
    if re.search(r"ABCDEFGHIJKLMNOPQRSTUVWXYZ|abcdefghijklmnopqrstuvwxyz", normalized):
        return True
    if len(normalized) >= 10 and " " not in normalized:
        alpha_chars = {char for char in normalized if char.isalpha()}
        symbol_count = sum(
            1 for char in normalized if unicodedata.category(char)[0] in {"P", "S"}
        )
        if "\u0100" in normalized:
            return True
        if normalized.count("\u0102") >= 2 and symbol_count > 0:
            return True
        if normalized.count("\u0102") >= 6:
            return True
        if len(normalized) >= 20 and len(alpha_chars) <= 4:
            return True
        if len(alpha_chars) <= 4 and symbol_count / len(normalized) > 0.35:
            return True

    binary_markers = (
        "Root Entry",
        "WordDocument",
        "EMBED Word.Document",
        "FILE \u0110\u01af\u1ee2C",
        "SummaryInformation",
        "DocumentSummaryInformation",
        "CompObj",
        "Ole10Native",
        "ObjectPool",
        "ObjInfo",
        "Default Paragraph Font",
        "Normal Heading",
        "Table Normal",
        "Footer Page Number",
        "Table Normal No List",
        "#Char",
    )
    if any(marker in normalized for marker in binary_markers):
        return True
    if normalized.count("\xff") >= 3 or normalized.count("\ufffd") >= 1:
        return True

    letters = [char for char in normalized if char.isalpha()]
    if not letters:
        return False

    latin_letters = [
        char for char in letters if "LATIN" in unicodedata.name(char, "")
    ]
    bad_letter_count = len(letters) - len(latin_letters)
    bad_letter_ratio = bad_letter_count / len(letters)

    if len(normalized) >= 20 and bad_letter_ratio > 0.2:
        return True
    if len(normalized) >= 10 and bad_letter_count >= 8 and len(latin_letters) < 5:
        return True
    if len(normalized) >= 20 and non_vietnamese_letter_ratio(normalized) > 0.18:
        return True
    if len(normalized) >= 8 and non_vietnamese_letter_ratio(normalized) > 0.45:
        return True
    if len(normalized) >= 4 and non_vietnamese_letter_ratio(normalized) > 0.65:
        return True

    return False


def trim_binary_artifact_suffix(line: str) -> str:
    trim_markers = (
        "EMBED Word.Document",
        "EMBED Package",
        "FILE \u0110\u01af\u1ee2C",
        "INCLUDEPICTURE",
        "image001",
        "Ole ",
        "Normal Default Paragraph Font",
        "Default Paragraph Font",
        "Normal Heading",
        "Table Normal",
        "Table Grid",
        "Footer Page Number",
        "#Char",
        " 1\u0100",
        "Times New Roman",
        "Cambria Math",
        "User PC",
        "1Table",
        '!"#$%&',
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz",
        "\u00ae\u00af\u00b0",
        "\u00fd\u00fd\u00fd",
        "\u00ff\u00ff",
        "\u0100\uff10",
        "\u0201\uff10",
        "\u0108\u0108",
        "\u00e3\u00e3",
        "\u272b0",
        "\u5a0f",
        "\u5a03",
        "\u00c0\u4600",
    )
    positions = [line.find(marker) for marker in trim_markers if marker in line]
    if not positions:
        return line
    return line[: min(positions)].rstrip()


def remove_binary_artifact_lines(text: str) -> str:
    lines = []
    for line in text.splitlines():
        line = strip_leading_artifact_prefix(line)
        line = trim_binary_artifact_suffix(line)
        if is_likely_binary_artifact(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def is_trailing_binary_artifact_line(line: str, loose: bool = False) -> bool:
    normalized = line.strip()
    if not normalized:
        return True

    exact_markers = {
        "Ole",
        "\u00ea\u00dc",
        "\u00f8 \u0104",
        "\u00c4 \u00d0",
        "\u1cc0 X\u0100",
        "User PC",
        "User",
        "PC",
        "Unknown",
        "B\u1ed8 T\u00c0I CH\u00cdNH",
    }
    if normalized in exact_markers:
        return True

    tail_markers = (
        "Normal Default",
        "Table Normal",
        "Unknown",
        "\ua75b",
        "\u1818",
        "\u00c0\u0136",
        "LM\u0500",
        "Y\ufb00",
        "\u00d4\u00d5",
        "\u00d5\u2e00",
        "X\u0100",
        "\u7843",
        "\uc000",
        "\u01ff",
        "\u24ff",
    )
    if any(marker in normalized for marker in tail_markers):
        return True

    if loose and " " not in normalized and len(normalized) <= 40:
        return True

    return is_likely_binary_artifact(normalized)


def remove_trailing_binary_artifact_block(text: str) -> str:
    lines = text.splitlines()
    found_artifact = False
    while lines and is_trailing_binary_artifact_line(lines[-1], loose=found_artifact):
        if lines[-1].strip():
            found_artifact = True
        lines.pop()
    return "\n".join(lines)


def remove_trailing_binary_artifact_suffix(text: str) -> str:
    trailing_markers = (
        "\n\u00ea\u00dc",
        "\nOle",
        "\n\u00f8 \u0104",
        "\u00fd\u00f8\u00f8",
        "\u00fd\u00f8",
        " \u00fd\u00f8",
        "\n\u00fd\u00f8",
        "\nNormal DA",
        "\ua75b",
        "Normal Default Paragraph Font",
        "Default Paragraph Font",
        "Table Normal No List",
        "\u00a1D\u0100",
    )
    tail_threshold = max(0, len(text) - 5000)
    positions = [
        position
        for marker in trailing_markers
        if (position := text.find(marker, tail_threshold)) >= 0
    ]
    if not positions:
        return text
    return text[: min(positions)].rstrip()


def strip_each_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(lines)


def remove_excess_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


def remove_obvious_page_noise(text: str) -> str:
    """Remove page artifacts without deleting legal structure."""
    lines = text.splitlines()
    cleaned: list[str] = []

    for index, line in enumerate(lines):
        normalized = line.strip()
        prev_line = lines[index - 1].strip() if index > 0 else ""
        next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""

        if re.match(r"^CÔNG BÁO/Số\b", normalized, re.IGNORECASE):
            continue
        if re.match(r"^\d+\s+CÔNG BÁO/Số\b", normalized, re.IGNORECASE):
            continue
        if normalized.isdigit() and (
            re.match(r"^CÔNG BÁO/Số\b", next_line, re.IGNORECASE)
            or re.match(r"^CÔNG BÁO/Số\b", prev_line, re.IGNORECASE)
        ):
            continue
        if re.fullmatch(r"[-–—_]{3,}", normalized):
            continue

        cleaned.append(line)

    return "\n".join(cleaned)


def looks_like_heading(line: str) -> bool:
    if len(line) < 4:
        return False
    letters = [char for char in line if char.isalpha()]
    if len(letters) < 3:
        return False
    uppercase_letters = [char for char in letters if char.upper() == char]
    return len(uppercase_letters) / len(letters) > 0.85


def should_merge(previous: str, current: str) -> bool:
    if not previous or not current:
        return False
    if LEGAL_START_RE.match(current):
        return False
    if "Độc lập" in previous and "Tự do" in previous and "Hạnh phúc" in previous:
        return False
    if looks_like_heading(previous) or looks_like_heading(current):
        return False
    if previous.endswith(SENTENCE_ENDS):
        return False
    if re.search(r"[,/]$", previous):
        return True
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}\b", current):
        return True
    if current.lower().startswith("số ") and not re.match(r"^(Số|Luật số)", previous, re.IGNORECASE):
        return True
    if current[:1].islower():
        return True
    if len(previous) < 100 and len(current) < 100:
        return True
    return False


def merge_broken_lines(text: str) -> str:
    """Merge lines broken in the middle of a sentence, preserving legal units."""
    merged_lines: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line:
            if merged_lines and merged_lines[-1] != "":
                merged_lines.append("")
            continue

        if not merged_lines or merged_lines[-1] == "":
            merged_lines.append(line)
            continue

        previous = merged_lines[-1]
        if should_merge(previous, line):
            merged_lines[-1] = f"{previous} {line}"
        else:
            merged_lines.append(line)

    return "\n".join(merged_lines)


def clean_text(text: str) -> str:
    text = normalize_line_endings(text)
    text = normalize_unicode(text)
    text = repair_common_mojibake(text)
    text = remove_page_markers(text)
    text = normalize_spaces(text)
    text = strip_each_line(text)
    text = remove_embedded_artifact_spans(text)
    text = remove_binary_artifact_lines(text)
    text = remove_trailing_binary_artifact_block(text)
    text = remove_obvious_page_noise(text)
    text = remove_excess_blank_lines(text)
    text = merge_broken_lines(text)
    text = remove_binary_artifact_lines(text)
    text = remove_excess_blank_lines(text)
    text = remove_trailing_binary_artifact_block(text)
    text = remove_trailing_binary_artifact_suffix(text)
    return text.strip()


def clean_file(input_file: Path, output_file: Path) -> CleaningStats:
    raw_text = input_file.read_text(encoding="utf-8", errors="ignore")
    cleaned = clean_text(raw_text)
    output_file.write_text(cleaned, encoding="utf-8")

    warning = ""
    if not cleaned.strip():
        warning = "empty_after_cleaning"
    elif len(cleaned.strip()) < 200:
        warning = "very_short_text"

    return CleaningStats(
        input_chars=len(raw_text),
        output_chars=len(cleaned),
        input_lines=len(raw_text.splitlines()),
        output_lines=len(cleaned.splitlines()),
        warning=warning,
    )


def write_log(rows: list[dict[str, object]], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "file_name",
        "output_path",
        "status",
        "input_chars",
        "output_chars",
        "input_lines",
        "output_lines",
        "warning",
        "error",
    ]
    with log_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_cleaner(input_dir: Path, output_dir: Path, log_path: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    input_files = sorted(
        file for file in input_dir.glob("*.txt") if file.name != ".gitkeep"
    )

    if not input_files:
        print(f"No .txt files found in {input_dir}")
        return 1

    logs: list[dict[str, object]] = []
    counters = {"success": 0, "warning": 0, "error": 0}

    for input_file in input_files:
        output_file = output_dir / input_file.name
        log_row: dict[str, object] = {
            "file_name": input_file.name,
            "output_path": str(output_file.relative_to(PROJECT_ROOT)),
            "status": "",
            "input_chars": 0,
            "output_chars": 0,
            "input_lines": 0,
            "output_lines": 0,
            "warning": "",
            "error": "",
        }

        try:
            stats = clean_file(input_file, output_file)
            status = "warning" if stats.warning else "success"
            log_row.update(
                {
                    "status": status,
                    "input_chars": stats.input_chars,
                    "output_chars": stats.output_chars,
                    "input_lines": stats.input_lines,
                    "output_lines": stats.output_lines,
                    "warning": stats.warning,
                }
            )
            counters[status] += 1
            print(
                f"[{status.upper()}] {input_file.name}: "
                f"{stats.input_chars} -> {stats.output_chars} chars"
                + (f" ({stats.warning})" if stats.warning else "")
            )
        except Exception as exc:
            log_row["status"] = "error"
            log_row["error"] = str(exc)
            counters["error"] += 1
            print(f"[ERROR] {input_file.name}: {exc}")

        logs.append(log_row)

    write_log(logs, log_path)

    print("\n===== TEXT CLEANING SUMMARY =====")
    print(f"Success: {counters['success']}")
    print(f"Warning: {counters['warning']}")
    print(f"Error:   {counters['error']}")
    print(f"Output:  {output_dir}")
    print(f"Log:     {log_path}")

    return 1 if counters["error"] else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean extracted raw text files.")
    parser.add_argument("--input-dir", type=Path, default=INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--log-path", type=Path, default=LOG_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_cleaner(args.input_dir, args.output_dir, args.log_path)


if __name__ == "__main__":
    sys.exit(main())
