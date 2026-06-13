from __future__ import annotations

import unicodedata

from backend.app.guardrails.validation_result import ValidationResult


TNCN_SCOPE_TERMS = [
    "thu nhap ca nhan",
    "thue thu nhap ca nhan",
    "thue tncn",
    "tncn",
    "pit",
    "tien luong",
    "tien cong",
    "luong",
    "luong gross",
    "luong net",
    "thuong",
    "thuong tet",
    "phu cap",
    "lam them gio",
    "tang ca",
    "lam dem",
    "ban dem",
    "giam tru gia canh",
    "giam tru ban than",
    "nguoi phu thuoc",
    "npt",
    "bao hiem bat buoc",
    "bao hiem",
    "bhxh",
    "bhyt",
    "bhtn",
    "thu nhap chiu thue",
    "thu nhap tinh thue",
    "quyet toan",
    "quyet toan thue",
    "uy quyen quyet toan",
    "chung tu khau tru",
    "ma so thue",
    "khau tru",
    "khau tru thue",
    "bieu thue",
    "bieu thue luy tien",
    "thue suat",
    "cu tru",
    "khong cu tru",
    "ca nhan cu tru",
    "ca nhan khong cu tru",
    "nguoi nuoc ngoai",
    "nguoi nhat",
    "quoc tich",
    "lam viec tai viet nam",
    "o viet nam",
    "ngay trong nam",
    "hoan thue",
    "mien thue",
    "nop thue",
    "nop them thue",
    "tinh thue",
    "cho thue nha",
    "cho thue tai san",
    "ban nha",
    "can nha duy nhat",
    "freelance",
    "freelancer",
    "lao dong tu do",
    "hop dong dich vu",
    "hop dong thoi vu",
    "khong ky hop dong",
]

LEGAL_CONTEXT_TERMS = [
    "can cu phap ly",
    "nguon phap luat",
    "van ban phap luat",
    "van ban nao",
    "quy dinh",
    "hieu luc",
    "thay the",
    "nghi quyet",
    "luat",
    "nghi dinh",
    "thong tu",
    "cong van",
    "dieu ",
    "khoan",
    "trich dan",
    "co hieu luc",
    "hieu luc phap ly",
]

OUT_OF_SCOPE_TAX_TERMS = [
    "thue gia tri gia tang",
    "thue gtgt",
    "vat",
    "thue doanh nghiep",
    "thue tndn",
    "thue xuat nhap khau",
    "hai quan",
    "thue tieu thu dac biet",
    "thue nha dat",
    "hoa don dien tu",
]

NON_TAX_OUT_OF_SCOPE_TERMS = [
    "gia bitcoin",
    "bitcoin hom nay",
    "chung khoan",
    "thoi tiet",
    "bong da",
    "thanh lap cong ty",
    "tu van thanh lap cong ty",
    "viet hop dong lao dong",
    "soan hop dong lao dong",
    "mau hop dong lao dong",
]

SENSITIVE_OR_ILLEGAL_TERMS = [
    "api key",
    "supabase key",
    "connection string",
    "chuoi ket noi",
    "du lieu trong co so du lieu",
    "database vector",
    "co so du lieu vector",
    "tron thue",
    "khong bi phat hien",
]


def _ascii_fold(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _contains_any_folded(folded_text: str, keywords: list[str]) -> bool:
    return any(keyword in folded_text for keyword in keywords)


def is_tncn_related(question: str) -> bool:
    q = _ascii_fold(question)
    if _contains_any_folded(q, TNCN_SCOPE_TERMS):
        return True

    # Questions about cited legal instruments are allowed because the answer
    # still has to be grounded in the TNCN corpus and may need to say "not found".
    return _contains_any_folded(q, LEGAL_CONTEXT_TERMS) and not _contains_any_folded(
        q,
        NON_TAX_OUT_OF_SCOPE_TERMS,
    )


def is_clearly_out_of_scope(question: str) -> bool:
    q = _ascii_fold(question)
    return (
        _contains_any_folded(q, OUT_OF_SCOPE_TAX_TERMS)
        or _contains_any_folded(q, NON_TAX_OUT_OF_SCOPE_TERMS)
        or _contains_any_folded(q, SENSITIVE_OR_ILLEGAL_TERMS)
        or _is_contract_drafting_request(q)
    )


def _is_contract_drafting_request(folded_text: str) -> bool:
    return "hop dong lao dong" in folded_text and any(
        term in folded_text for term in ("viet", "soan", "mau", "lap hop dong")
    )


def validate_scope(question: str) -> ValidationResult:
    if is_clearly_out_of_scope(question):
        return ValidationResult(
            is_valid=False,
            message="Câu hỏi này nằm ngoài phạm vi hỗ trợ về Thuế Thu nhập cá nhân.",
            reason="OUT_OF_SCOPE",
        )

    if not is_tncn_related(question):
        return ValidationResult(
            is_valid=False,
            message=(
                "Hiện tại hệ thống chỉ hỗ trợ giải đáp về Thuế Thu nhập cá nhân. "
                "Vui lòng đặt câu hỏi liên quan đến Thuế TNCN."
            ),
            reason="UNKNOWN_SCOPE",
        )

    return ValidationResult(is_valid=True)
