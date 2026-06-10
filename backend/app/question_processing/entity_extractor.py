from __future__ import annotations

import re

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


def parse_money_to_vnd(text: str) -> int | None:
    q = text.casefold()

    million_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(triệu|tr)\b", q)
    if million_match:
        return int(_parse_decimal(million_match.group(1)) * 1_000_000)

    vnd_match = re.search(r"(\d[\d.,]{5,})\s*(đồng|vnd|vnđ)?\b", q)
    if vnd_match:
        return _parse_integer_digits(vnd_match.group(1))

    return None


def extract_income(text: str) -> int | None:
    q = text.casefold()
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
        before = q[max(0, match.start() - 25) : match.start()]
        if "bảo hiểm" not in before and "bhxh" not in before and "bhyt" not in before and "bhtn" not in before:
            return int(_parse_decimal(match.group(1)) * 1_000_000)

    insurance_terms = ("bảo hiểm", "bhxh", "bhyt", "bhtn")
    if not any(term in q for term in insurance_terms):
        return parse_money_to_vnd(q)
    return None


def extract_dependents(text: str) -> int | None:
    q = text.casefold()
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
    q = text.casefold()
    patterns = [
        r"(?:bảo hiểm|đóng bảo hiểm|bhxh|bhyt|bhtn)\D{0,20}(\d+(?:[.,]\d+)?)\s*(triệu|tr)\b",
        r"(?:bảo hiểm|đóng bảo hiểm|bhxh|bhyt|bhtn)\D{0,20}(\d[\d.,]{5,})\s*(đồng|vnd|vnđ)?\b",
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
    q = text.casefold()
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
    q = text.casefold()
    if "không cư trú" in q:
        return "non_resident"
    if "cư trú" in q:
        return "resident"
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
        tax_year=extract_tax_year(question),
    )
