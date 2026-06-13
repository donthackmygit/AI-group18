from __future__ import annotations

import re
import unicodedata

from backend.app.schemas.question_processing import ExtractedEntities


NUMBER_WORDS = {
    "không": 0,
    "một": 1,
    "mot": 1,
    "hai": 2,
    "ba": 3,
    "bốn": 4,
    "bon": 4,
    "tư": 4,
    "năm": 5,
    "nam": 5,
    "sáu": 6,
    "sau": 6,
    "bảy": 7,
    "bay": 7,
    "tám": 8,
    "tam": 8,
    "chín": 9,
    "chin": 9,
    "mười": 10,
    "muoi": 10,
}


def _parse_decimal(value: str) -> float:
    return float(value.replace(",", "."))


def _parse_integer_digits(value: str) -> int:
    return int(value.replace(".", "").replace(",", ""))


def _ascii_fold(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def parse_money_to_vnd(text: str) -> int | None:
    q = _ascii_fold(text)

    ascii_million_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(trieu|tr)\b", q)
    if ascii_million_match:
        return int(_parse_decimal(ascii_million_match.group(1)) * 1_000_000)

    ascii_vnd_match = re.search(r"(\d[\d.,]{5,})\s*(dong|vnd)?\b", q)
    if ascii_vnd_match:
        return _parse_integer_digits(ascii_vnd_match.group(1))

    million_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(triệu|tr)\b", q)
    if million_match:
        return int(_parse_decimal(million_match.group(1)) * 1_000_000)

    vnd_match = re.search(r"(\d[\d.,]{5,})\s*(đồng|vnd|vnđ)?\b", q)
    if vnd_match:
        return _parse_integer_digits(vnd_match.group(1))

    return None


def extract_income(text: str) -> int | None:
    q = _ascii_fold(text)
    ascii_income_patterns = [
        r"(?:luong|tien luong|thu nhap|thu nhap chiu thue|thu nhap tinh thue)\D{0,20}(\d+(?:[.,]\d+)?)\s*(trieu|tr)\b",
        r"(?:luong|tien luong|thu nhap|thu nhap chiu thue|thu nhap tinh thue)\D{0,20}(\d[\d.,]{5,})\s*(dong|vnd)?\b",
    ]

    for pattern in ascii_income_patterns:
        match = re.search(pattern, q)
        if not match:
            continue
        if match.group(2) in {"trieu", "tr"}:
            return int(_parse_decimal(match.group(1)) * 1_000_000)
        return _parse_integer_digits(match.group(1))

    ascii_money_values = list(re.finditer(r"(\d+(?:[.,]\d+)?)\s*(trieu|tr)\b", q))
    for match in ascii_money_values:
        before = q[max(0, match.start() - 80) : match.start()]
        after = q[match.end() : match.end() + 40]
        if (
            "bao hiem" not in before
            and "bhxh" not in before
            and "bhyt" not in before
            and "bhtn" not in before
            and "bao hiem" not in after
            and "bhxh" not in after
            and "bhyt" not in after
            and "bhtn" not in after
        ):
            return int(_parse_decimal(match.group(1)) * 1_000_000)

    income_patterns = [
        r"(?:lương|tiền lương|thu nhập|thu nhập chịu thuế|thu nhập tính thuế)\D{0,20}(\d+(?:[.,]\d+)?)\s*(triệu|tr)\b",
        r"(?:lương|tiền lương|thu nhập|thu nhập chịu thuế|thu nhập tính thuế)\D{0,20}(\d[\d.,]{5,})\s*(đồng|vnd|vnđ)?\b",
    ]

    for pattern in income_patterns:
        match = re.search(pattern, q)
        if not match:
            continue
        if match.group(2) in {"triệu", "tr"}:
            return int(_parse_decimal(match.group(1)) * 1_000_000)
        return _parse_integer_digits(match.group(1))

    money_values = list(re.finditer(r"(\d+(?:[.,]\d+)?)\s*(triệu|tr)\b", q))
    for match in money_values:
        before = q[max(0, match.start() - 80) : match.start()]
        after = q[match.end() : match.end() + 40]
        if (
            "bảo hiểm" not in before
            and "bhxh" not in before
            and "bhyt" not in before
            and "bhtn" not in before
            and "bảo hiểm" not in after
            and "bhxh" not in after
            and "bhyt" not in after
            and "bhtn" not in after
        ):
            return int(_parse_decimal(match.group(1)) * 1_000_000)

    insurance_terms = ("bao hiem", "bảo hiểm", "bhxh", "bhyt", "bhtn")
    if not any(term in q for term in insurance_terms):
        return parse_money_to_vnd(q)
    return None


def extract_dependents(text: str) -> int | None:
    q = _ascii_fold(text)
    if any(
        phrase in q
        for phrase in (
            "khong co nguoi phu thuoc",
            "khong nguoi phu thuoc",
            "khong co npt",
            "khong npt",
            "0 nguoi phu thuoc",
            "0 npt",
        )
    ):
        return 0

    ascii_patterns = [
        r"(\d+)\s*nguoi phu thuoc",
        r"(\d+)\s*npt\b",
        r"co\s*(\d+)\s*nguoi",
    ]

    for pattern in ascii_patterns:
        match = re.search(pattern, q)
        if match:
            return int(match.group(1))

    for word, value in NUMBER_WORDS.items():
        folded_word = _ascii_fold(word)
        if f"{folded_word} nguoi phu thuoc" in q or f"co {folded_word} nguoi" in q:
            return value

    patterns = [
        r"(\d+)\s*người phụ thuộc",
        r"(\d+)\s*npt\b",
        r"có\s*(\d+)\s*người",
    ]

    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            return int(match.group(1))

    for word, value in NUMBER_WORDS.items():
        if f"{word} người phụ thuộc" in q or f"có {word} người" in q:
            return value

    return None


def extract_insurance(text: str) -> int | None:
    q = _ascii_fold(text)
    if any(
        phrase in q
        for phrase in (
            "khong dong bao hiem",
            "khong co bao hiem",
            "khong tru bao hiem",
            "bao hiem 0",
            "bao hiem la 0",
        )
    ):
        return 0

    ascii_patterns = [
        r"(?:bao hiem|dong bao hiem|bhxh|bhyt|bhtn)\D{0,70}(\d+(?:[.,]\d+)?)\s*(trieu|tr)\b",
        r"(?:bao hiem|dong bao hiem|bhxh|bhyt|bhtn)\D{0,70}(\d[\d.,]{5,})\s*(dong|vnd)?\b",
    ]

    for pattern in ascii_patterns:
        match = re.search(pattern, q)
        if not match:
            continue
        if match.group(2) in {"trieu", "tr"}:
            return int(_parse_decimal(match.group(1)) * 1_000_000)
        return _parse_integer_digits(match.group(1))

    patterns = [
        r"(?:bảo hiểm|đóng bảo hiểm|bhxh|bhyt|bhtn)\D{0,70}(\d+(?:[.,]\d+)?)\s*(triệu|tr)\b",
        r"(?:bảo hiểm|đóng bảo hiểm|bhxh|bhyt|bhtn)\D{0,70}(\d[\d.,]{5,})\s*(đồng|vnd|vnđ)?\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, q)
        if not match:
            continue
        if match.group(2) in {"triệu", "tr"}:
            return int(_parse_decimal(match.group(1)) * 1_000_000)
        return _parse_integer_digits(match.group(1))

    return None


def extract_income_period(text: str) -> str | None:
    q = _ascii_fold(text)
    if (
        "/nam" in q
        or "moi nam" in q
        or "hang nam" in q
        or "theo nam" in q
        or "ca nam" in q
        or "trong nam" in q
    ):
        return "yearly"
    if "/thang" in q or "moi thang" in q or "hang thang" in q or "theo thang" in q:
        return "monthly"
    if "thang" in q and "nam " not in q:
        return "monthly"
    if "luong" in q or "tien luong" in q:
        return "monthly"
    if "/năm" in q or "mỗi năm" in q or "hàng năm" in q or "theo năm" in q:
        return "yearly"
    if "/tháng" in q or "mỗi tháng" in q or "hàng tháng" in q or "theo tháng" in q:
        return "monthly"
    if "tháng" in q and "năm " not in q:
        return "monthly"
    if "lương" in q or "tiền lương" in q:
        return "monthly"
    return None


def extract_resident_status(text: str) -> str | None:
    q = _ascii_fold(text)
    days = extract_days_in_vietnam(text)
    if days is not None:
        return "resident" if days >= 183 else "non_resident"

    if "khong cu tru" in q:
        return "non_resident"
    if "cu tru" in q:
        return "resident"
    if "không cư trú" in q:
        return "non_resident"
    if "cư trú" in q:
        return "resident"
    return None


def extract_nationality(text: str) -> str | None:
    q = _ascii_fold(text)
    nationality_patterns = [
        ("nhat", "Nhật"),
        ("nhat ban", "Nhật"),
        ("han quoc", "Hàn Quốc"),
        ("trung quoc", "Trung Quốc"),
        ("my", "Mỹ"),
        ("hoa ky", "Mỹ"),
        ("anh", "Anh"),
        ("phap", "Pháp"),
        ("duc", "Đức"),
    ]
    if "nguoi nuoc ngoai" in q:
        return "nước ngoài"
    for keyword, label in nationality_patterns:
        if f"nguoi {keyword}" in q or f"quoc tich {keyword}" in q:
            return label
    return None


def extract_work_start_month(text: str) -> int | None:
    q = _ascii_fold(text)
    match = re.search(r"(?:tu|bat dau|lam viec tu)\s*thang\s*(\d{1,2})\b", q)
    if not match:
        match = re.search(r"\bthang\s*(\d{1,2})\b", q)
    if not match:
        return None
    month = int(match.group(1))
    if 1 <= month <= 12:
        return month
    return None


def extract_days_in_vietnam(text: str) -> int | None:
    q = _ascii_fold(text)
    match = re.search(r"\b(\d{1,3})\s*ngay\b", q)
    if match and ("viet nam" in q or "o vn" in q or "tai vn" in q):
        return int(match.group(1))
    return None


def extract_tax_year(text: str) -> int | None:
    match = re.search(r"\b(20\d{2})\b", text)
    if match:
        return int(match.group(1))
    return None


def extract_entities(question: str) -> ExtractedEntities:
    return ExtractedEntities(
        income=extract_income(question),
        income_period=extract_income_period(question),
        dependents=extract_dependents(question),
        insurance=extract_insurance(question),
        resident_status=extract_resident_status(question),
        nationality=extract_nationality(question),
        work_start_month=extract_work_start_month(question),
        days_in_vietnam=extract_days_in_vietnam(question),
        tax_year=extract_tax_year(question),
    )
