import argparse
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[1]


TYPE_BY_FOLDER = {
    "laws": "Luật",
    "decrees": "Nghị định",
    "circulars": "Thông tư",
    "directives": "Chỉ thị",
    "official_dispatches": "Công văn",
    "resolutions": "Nghị quyết",
}


AUTHORITY_BY_CODE = [
    (re.compile(r"/QH\d+", re.I), "Quốc hội"),
    (re.compile(r"/UBTVQH\d+", re.I), "Ủy ban Thường vụ Quốc hội"),
    (re.compile(r"/NĐ-CP", re.I), "Chính phủ"),
    (re.compile(r"/TT-BTC", re.I), "Bộ Tài chính"),
    (re.compile(r"/TTLT-BTC-BCA", re.I), "Bộ Tài chính; Bộ Công an"),
    (re.compile(r"/TTLT-BTC-BQP", re.I), "Bộ Tài chính; Bộ Quốc phòng"),
    (re.compile(r"/TCT-", re.I), "Tổng cục Thuế"),
    (re.compile(r"/CTHN-", re.I), "Cục Thuế Thành phố Hà Nội"),
    (re.compile(r"/CT-TTHT", re.I), "Cục Thuế"),
]


VIETNAMESE_MONTH_DATE = re.compile(
    r"ng[aà]y\s+(\d{1,2})\s+th[aá]ng\s+(\d{1,2})\s+n[aă]m\s+(\d{4})",
    re.I,
)


def strip_accents(value: str) -> str:
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", value)


def normalize_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_code(value: str) -> str:
    value = normalize_ws(value)
    value = value.replace("–", "-").replace("—", "-")
    value = re.sub(r"\s*/\s*", "/", value)
    value = re.sub(r"\s*-\s*", "-", value)
    return value.upper()


def filename_to_number(path: Path) -> str:
    stem = path.stem
    folder = path.parent.name

    if folder in {"laws", "decrees", "circulars", "resolutions", "directives"}:
        match = re.match(r"^(\d+)-(\d{4})-([A-Za-zĐđ0-9]+(?:-[A-Za-zĐđ0-9]+){0,2})", stem)
        if match:
            number, year, suffix = match.groups()
            suffix = suffix.replace("ND-CP", "NĐ-CP")
            return normalize_code(f"{number}/{year}/{suffix}")

    if folder == "official_dispatches":
        match = re.match(r"^(\d+)-(.+)$", stem)
        if match:
            number, suffix = match.groups()
            parts = suffix.split("-")
            code = parts[0] if len(parts) == 1 else f"{parts[0]}-{'-'.join(parts[1:])}"
            return normalize_code(f"{number}/{code}")

    match = re.match(r"^(\d+)-(.+)$", stem)
    if match:
        number, suffix = match.groups()
        return normalize_code(f"{number}/{suffix}")

    return normalize_code(stem.replace("-", "/"))


def document_id(document_type: str, document_number: str) -> str:
    prefixes = {
        "Luật": "LAW",
        "Nghị định": "DECREE",
        "Thông tư": "CIRCULAR",
        "Thông tư liên tịch": "JOINT_CIRCULAR",
        "Chỉ thị": "DIRECTIVE",
        "Công văn": "DISPATCH",
        "Nghị quyết": "RESOLUTION",
    }
    prefix = prefixes.get(document_type, "DOC")
    body = strip_accents(document_number.upper())
    body = body.replace("Đ", "D")
    body = re.sub(r"[^A-Z0-9]+", "_", body).strip("_")
    return f"{prefix}_{body}"


def read_pdf_text(path: Path, max_pages: int | None = None) -> tuple[str, int]:
    reader = PdfReader(str(path))
    pages = reader.pages
    page_count = len(pages)
    selected = pages if max_pages is None else pages[:max_pages]
    chunks = []
    for page in selected:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            chunks.append("")
    return "\n".join(chunks), page_count


def read_doc_binary_text(path: Path) -> str:
    data = path.read_bytes()
    utf16 = data.decode("utf-16le", errors="ignore")
    ascii_text = data.decode("latin-1", errors="ignore")
    candidates = []
    for source in (utf16, ascii_text):
        cleaned = "".join(ch if ch.isprintable() or ch in "\n\r\t" else " " for ch in source)
        lines = [normalize_ws(line) for line in cleaned.splitlines()]
        lines = [line for line in lines if len(line) >= 3]
        candidates.append("\n".join(lines))
    return max(candidates, key=len)


