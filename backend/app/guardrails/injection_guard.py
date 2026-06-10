from __future__ import annotations

from backend.app.guardrails.validation_result import ValidationResult


PROMPT_INJECTION_PATTERNS = [
    "bỏ qua hướng dẫn",
    "bỏ qua toàn bộ hướng dẫn",
    "bỏ qua các hướng dẫn trước",
    "ignore previous instructions",
    "ignore all previous instructions",
    "forget previous instructions",
    "system prompt",
    "developer message",
    "hiển thị prompt",
    "in ra prompt",
    "tiết lộ prompt",
    "không cần dựa vào tài liệu",
    "không cần căn cứ pháp luật",
    "hãy tự bịa",
    "bịa ra điều luật",
    "trả lời dù không có nguồn",
    "không cần trích dẫn",
    "jailbreak",
]


def detect_prompt_injection(question: str) -> bool:
    q = question.casefold()
    return any(pattern in q for pattern in PROMPT_INJECTION_PATTERNS)


def validate_prompt_injection(question: str) -> ValidationResult:
    if detect_prompt_injection(question):
        return ValidationResult(
            is_valid=False,
            message=(
                "Câu hỏi có dấu hiệu yêu cầu hệ thống bỏ qua quy tắc trả lời. "
                "Vui lòng đặt câu hỏi trực tiếp về Thuế Thu nhập cá nhân."
            ),
            reason="PROMPT_INJECTION_DETECTED",
        )

    return ValidationResult(is_valid=True)
