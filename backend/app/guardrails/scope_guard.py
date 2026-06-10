from __future__ import annotations

from backend.app.guardrails.validation_result import ValidationResult


TNCN_KEYWORDS = [
    "thuế thu nhập cá nhân",
    "thuế tncn",
    "tncn",
    "thu nhập cá nhân",
    "tiền lương",
    "tiền công",
    "lương",
    "thưởng",
    "phụ cấp",
    "giảm trừ gia cảnh",
    "người phụ thuộc",
    "bảo hiểm bắt buộc",
    "thu nhập chịu thuế",
    "thu nhập tính thuế",
    "quyết toán thuế",
    "mã số thuế",
    "khấu trừ thuế",
    "biểu thuế lũy tiến",
    "cư trú",
    "không cư trú",
    "hoàn thuế",
    "miễn thuế",
    "giảm trừ",
    "tính thuế",
    "nộp thuế",
    "thuế suất",
]

OUT_OF_SCOPE_KEYWORDS = [
    "thuế giá trị gia tăng",
    "vat",
    "gtgt",
    "thuế doanh nghiệp",
    "thuế tndn",
    "thuế xuất nhập khẩu",
    "thuế nhà đất",
    "thuế tiêu thụ đặc biệt",
    "bảo hiểm xã hội là gì",
    "hải quan",
    "hóa đơn điện tử",
]


def is_tncn_related(question: str) -> bool:
    q = question.casefold()
    return any(keyword in q for keyword in TNCN_KEYWORDS)


def is_clearly_out_of_scope(question: str) -> bool:
    q = question.casefold()
    return any(keyword in q for keyword in OUT_OF_SCOPE_KEYWORDS)


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
