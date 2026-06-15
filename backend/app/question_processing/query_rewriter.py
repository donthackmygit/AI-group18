from __future__ import annotations

from typing import Any
import unicodedata

from backend.app.schemas.question_processing import ExtractedEntities


FOLLOW_UP_KEYWORDS = [
    "thế còn",
    "vậy còn",
    "nếu",
    "trường hợp",
    "còn nếu",
    "vậy nếu",
    "thì sao",
    "hãy tính",
    "tính thuế",
    "tính giúp",
    "tính cho tôi",
    "vậy tôi",
]


def is_follow_up_question(question: str) -> bool:
    q = _ascii_fold(question)
    return any(_ascii_fold(keyword) in q for keyword in FOLLOW_UP_KEYWORDS)


def _ascii_fold(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _format_vnd(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def rewrite_follow_up_question(
    current_question: str,
    current_entities: ExtractedEntities,
    conversation_context: dict[str, Any] | None,
) -> str:
    if not conversation_context or not _should_rewrite_with_context(
        current_question,
        current_entities,
        conversation_context,
    ):
        return current_question

    if _is_residency_follow_up(current_question):
        return _rewrite_residency_question(current_question, current_entities, conversation_context)

    last_entities = conversation_context.get("last_entities", {})
    income = current_entities.income or last_entities.get("income")
    income_period = current_entities.income_period or last_entities.get("income_period")
    dependents = (
        current_entities.dependents
        if current_entities.dependents is not None
        else last_entities.get("dependents")
    )
    insurance = (
        current_entities.insurance
        if current_entities.insurance is not None
        else last_entities.get("insurance")
    )
    resident_status = current_entities.resident_status or last_entities.get("resident_status")

    parts: list[str] = []
    if income:
        period_text = " mỗi tháng" if income_period == "monthly" else ""
        period_text = " mỗi năm" if income_period == "yearly" else period_text
        parts.append(f"có thu nhập {_format_vnd(int(income))} đồng{period_text}")

    if insurance is not None:
        if int(insurance) == 0:
            parts.append("không đóng bảo hiểm bắt buộc")
        else:
            parts.append(f"đóng bảo hiểm {_format_vnd(int(insurance))} đồng")

    if dependents is not None:
        parts.append(f"có {dependents} người phụ thuộc")

    if resident_status == "non_resident":
        parts.append("là cá nhân không cư trú")
    elif resident_status == "resident":
        parts.append("là cá nhân cư trú")

    if parts:
        return "Người nộp thuế " + ", ".join(parts) + " thì phải nộp bao nhiêu thuế TNCN?"

    return current_question


def _should_rewrite_with_context(
    current_question: str,
    current_entities: ExtractedEntities,
    conversation_context: dict[str, Any],
) -> bool:
    if is_follow_up_question(current_question):
        return True

    q = _ascii_fold(current_question)
    asks_to_calculate = any(
        term in q
        for term in (
            "tinh thue",
            "tinh giup",
            "tinh cho toi",
            "phai nop bao nhieu",
            "so thue",
        )
    )
    has_new_numeric_context = any(
        value is not None
        for value in (
            current_entities.income,
            current_entities.insurance,
            current_entities.dependents,
        )
    )
    if asks_to_calculate and not has_new_numeric_context:
        return True

    last_entities = conversation_context.get("last_entities") or {}
    last_has_tax_context = any(
        last_entities.get(key) is not None
        for key in (
            "income",
            "income_period",
            "insurance",
            "dependents",
            "resident_status",
        )
    )
    has_new_tax_context = any(
        value is not None
        for value in (
            current_entities.income,
            current_entities.income_period,
            current_entities.insurance,
            current_entities.dependents,
            current_entities.resident_status,
        )
    )
    mentions_tax_context = any(
        term in q
        for term in (
            "bao hiem",
            "bhxh",
            "bhyt",
            "bhtn",
            "ca nhan cu tru",
            "khong cu tru",
            "cu tru",
            "nguoi phu thuoc",
            "npt",
            "luong",
            "thu nhap",
        )
    )
    return last_has_tax_context and has_new_tax_context and mentions_tax_context


def _is_residency_follow_up(question: str) -> bool:
    q = _ascii_fold(question)
    return any(
        term in q
        for term in (
            "thuoc dien cu tru",
            "cu tru nao",
            "xac dinh cu tru",
            "thue duoc tinh ra sao",
            "cu tru hay khong",
        )
    )


def _rewrite_residency_question(
    current_question: str,
    current_entities: ExtractedEntities,
    conversation_context: dict[str, Any],
) -> str:
    last_entities = conversation_context.get("last_entities", {})
    nationality = current_entities.nationality or last_entities.get("nationality")
    days = (
        current_entities.days_in_vietnam
        if current_entities.days_in_vietnam is not None
        else last_entities.get("days_in_vietnam")
    )
    start_month = (
        current_entities.work_start_month
        if current_entities.work_start_month is not None
        else last_entities.get("work_start_month")
    )

    parts = []
    if nationality:
        parts.append(f"là người {nationality}")
    if start_month:
        parts.append(f"làm việc tại Việt Nam từ tháng {start_month}")
    if days:
        parts.append(f"ở Việt Nam {days} ngày trong năm")

    if not parts:
        return current_question

    return (
        "Người nộp thuế "
        + ", ".join(parts)
        + " thì thuộc diện cá nhân cư trú hay không cư trú theo Thuế TNCN, "
        "và thuế thu nhập cá nhân được tính theo nguyên tắc nào?"
    )
