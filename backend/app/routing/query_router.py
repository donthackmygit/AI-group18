from __future__ import annotations

from backend.app.routing.route_rules import get_missing_fields_for_tax_calculation
from backend.app.schemas.query_route import (
    QueryClassificationResult,
    QueryIntent,
    QueryRoute,
    QueryRoutingResult,
)
from backend.app.schemas.question_processing import ExtractedEntities


MISSING_FIELD_LABELS = {
    "gross_income": "mức thu nhập/lương",
    "income_period": "thu nhập theo tháng hay theo năm",
    "resident_status": "tình trạng cư trú: cá nhân cư trú hay không cư trú",
    "mandatory_insurance": "số tiền bảo hiểm bắt buộc, nếu không đóng thì ghi 0",
    "dependents": "số người phụ thuộc, nếu không có thì ghi 0",
}


def route_query(
    classification: QueryClassificationResult,
    entities: ExtractedEntities,
) -> QueryRoutingResult:
    intent = classification.intent
    missing_fields = list(classification.missing_fields)

    if intent == QueryIntent.OUT_OF_SCOPE:
        return QueryRoutingResult(
            route=QueryRoute.REJECT,
            intent=intent,
            retrieval_required=False,
            tax_calculation_required=False,
            llm_required=False,
            reject_message="Câu hỏi này nằm ngoài phạm vi hỗ trợ về Thuế Thu nhập cá nhân.",
        )

    if intent == QueryIntent.UNCLEAR:
        return QueryRoutingResult(
            route=QueryRoute.CLARIFICATION_REQUIRED,
            intent=intent,
            retrieval_required=False,
            tax_calculation_required=False,
            llm_required=False,
            missing_fields=missing_fields,
            clarification_message=(
                "Bạn vui lòng nhập rõ câu hỏi liên quan đến Thuế Thu nhập cá nhân, "
                "ví dụ: cách tính thuế TNCN, giảm trừ gia cảnh, quyết toán thuế "
                "hoặc người phụ thuộc."
            ),
        )

    if intent == QueryIntent.TAX_CALCULATION:
        if "calculation_request" in classification.missing_fields:
            follow_up_fields = _missing_tax_context_fields(entities)
            return QueryRoutingResult(
                route=QueryRoute.CLARIFICATION_REQUIRED,
                intent=intent,
                retrieval_required=False,
                tax_calculation_required=False,
                llm_required=False,
                missing_fields=["calculation_request", *follow_up_fields],
                clarification_message=_build_tax_fact_collection_message(follow_up_fields),
            )

        missing_fields = get_missing_fields_for_tax_calculation(entities)

        if missing_fields:
            return QueryRoutingResult(
                route=QueryRoute.CLARIFICATION_REQUIRED,
                intent=intent,
                retrieval_required=False,
                tax_calculation_required=False,
                llm_required=False,
                missing_fields=missing_fields,
                clarification_message=_build_tax_calculation_clarification(missing_fields),
            )

        return QueryRoutingResult(
            route=QueryRoute.RAG_WITH_TAX_CALCULATION,
            intent=intent,
            retrieval_required=True,
            tax_calculation_required=True,
            llm_required=True,
            missing_fields=[],
        )

    if intent in {
        QueryIntent.LEGAL_LOOKUP,
        QueryIntent.DEFINITION,
        QueryIntent.PROCEDURE_GUIDE,
        QueryIntent.GENERAL_TNCN_QUERY,
    }:
        if "residency_context_fact" in classification.missing_fields:
            return QueryRoutingResult(
                route=QueryRoute.CLARIFICATION_REQUIRED,
                intent=intent,
                retrieval_required=False,
                tax_calculation_required=False,
                llm_required=False,
                missing_fields=["residency_context_fact"],
                clarification_message=_build_residency_fact_collection_message(entities),
            )

        return QueryRoutingResult(
            route=QueryRoute.RAG_ONLY,
            intent=intent,
            retrieval_required=True,
            tax_calculation_required=False,
            llm_required=True,
            missing_fields=missing_fields,
        )

    if intent == QueryIntent.FOLLOW_UP:
        return QueryRoutingResult(
            route=QueryRoute.CLARIFICATION_REQUIRED,
            intent=intent,
            retrieval_required=False,
            tax_calculation_required=False,
            llm_required=False,
            missing_fields=missing_fields,
            clarification_message=(
                "Bạn vui lòng nói rõ hơn câu hỏi trước đó hoặc cung cấp thêm thông tin cần thay đổi."
            ),
        )

    return QueryRoutingResult(
        route=QueryRoute.CLARIFICATION_REQUIRED,
        intent=intent,
        retrieval_required=False,
        tax_calculation_required=False,
        llm_required=False,
        missing_fields=missing_fields,
        clarification_message="Hệ thống chưa xác định được cách xử lý câu hỏi này.",
    )


def _build_tax_calculation_clarification(missing_fields: list[str]) -> str:
    labels = [MISSING_FIELD_LABELS.get(field, field) for field in missing_fields]
    return (
        "Để tính thuế TNCN chính xác, bạn vui lòng cung cấp thêm: "
        + "; ".join(labels)
        + "."
    )


def _missing_tax_context_fields(entities: ExtractedEntities) -> list[str]:
    missing: list[str] = []
    if entities.income is None:
        missing.append("gross_income")
    if entities.income_period is None:
        missing.append("income_period")
    if entities.insurance is None:
        missing.append("mandatory_insurance")
    if entities.dependents is None:
        missing.append("dependents")
    if entities.resident_status is None:
        missing.append("resident_status")
    return missing


def _build_tax_fact_collection_message(missing_fields: list[str]) -> str:
    if not missing_fields:
        return (
            "Mình đã ghi nhận các dữ kiện tính thuế. "
            "Khi cần tính, bạn hãy nhắn: Hãy tính thuế giúp tôi."
        )

    labels = [MISSING_FIELD_LABELS.get(field, field) for field in missing_fields]
    return (
        "Mình đã ghi nhận dữ kiện bạn vừa cung cấp. "
        "Để tính thuế đầy đủ hơn, bạn có thể cung cấp thêm: "
        + "; ".join(labels)
        + ". Khi đã đủ thông tin, hãy nhắn: Hãy tính thuế giúp tôi."
    )


def _build_residency_fact_collection_message(entities: ExtractedEntities) -> str:
    facts: list[str] = []
    if entities.work_start_month is not None:
        facts.append(f"bắt đầu làm việc tại Việt Nam từ tháng {entities.work_start_month}")
    if entities.nationality:
        facts.append(f"quốc tịch/người {entities.nationality}")
    if entities.days_in_vietnam is not None:
        facts.append(f"ở Việt Nam {entities.days_in_vietnam} ngày trong năm")

    if facts:
        return (
            "Mình đã ghi nhận dữ kiện xác định cư trú: "
            + "; ".join(facts)
            + ". Khi cần kết luận, bạn hãy hỏi: Vậy tôi thuộc diện cư trú nào?"
        )

    return (
        "Mình đã ghi nhận dữ kiện xác định cư trú. "
        "Khi cần kết luận, bạn hãy hỏi: Vậy tôi thuộc diện cư trú nào?"
    )
