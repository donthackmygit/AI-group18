from __future__ import annotations

import json

from backend.app.schemas.context import ContextBuildResult
from backend.app.schemas.prompt import (
    PromptBuilderStrategy,
    PromptBuildResult,
    PromptMessage,
)
from backend.app.schemas.question_processing import ProcessedQuestion
from backend.app.schemas.query_route import QueryClassificationResult, QueryRoutingResult
from backend.app.schemas.tax_calculation import TaxCalculationResult
from backend.app.services.context_builder_service import estimate_tokens


SYSTEM_INSTRUCTION = (
    "Bạn là trợ lý giải đáp Thuế Thu nhập cá nhân tại Việt Nam. "
    "Nhiệm vụ của bạn là giải thích quy định dựa trên tài liệu pháp luật được cung cấp, "
    "trình bày rõ ràng, có căn cứ, và không thay thế ý kiến của cơ quan thuế hoặc chuyên gia thuế."
)

BASE_ANSWER_RULES = [
    "Chỉ trả lời dựa trên tài liệu được cung cấp trong phần CONTEXT.",
    "Không tự tạo ra mức thuế, điều luật, khoản, điểm hoặc số hiệu văn bản.",
    "Nếu tài liệu không đủ để trả lời, hãy nói rõ rằng chưa tìm thấy đủ căn cứ pháp lý.",
    "Mỗi kết luận pháp lý cần đi kèm nguồn trích dẫn dạng [SOURCE_n].",
    "Ưu tiên văn bản đang có hiệu lực khi các nguồn có nội dung khác nhau.",
    "Không thay thế ý kiến của chuyên gia thuế hoặc cơ quan quản lý thuế.",
]

NO_CONTEXT_RULE = (
    "Nếu CONTEXT trống hoặc không có SOURCE phù hợp, không được suy đoán; "
    "hãy trả lời rằng hệ thống chưa tìm thấy đủ căn cứ pháp lý."
)

TAX_CALCULATION_RULE = (
    "Với câu hỏi tính toán, không tự quyết định toàn bộ số thuế khi chưa có kết quả từ "
    "Tax Calculation Service; chỉ giải thích căn cứ, công thức và thông tin còn thiếu nếu có."
)


class PromptBuilderService:
    def build(
        self,
        processed_question: ProcessedQuestion,
        classification: QueryClassificationResult,
        routing: QueryRoutingResult,
        context: ContextBuildResult | None,
        calculation: TaxCalculationResult | None = None,
    ) -> PromptBuildResult:
        context_text = _resolve_context_text(context)
        source_ids = _source_ids(context)
        answer_rules = _answer_rules(
            has_context=bool(source_ids),
            requires_tax_calculation=routing.tax_calculation_required,
        )
        output_format = _output_format(routing.tax_calculation_required)
        user_prompt = _build_user_prompt(
            processed_question=processed_question,
            classification=classification,
            routing=routing,
            context_text=context_text,
            source_ids=source_ids,
            answer_rules=answer_rules,
            output_format=output_format,
            calculation=calculation,
        )
        messages = [
            PromptMessage(role="system", content=SYSTEM_INSTRUCTION),
            PromptMessage(role="user", content=user_prompt),
        ]
        prompt_text = _messages_to_text(messages)

        return PromptBuildResult(
            strategy=PromptBuilderStrategy.STRUCTURED_MESSAGES,
            applied=True,
            input_question=processed_question.standalone_question,
            context_source_count=len(source_ids),
            source_ids=source_ids,
            requires_tax_calculation=routing.tax_calculation_required,
            estimated_tokens=sum(estimate_tokens(message.content) for message in messages),
            system_instruction=SYSTEM_INSTRUCTION,
            answer_rules=answer_rules,
            output_format=output_format,
            messages=messages,
            prompt_text=prompt_text,
            note=(
                "Prompt contains system instruction, user question, retrieved context, answer rules, "
                "and the expected JSON output format for the future LLM step."
            ),
        )


