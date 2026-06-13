from __future__ import annotations

import re
import unicodedata

from backend.app.question_processing.query_rewriter import is_follow_up_question
from backend.app.schemas.query_route import QueryClassificationResult, QueryIntent


OUT_OF_SCOPE_KEYWORDS = [
    "thue vat",
    "vat",
    "thue gia tri gia tang",
    "gtgt",
    "thue doanh nghiep",
    "thue tndn",
    "thue xuat nhap khau",
    "hai quan",
    "thue tieu thu dac biet",
    "thue nha dat",
    "gia bitcoin",
    "bitcoin hom nay",
    "thanh lap cong ty",
    "viet hop dong lao dong",
    "soan hop dong lao dong",
]

YES_NO_LEGAL_PATTERNS = [
    "co phai nop thue khong",
    "co phai nop thue",
    "co phai chiu thue khong",
    "co phai chiu thue",
    "co chiu thue khong",
    "chiu thue khong",
    "co duoc mien thue khong",
    "co duoc mien thue",
    "co tinh thue khong",
    "co bi tinh thue khong",
    "co bi khau tru khong",
    "co bi khau tru thue khong",
    "co phai quyet toan khong",
    "co can quyet toan khong",
    "co duoc hoan thue khong",
    "dung khong",
    "co dung la",
    "hay khong",
    "duoc xac dinh",
]

CALCULATION_ACTION_TERMS = [
    "tinh thue",
    "tinh giup",
    "hay tinh",
    "uoc tinh",
    "nop bao nhieu",
    "phai nop bao nhieu",
    "bao nhieu thue",
    "so thue phai nop",
    "thue tncn phai nop",
    "dong thue bao nhieu",
    "tinh theo tung bac",
    "trinh bay tung buoc",
]

CALCULATION_FACT_TERMS = [
    "luong",
    "luong gross",
    "luong net",
    "thu nhap",
    "thu nhap chiu thue",
    "thu nhap tinh thue",
    "bao hiem",
    "bhxh",
    "bhyt",
    "bhtn",
    "nguoi phu thuoc",
]

LEGAL_LOOKUP_KEYWORDS = [
    "quy dinh",
    "theo luat",
    "dieu luat",
    "dieu ",
    "khoan",
    "thong tu",
    "nghi dinh",
    "nghi quyet",
    "cong van",
    "van ban",
    "can cu phap ly",
    "nguon phap luat",
    "trich dan",
    "thue suat",
    "bieu thue",
    "mien thue",
    "khau tru",
    "hieu luc",
    "thay the",
    "hieu luc phap ly",
]

DEFINITION_KEYWORDS = [
    "la gi",
    "the nao la",
    "khai niem",
    "dinh nghia",
    "giai thich",
    "khac nhau nhu the nao",
    "so sanh",
]

PROCEDURE_KEYWORDS = [
    "thu tuc",
    "ho so",
    "cach dang ky",
    "dang ky nguoi phu thuoc",
    "quyet toan",
    "ke khai",
    "nop ho so",
    "lam the nao",
    "phai lam gi",
    "uy quyen",
    "chung tu khau tru",
]

PERSONAL_DEDUCTION_TERMS = [
    "giam tru gia canh",
    "muc giam tru",
    "giam tru cho ban than",
    "giam tru doi voi nguoi nop thue",
    "giam tru nguoi phu thuoc",
    "nguoi phu thuoc duoc giam",
]

RESIDENCY_FACT_TERMS = [
    "toi la nguoi",
    "quoc tich",
    "nguoi nhat",
    "nguoi nuoc ngoai",
    "lam viec tai viet nam tu thang",
    "lam viec o viet nam tu thang",
    "tong thoi gian o viet nam",
    "o viet nam nam nay",
]

RESIDENCY_QUESTION_TERMS = [
    "thuoc dien cu tru",
    "ca nhan cu tru",
    "ca nhan khong cu tru",
    "xac dinh cu tru",
    "cu tru nao",
    "thue duoc tinh ra sao",
]


