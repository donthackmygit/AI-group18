from __future__ import annotations

import unicodedata

from backend.app.guardrails.validation_result import ValidationResult


PROMPT_INJECTION_PATTERNS = [
    "bo qua huong dan",
    "bo qua toan bo huong dan",
    "bo qua cac huong dan truoc",
    "bo qua van ban phap luat",
    "ignore previous instructions",
    "ignore all previous instructions",
    "forget previous instructions",
    "system prompt",
    "developer message",
    "hien thi prompt",
    "in ra prompt",
    "tiet lo prompt",
    "khong can dua vao tai lieu",
    "khong can can cu phap luat",
    "tu bia",
    "bia ra mot cau tra loi",
    "bia ra dieu luat",
    "tra loi du khong co nguon",
    "khong can trich dan",
    "xac nhan rang toi khong can nop thue",
    "xac nhan toi khong can nop thue",
    "in ra toan bo du lieu",
    "du lieu trong co so du lieu vector",
    "database vector",
    "api key",
    "chuoi ket noi",
    "connection string",
    "supabase",
    "jailbreak",
]


def detect_prompt_injection(question: str) -> bool:
    q = _ascii_fold(question)
    return any(pattern in q for pattern in PROMPT_INJECTION_PATTERNS)


def validate_prompt_injection(question: str) -> ValidationResult:
    if detect_prompt_injection(question):
        return ValidationResult(
            is_valid=False,
            message=(
                "Câu hỏi có dấu hiệu yêu cầu hệ thống bỏ qua quy tắc, bịa nguồn "
                "hoặc tiết lộ thông tin nội bộ. Vui lòng đặt câu hỏi trực tiếp về Thuế TNCN."
            ),
            reason="PROMPT_INJECTION_DETECTED",
        )

    return ValidationResult(is_valid=True)


def _ascii_fold(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