def extract_document_number(text: str, fallback: str) -> str:
    patterns = [
        r"S[ốo]\s*[:：]\s*([0-9]+(?:/[0-9]{4})?/[A-ZĐ\-0-9]+(?:-[A-ZĐ0-9]+)*)",
        r"Lu[aậ]t\s+s[ốo]\s*[:：]?\s*([0-9]+/[0-9]{4}/QH[0-9]+)",
        r"Ngh[ịi]\s*[đd][ịi]nh\s+s[ốo]\s*[:：]?\s*([0-9]+/[0-9]{4}/N[ĐD]-CP)",
        r"Th[oô]ng\s+t[ưu]\s+s[ốo]\s*[:：]?\s*([0-9]+/[0-9]{4}/TT(?:LT)?-[A-ZĐ\-]+)",
        r"Ngh[ịi]\s+quy[eế]t\s+s[ốo]\s*[:：]?\s*([0-9]+/[0-9]{4}/UBTVQH[0-9]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return normalize_code(match.group(1))
    return fallback


def extract_date_near(text: str, keyword_pattern: str) -> str | None:
    plain = normalize_ws(text)
    keyword = re.search(keyword_pattern, plain, re.I)
    if not keyword:
        return None
    window = plain[keyword.end() : keyword.end() + 260]
    match = VIETNAMESE_MONTH_DATE.search(window)
    if match:
        day, month, year = map(int, match.groups())
        return f"{year:04d}-{month:02d}-{day:02d}"
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", window)
    if match:
        day, month, year = map(int, match.groups())
        return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def extract_first_vietnamese_date(text: str) -> str | None:
    match = VIETNAMESE_MONTH_DATE.search(text)
    if match:
        day, month, year = map(int, match.groups())
        return f"{year:04d}-{month:02d}-{day:02d}"
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if match:
        day, month, year = map(int, match.groups())
        return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def extract_effective_date(full_text: str) -> str | None:
    patterns = [
        r"c[oó]\s+hi[ệe]u\s+l[ựu]c(?:\s+thi\s+h[aà]nh)?(?:\s+k[ểe]\s+t[ừu])?",
        r"hi[ệe]u\s+l[ựu]c\s+thi\s+h[aà]nh\s+t[ừu]",
    ]
    candidates = []
    for pattern in patterns:
        for match in re.finditer(pattern, full_text, re.I):
            window = full_text[match.end() : match.end() + 320]
            date_match = VIETNAMESE_MONTH_DATE.search(window)
            if date_match:
                day, month, year = map(int, date_match.groups())
                candidates.append(f"{year:04d}-{month:02d}-{day:02d}")
            slash = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", window)
            if slash:
                day, month, year = map(int, slash.groups())
                candidates.append(f"{year:04d}-{month:02d}-{day:02d}")
    return candidates[-1] if candidates else None


def infer_authority(document_number: str, text: str) -> str:
    for pattern, authority in AUTHORITY_BY_CODE:
        if pattern.search(document_number):
            return authority

    upper_text = strip_accents(text[:1200]).upper()
    if "BO TAI CHINH" in upper_text and "BO CONG AN" in upper_text:
        return "Bộ Tài chính; Bộ Công an"
    if "BO TAI CHINH" in upper_text and "BO QUOC PHONG" in upper_text:
        return "Bộ Tài chính; Bộ Quốc phòng"
    if "BO TAI CHINH" in upper_text:
        return "Bộ Tài chính"
    if "TONG CUC THUE" in upper_text:
        return "Tổng cục Thuế"
    if "CUC THUE TP HA NOI" in upper_text or "CUC THUE THANH PHO HA NOI" in upper_text:
        return "Cục Thuế Thành phố Hà Nội"
    return ""


def extract_title(document_type: str, document_number: str, text: str, path: Path) -> str:
    lines = [normalize_ws(line) for line in text.splitlines()]
    lines = [line for line in lines if line and len(line) <= 220]
    upperless = [strip_accents(line).upper() for line in lines]

    if document_type == "Công văn":
        for line in lines:
            if re.match(r"^(V/v|Về việc)\b", line, re.I):
                return f"Công văn {document_number} {line}"
        return f"Công văn {document_number}"

    type_words = {
        "Luật": ["LUAT"],
        "Nghị định": ["NGHI DINH"],
        "Thông tư": ["THONG TU"],
        "Thông tư liên tịch": ["THONG TU LIEN TICH", "THONG TU"],
        "Nghị quyết": ["NGHI QUYET"],
        "Chỉ thị": ["CHI THI"],
    }.get(document_type, [])

    for idx, upper in enumerate(upperless):
        if any(word in upper for word in type_words):
            collected = [lines[idx]]
            for nxt in range(idx + 1, min(idx + 5, len(lines))):
                candidate_upper = upperless[nxt]
                if any(stop in candidate_upper for stop in ["CAN CU", "QUOC HOI", "CHINH PHU", "BO TAI CHINH"]):
                    break
                if len(lines[nxt]) > 4:
                    collected.append(lines[nxt])
            title = normalize_ws(" ".join(collected))
            title = re.sub(r"^\d+\s+", "", title)
            if len(title) > 12:
                return title

    return f"{document_type} {document_number}"


def status_from_dates(effective_date: str | None, expiry_date: str | None) -> str:
    today = date.today().isoformat()
    if expiry_date and expiry_date <= today:
        return "expired"
    if effective_date and effective_date > today:
        return "not_yet_effective"
    return "effective"


def topics_from_title(title: str, text: str) -> str:
    combined = strip_accents(f"{title} {text[:2500]}").lower()
    topics = ["thuế thu nhập cá nhân"]
    keyword_topics = [
        ("quyet toan", "quyết toán thuế"),
        ("giam tru gia canh", "giảm trừ gia cảnh"),
        ("nguoi phu thuoc", "người phụ thuộc"),
        ("khau tru", "khấu trừ thuế"),
        ("cu tru", "cư trú"),
        ("tien luong", "tiền lương, tiền công"),
        ("tien cong", "tiền lương, tiền công"),
        ("chuyen nhuong", "chuyển nhượng"),
        ("bao hiem", "bảo hiểm"),
        ("ca nhan kinh doanh", "cá nhân kinh doanh"),
    ]
    for needle, topic in keyword_topics:
        if needle in combined and topic not in topics:
            topics.append(topic)
    return "; ".join(topics)


def build_row(path: Path) -> dict:
    rel = path.relative_to(PROJECT_ROOT).as_posix()
    folder = path.parent.name
    document_type = TYPE_BY_FOLDER.get(folder, "Tài liệu")
    fallback_number = filename_to_number(path)

    if path.suffix.lower() == ".pdf":
        head_text, page_count = read_pdf_text(path, max_pages=3)
        full_text, _ = read_pdf_text(path)
    elif path.suffix.lower() == ".doc":
        head_text = read_doc_binary_text(path)
        full_text = head_text
        page_count = None
    else:
        head_text = path.read_text(encoding="utf-8", errors="ignore")
        full_text = head_text
        page_count = None

    document_number = extract_document_number(head_text, fallback_number)
    if "TTLT" in document_number:
        document_type = "Thông tư liên tịch"
    issuing_authority = infer_authority(document_number, head_text)
    issue_date = extract_first_vietnamese_date(head_text)
    effective_date = extract_effective_date(full_text)
    if document_type == "Công văn" and issue_date and not effective_date:
        effective_date = issue_date
    title = extract_title(document_type, document_number, head_text, path)
    text_is_scanned = path.suffix.lower() == ".pdf" and len(normalize_ws(full_text)) < 100

    row = {
        "document_id": document_id(document_type, document_number),
        "file_name": path.name,
        "title": title,
        "document_number": document_number,
        "document_type": document_type,
        "issuing_authority": issuing_authority,
        "issue_date": issue_date or "",
        "effective_date": effective_date or "",
        "expiry_date": "",
        "status": status_from_dates(effective_date, None),
        "source_type": "official",
        "source_url": "",
        "local_path": rel,
        "download_date": "2026-06-07",
        "topics": topics_from_title(title, full_text),
        "version": 1,
        "notes": "",
        "_page_count": page_count,
        "_excerpt": normalize_ws(head_text[:900]),
    }

    if not effective_date and document_type != "Công văn":
        row["notes"] = "Chưa trích xuất chắc chắn ngày hiệu lực từ nội dung; cần rà soát thủ công."
    if document_type == "Công văn":
        row["notes"] = "Công văn không phải văn bản quy phạm pháp luật; dùng ngày ban hành làm mốc hiệu lực tham chiếu nếu trích xuất được."
    if text_is_scanned:
        row["notes"] = normalize_ws(
            f"{row['notes']} PDF dạng scan/ảnh, không trích xuất được toàn văn bằng pypdf."
        )
    if path.suffix.lower() == ".doc":
        row["notes"] = normalize_ws(
            f"{row['notes']} File .doc cũ, metadata trích từ text nhúng trong file."
        )

    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default=str(PROJECT_ROOT / "data" / "raw"))
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    files = [
        p
        for p in raw_dir.rglob("*")
        if p.is_file()
        and p.name != ".gitkeep"
        and p.suffix.lower() in {".pdf", ".doc", ".docx", ".txt"}
    ]
    rows = [build_row(path) for path in sorted(files, key=lambda p: p.as_posix())]

    payload = {"generated_at": "2026-06-07", "count": len(rows), "rows": rows}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
