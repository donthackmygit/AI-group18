from __future__ import annotations

from backend.app.routing.route_rules import get_missing_fields_for_tax_calculation
from backend.app.schemas.query_route import (
    QueryClassificationResult,
    QueryIntent,
    QueryRoute,
    QueryRoutingResult,
)
from backend.app.schemas.question_processing import ExtractedEntities


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
                "ví dụ: cách tính thuế TNCN, giảm trừ gia cảnh, quyết toán thuế hoặc người phụ thuộc."
            ),
        )

    if intent == QueryIntent.TAX_CALCULATION:
        missing_fields = get_missing_fields_for_tax_calculation(entities)

        if "gross_income" in missing_fields:
            return QueryRoutingResult(
                route=QueryRoute.CLARIFICATION_REQUIRED,
                intent=intent,
                retrieval_required=False,
                tax_calculation_required=False,
                llm_required=False,
                missing_fields=missing_fields,
                clarification_message=(
                    "Bạn vui lòng cung cấp mức thu nhập để hệ thống có thể tính Thuế TNCN."
                ),
            )

        if "income_period" in missing_fields:
            return QueryRoutingResult(
                route=QueryRoute.CLARIFICATION_REQUIRED,
                intent=intent,
                retrieval_required=False,
                tax_calculation_required=False,
                llm_required=False,
                missing_fields=missing_fields,
                clarification_message=(
                    "Bạn vui lòng cho biết thu nhập là theo tháng hay theo năm."
                ),
            )

        return QueryRoutingResult(
            route=QueryRoute.RAG_WITH_TAX_CALCULATION,
            intent=intent,
            retrieval_required=True,
            tax_calculation_required=True,
            llm_required=True,
            missing_fields=missing_fields,
        )

    if intent in {
        QueryIntent.LEGAL_LOOKUP,
        QueryIntent.DEFINITION,
        QueryIntent.PROCEDURE_GUIDE,
    }:
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
