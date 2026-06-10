from __future__ import annotations

from backend.app.schemas.question_processing import ExtractedEntities


def build_retrieval_query(
    intent: str,
    topic: str | None,
    question: str,
    entities: ExtractedEntities,
) -> str:
    if intent == "TAX_CALCULATION":
        base = [
            "quy định tính thuế TNCN",
            "thu nhập từ tiền lương tiền công",
            "giảm trừ gia cảnh",
            "người phụ thuộc",
            "bảo hiểm bắt buộc",
            "thu nhập tính thuế",
            "biểu thuế lũy tiến từng phần",
        ]

        if entities.resident_status == "non_resident":
            base.append("cá nhân không cư trú")
        elif entities.resident_status == "resident":
            base.append("cá nhân cư trú")

        return " ".join(base)

    if intent == "LEGAL_LOOKUP":
        if topic:
            return f"quy định pháp luật về {topic} Thuế TNCN"
        return question

    if intent == "DEFINITION":
        if topic:
            return f"khái niệm định nghĩa {topic} trong Thuế TNCN"
        return question

    if intent == "PROCEDURE_GUIDE":
        if topic:
            return f"thủ tục hồ sơ hướng dẫn về {topic} Thuế TNCN"
        return f"thủ tục hồ sơ hướng dẫn Thuế TNCN {question}"

    return question