def classify_query(
    question: str,
    has_conversation_context: bool = False,
) -> QueryClassificationResult:
    q = _ascii_fold(question).strip()

    if _contains_any(q, OUT_OF_SCOPE_KEYWORDS):
        return QueryClassificationResult(
            intent=QueryIntent.OUT_OF_SCOPE,
            confidence=0.95,
            reason="Detected out-of-scope tax or non-tax topic.",
        )

    if _is_residency_question(q):
        return QueryClassificationResult(
            intent=QueryIntent.LEGAL_LOOKUP,
            confidence=0.88,
            topic="Xác định tình trạng cư trú Thuế TNCN",
            reason="Detected residency status question.",
        )

    if _is_residency_fact_only(q):
        return QueryClassificationResult(
            intent=QueryIntent.GENERAL_TNCN_QUERY,
            confidence=0.78,
            topic="Dữ kiện xác định cư trú Thuế TNCN",
            missing_fields=["residency_context_fact"],
            reason="Detected residency context fact without an explicit question.",
        )

    if has_conversation_context and is_follow_up_question(q):
        return QueryClassificationResult(
            intent=QueryIntent.FOLLOW_UP,
            confidence=0.85,
            reason="Detected follow-up expression.",
        )

    if _is_personal_deduction_lookup(q):
        return QueryClassificationResult(
            intent=QueryIntent.LEGAL_LOOKUP,
            confidence=0.92,
            topic="Giảm trừ gia cảnh",
            reason="Detected legal lookup for family deduction amount.",
        )

    if _contains_any(q, YES_NO_LEGAL_PATTERNS):
        return QueryClassificationResult(
            intent=QueryIntent.LEGAL_LOOKUP,
            confidence=0.9,
            topic="Tra cứu nghĩa vụ Thuế TNCN",
            reason="Detected yes/no legal lookup pattern.",
        )

    if _is_tax_calculation_request(q):
        return QueryClassificationResult(
            intent=QueryIntent.TAX_CALCULATION,
            confidence=0.88,
            topic="Tính thuế TNCN",
            reason="Detected tax calculation request.",
        )

    if _is_tax_input_fact_only(q):
        return QueryClassificationResult(
            intent=QueryIntent.TAX_CALCULATION,
            confidence=0.78,
            topic="Dữ kiện tính thuế TNCN",
            missing_fields=["calculation_request"],
            reason="Detected tax input facts without an explicit calculation request.",
        )

    if _contains_any(q, PROCEDURE_KEYWORDS):
        return QueryClassificationResult(
            intent=QueryIntent.PROCEDURE_GUIDE,
            confidence=0.82,
            topic="Thủ tục Thuế TNCN",
        )

    if _contains_any(q, DEFINITION_KEYWORDS):
        return QueryClassificationResult(
            intent=QueryIntent.DEFINITION,
            confidence=0.82,
            topic="Khái niệm Thuế TNCN",
        )

    if _contains_any(q, LEGAL_LOOKUP_KEYWORDS):
        return QueryClassificationResult(
            intent=QueryIntent.LEGAL_LOOKUP,
            confidence=0.82,
            topic="Tra cứu quy định Thuế TNCN",
        )

    return QueryClassificationResult(
        intent=QueryIntent.GENERAL_TNCN_QUERY,
        confidence=0.6,
        topic="Thuế Thu nhập cá nhân",
        reason="TNCN-related question passed scope guard but did not match a specialized intent.",
    )


def _ascii_fold(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _contains_any(folded_text: str, keywords: list[str]) -> bool:
    return any(keyword in folded_text for keyword in keywords)


def _is_personal_deduction_lookup(folded_text: str) -> bool:
    return _contains_any(folded_text, PERSONAL_DEDUCTION_TERMS) and _contains_any(
        folded_text,
        ["bao nhieu", "muc", "quy dinh", "ban than", "moi thang", "mot thang", "mot nam"],
    )


def _is_tax_calculation_request(folded_text: str) -> bool:
    has_money = bool(re.search(r"\d+(?:[.,]\d+)?\s*(trieu|tr|dong|vnd)\b", folded_text))
    has_action = _contains_any(folded_text, CALCULATION_ACTION_TERMS)
    has_fact = _contains_any(folded_text, CALCULATION_FACT_TERMS)

    if has_action and (has_money or has_fact):
        return True

    if has_action and "thue" in folded_text:
        return True

    return False


def _is_tax_input_fact_only(folded_text: str) -> bool:
    has_money = bool(re.search(r"\d+(?:[.,]\d+)?\s*(trieu|tr|dong|vnd)\b", folded_text))
    has_fact = _contains_any(folded_text, CALCULATION_FACT_TERMS)

    # In multi-turn flows, users often provide facts without a question mark:
    # "Tôi có lương 35 triệu/tháng", "Tôi có hai người phụ thuộc".
    if has_money and has_fact:
        return True

    if has_fact and not folded_text.endswith("?") and not _contains_any(folded_text, LEGAL_LOOKUP_KEYWORDS):
        return True

    return False


def _is_residency_question(folded_text: str) -> bool:
    return _contains_any(folded_text, RESIDENCY_QUESTION_TERMS) and (
        "cu tru" in folded_text or "thue" in folded_text
    )


def _is_residency_fact_only(folded_text: str) -> bool:
    if folded_text.endswith("?"):
        return False
    return _contains_any(folded_text, RESIDENCY_FACT_TERMS)
