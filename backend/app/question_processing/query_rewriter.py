from __future__ import annotations

from typing import Any

from backend.app.schemas.question_processing import ExtractedEntities


FOLLOW_UP_KEYWORDS = [
    "thế còn",
    "vậy còn",
    "nếu",
    "trường hợp",
    "còn nếu",
    "vậy nếu",
    "thì sao",
]


def is_follow_up_question(question: str) -> bool:
    q = question.casefold()
    return any(keyword in q for keyword in FOLLOW_UP_KEYWORDS)


def _format_vnd(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def rewrite_follow_up_question(
    current_question: str,
    current_entities: ExtractedEntities,
    conversation_context: dict[str, Any] | None,
) -> str:
    if not conversation_context or not is_follow_up_question(current_question):
        return current_question

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

    if insurance:
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
