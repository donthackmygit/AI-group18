from __future__ import annotations

import re


def classify_intent(question: str) -> str:
    q = question.casefold()

    definition_keywords = [
        "là gì",
        "thế nào là",
        "giải thích",
        "khái niệm",
    ]
    legal_lookup_keywords = [
        "quy định",
        "điều kiện",
        "có phải chịu thuế không",
        "có chịu thuế không",
        "chịu thuế không",
        "miễn thuế",
        "khấu trừ",
        "quyết toán",
        "đăng ký người phụ thuộc",
        "mã số thuế",
        "thuế suất",
        "biểu thuế",
    ]
    procedure_keywords = [
        "thủ tục",
        "hồ sơ",
        "cách đăng ký",
        "đăng ký người phụ thuộc",
        "quyết toán",
        "kê khai",
        "nộp hồ sơ",
        "làm thế nào",
    ]
    legal_lookup_patterns = [
        r"chịu thuế.*không",
        r"có phải.*thuế.*không",
        r"có.*chịu thuế.*không",
    ]
    tax_calculation_keywords = [
        "tính thuế",
        "bao nhiêu thuế",
        "nộp bao nhiêu",
        "phải nộp",
        "lương",
        "thu nhập",
        "người phụ thuộc",
        "bảo hiểm",
        "thu nhập tính thuế",
        "thu nhập chịu thuế",
    ]

    if any(keyword in q for keyword in definition_keywords):
        return "DEFINITION"
    if any(re.search(pattern, q) for pattern in legal_lookup_patterns):
        return "LEGAL_LOOKUP"
    if any(keyword in q for keyword in procedure_keywords):
        return "PROCEDURE_GUIDE"
    if any(keyword in q for keyword in legal_lookup_keywords):
        return "LEGAL_LOOKUP"
    if any(keyword in q for keyword in tax_calculation_keywords):
        return "TAX_CALCULATION"
    return "GENERAL_TNCN_QUERY"


def detect_topic(question: str) -> str:
    q = question.casefold()

    if "giảm trừ gia cảnh" in q or "người phụ thuộc" in q:
        return "Giảm trừ gia cảnh"
    if "tiền lương" in q or "tiền công" in q or "lương" in q:
        return "Thu nhập từ tiền lương, tiền công"
    if "quyết toán" in q:
        return "Quyết toán thuế TNCN"
    if "hoàn thuế" in q:
        return "Hoàn thuế TNCN"
    if "không cư trú" in q or "cư trú" in q:
        return "Cá nhân cư trú và không cư trú"
    if "biểu thuế" in q or "thuế suất" in q or "lũy tiến" in q:
        return "Biểu thuế lũy tiến từng phần"
    if "miễn thuế" in q:
        return "Thu nhập miễn thuế"
    if "bảo hiểm" in q:
        return "Các khoản bảo hiểm bắt buộc"
    return "Thuế Thu nhập cá nhân"
