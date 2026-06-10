from __future__ import annotations

import unicodedata

from backend.app.question_processing.query_rewriter import is_follow_up_question
from backend.app.schemas.query_route import QueryClassificationResult, QueryIntent


OUT_OF_SCOPE_KEYWORDS = [
    "thuế vat",
    "vat",
    "thuế giá trị gia tăng",
    "gtgt",
    "thuế doanh nghiệp",
    "thuế tndn",
    "thuế xuất nhập khẩu",
    "hải quan",
    "thuế tiêu thụ đặc biệt",
    "thuế nhà đất",
    "bảo hiểm xã hội là gì",
    "thời tiết",
    "bóng đá",
    "chứng khoán",
]

YES_NO_LEGAL_PATTERNS = [
    "có phải nộp thuế không",
    "có phải nộp thuế",
    "có phải chịu thuế không",
    "có phải chịu thuế",
    "có chịu thuế không",
    "có chịu thuế",
    "chịu thuế không",
    "có được miễn thuế không",
    "có được miễn thuế",
]

TAX_CALCULATION_KEYWORDS = [
    "tính thuế",
    "nộp bao nhiêu",
    "phải nộp bao nhiêu",
    "bao nhiêu thuế",
    "số thuế",
    "lương",
    "thu nhập",
    "triệu",
    "người phụ thuộc",
    "bảo hiểm",
    "giảm trừ",
]

LEGAL_LOOKUP_KEYWORDS = [
    "quy định",
    "theo luật",
    "điều luật",
    "điều ",
    "khoản",
    "thông tư",
    "nghị định",
    "thuế suất",
    "biểu thuế",
    "miễn thuế",
    "khấu trừ",
]

DEFINITION_KEYWORDS = [
    "là gì",
    "thế nào là",
    "khái niệm",
    "định nghĩa",
    "giải thích",
]

PROCEDURE_KEYWORDS = [
    "thủ tục",
    "hồ sơ",
    "cách đăng ký",
    "đăng ký người phụ thuộc",
    "quyết toán",
    "kê khai",
    "nộp hồ sơ",
    "làm thế nào",
]


def contains_any(text: str, keywords: list[str]) -> bool:
    q = text.casefold()
    return any(keyword in q for keyword in keywords)


def _ascii_fold(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _is_personal_deduction_lookup(text: str) -> bool:
    q = _ascii_fold(text)
    deduction_terms = (
        "giam tru gia canh",
        "muc giam tru",
        "giam tru cho ban than",
        "giam tru doi voi nguoi nop thue",
        "giam tru nguoi phu thuoc",
    )
    lookup_terms = (
        "bao nhieu",
        "muc",
        "quy dinh",
        "ban than",
        "nguoi phu thuoc",
        "moi thang",
        "mot thang",
        "mot nam",
    )
    return any(term in q for term in deduction_terms) and any(term in q for term in lookup_terms)


def classify_query(
    question: str,
    has_conversation_context: bool = False,
) -> QueryClassificationResult:
    q = question.casefold().strip()

    if contains_any(q, OUT_OF_SCOPE_KEYWORDS):
        return QueryClassificationResult(
            intent=QueryIntent.OUT_OF_SCOPE,
            confidence=0.95,
            reason="Detected out-of-scope tax or non-tax topic.",
        )

    if has_conversation_context and is_follow_up_question(q):
        return QueryClassificationResult(
            intent=QueryIntent.FOLLOW_UP,
            confidence=0.85,
            reason="Detected follow-up expression.",
        )

    if contains_any(q, YES_NO_LEGAL_PATTERNS):
        return QueryClassificationResult(
            intent=QueryIntent.LEGAL_LOOKUP,
            confidence=0.9,
            topic="Tra cứu nghĩa vụ Thuế TNCN",
            reason="Detected yes/no legal lookup pattern.",
        )

    if contains_any(q, PROCEDURE_KEYWORDS):
        return QueryClassificationResult(
            intent=QueryIntent.PROCEDURE_GUIDE,
            confidence=0.8,
            topic="Thủ tục Thuế TNCN",
        )

    if _is_personal_deduction_lookup(q):
        return QueryClassificationResult(
            intent=QueryIntent.LEGAL_LOOKUP,
            confidence=0.9,
            topic="Giảm trừ gia cảnh",
            reason="Detected legal lookup for personal deduction amount.",
        )

    if contains_any(q, DEFINITION_KEYWORDS):
        return QueryClassificationResult(
            intent=QueryIntent.DEFINITION,
            confidence=0.8,
            topic="Khái niệm Thuế TNCN",
        )

    if contains_any(q, LEGAL_LOOKUP_KEYWORDS):
        return QueryClassificationResult(
            intent=QueryIntent.LEGAL_LOOKUP,
            confidence=0.8,
            topic="Tra cứu quy định Thuế TNCN",
        )

    if contains_any(q, TAX_CALCULATION_KEYWORDS):
        return QueryClassificationResult(
            intent=QueryIntent.TAX_CALCULATION,
            confidence=0.85,
            topic="Tính thuế TNCN",
        )

    return QueryClassificationResult(
        intent=QueryIntent.UNCLEAR,
        confidence=0.4,
        reason="Could not confidently classify query.",
    )
