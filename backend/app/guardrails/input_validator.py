from __future__ import annotations

import re
import unicodedata

from backend.app.guardrails.validation_result import ValidationResult


MIN_QUESTION_LENGTH = 3
MAX_QUESTION_LENGTH = 1000
WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text)
    return WHITESPACE_RE.sub(" ", normalized).strip()


def validate_basic_question(question: str | None) -> ValidationResult:
    if question is None:
        return ValidationResult(
            is_valid=False,
            message="Vui lòng nhập câu hỏi.",
            reason="QUESTION_NULL",
        )

    normalized = normalize_text(question)

    if not normalized:
        return ValidationResult(
            is_valid=False,
            message="Vui lòng nhập câu hỏi.",
            reason="QUESTION_EMPTY",
            normalized_question=normalized,
        )

    if len(normalized) < MIN_QUESTION_LENGTH:
        return ValidationResult(
            is_valid=False,
            message=(
                "Câu hỏi quá ngắn. Vui lòng nhập rõ nội dung cần hỏi về "
                "Thuế Thu nhập cá nhân."
            ),
            reason="QUESTION_TOO_SHORT",
            normalized_question=normalized,
        )

    if len(normalized) > MAX_QUESTION_LENGTH:
        return ValidationResult(
            is_valid=False,
            message="Câu hỏi quá dài. Vui lòng rút gọn nội dung cần hỏi.",
            reason="QUESTION_TOO_LONG",
            normalized_question=normalized,
        )

    alnum_count = sum(ch.isalnum() for ch in normalized)
    if alnum_count / max(len(normalized), 1) < 0.3:
        return ValidationResult(
            is_valid=False,
            message="Câu hỏi không hợp lệ. Vui lòng nhập lại bằng nội dung rõ ràng hơn.",
            reason="QUESTION_INVALID_CHARACTERS",
            normalized_question=normalized,
        )

    return ValidationResult(is_valid=True, normalized_question=normalized)