def _resolve_context_text(context: ContextBuildResult | None) -> str:
    if context and context.context_text.strip():
        return context.context_text.strip()
    return "NO_CONTEXT: Hệ thống chưa tìm thấy tài liệu truy xuất phù hợp."


def _source_ids(context: ContextBuildResult | None) -> list[str]:
    if not context:
        return []
    return [source.citation_id for source in context.sources]


def _answer_rules(has_context: bool, requires_tax_calculation: bool) -> list[str]:
    rules = list(BASE_ANSWER_RULES)
    if not has_context:
        rules.append(NO_CONTEXT_RULE)
    if requires_tax_calculation:
        rules.append(TAX_CALCULATION_RULE)
    return rules


def _output_format(requires_tax_calculation: bool) -> dict[str, object]:
    calculation_schema: object
    if requires_tax_calculation:
        calculation_schema = {
            "taxable_income": "number | null",
            "personal_deduction": "number | null",
            "dependent_deduction": "number | null",
            "tax_amount": "number | null",
            "calculation_steps": ["string"],
            "missing_fields": ["string"],
        }
    else:
        calculation_schema = None

    return {
        "answer": "string",
        "citations": [
            {
                "citation_id": "SOURCE_1",
                "document_number": "string | null",
                "article": "string | null",
                "clause": "string | null",
                "content_summary": "string",
            }
        ],
        "calculation": calculation_schema,
        "confidence": "low | medium | high",
        "warning": "string | null",
    }


def _build_user_prompt(
    processed_question: ProcessedQuestion,
    classification: QueryClassificationResult,
    routing: QueryRoutingResult,
    context_text: str,
    source_ids: list[str],
    answer_rules: list[str],
    output_format: dict[str, object],
    calculation: TaxCalculationResult | None,
) -> str:
    rules_text = "\n".join(f"{index}. {rule}" for index, rule in enumerate(answer_rules, start=1))
    source_text = ", ".join(source_ids) if source_ids else "Không có SOURCE hợp lệ."
    output_json = json.dumps(output_format, ensure_ascii=False, indent=2)
    entities_json = json.dumps(
        processed_question.entities.model_dump(exclude_none=True),
        ensure_ascii=False,
        indent=2,
    )
    calculation_text = _calculation_text(calculation)

    return "\n\n".join(
        [
            "CÂU HỎI NGƯỜI DÙNG:\n" + processed_question.standalone_question,
            "THÔNG TIN PHÂN TÍCH:\n"
            f"- Intent: {classification.intent.value}\n"
            f"- Topic: {processed_question.topic or classification.topic or 'Không xác định'}\n"
            f"- Route: {routing.route.value}\n"
            f"- Retrieval required: {routing.retrieval_required}\n"
            f"- Tax calculation required: {routing.tax_calculation_required}\n"
            f"- Missing fields: {', '.join(routing.missing_fields) if routing.missing_fields else 'Không có'}\n"
            f"- Entities:\n{entities_json}",
            "CONTEXT:\n" + context_text,
            "KẾT QUẢ TAX CALCULATION SERVICE:\n" + calculation_text,
            "SOURCE ĐƯỢC PHÉP TRÍCH DẪN:\n" + source_text,
            "QUY TẮC TRẢ LỜI:\n" + rules_text,
            "ĐỊNH DẠNG ĐẦU RA:\n"
            "Chỉ trả về một JSON object hợp lệ theo cấu trúc sau, không bọc trong Markdown:\n"
            + output_json,
        ]
    )


def _messages_to_text(messages: list[PromptMessage]) -> str:
    sections = []
    for message in messages:
        sections.append(f"[{message.role.upper()}]\n{message.content}")
    return "\n\n".join(sections)


def _calculation_text(calculation: TaxCalculationResult | None) -> str:
    if calculation is None:
        return "NO_CALCULATION: Route hiện tại không yêu cầu Tax Calculation Service."
    return json.dumps(
        calculation.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        indent=2,
    )
