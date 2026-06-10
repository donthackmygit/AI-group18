from __future__ import annotations

import re
from statistics import mean

from backend.app.core.config import Settings
from backend.app.guardrails.chat_guardrail import validate_chat_question
from backend.app.guardrails.input_validator import normalize_text
from backend.app.guardrails.validation_logger import log_validation
from backend.app.guardrails.validation_result import ValidationResult
from backend.app.question_processing.memory import ConversationMemoryStore
from backend.app.question_processing.processor import process_question
from backend.app.question_processing.query_rewriter import is_follow_up_question
from backend.app.query_embedding.query_embedding_service import QueryEmbeddingService
from backend.app.repositories.chat_history_repository import ChatHistoryRepository
from backend.app.routing.query_classifier import classify_query
from backend.app.routing.query_router import route_query
from backend.app.schemas.rag import Citation, ChatRequest, ChatResponse, SearchRequest, SearchResponse
from backend.app.schemas.question_processing import ProcessedQuestion
from backend.app.schemas.query_route import (
    QueryClassificationResult,
    QueryIntent,
    QueryRoute,
    QueryRoutingResult,
)
from backend.app.services.embedding_service import EmbeddingService
from backend.app.services.context_builder_service import ContextBuilderService
from backend.app.services.llm_service import LLMService
from backend.app.services.prompt_builder_service import PromptBuilderService
from backend.app.services.reranker_service import RerankerService
from backend.app.services.response_formatter_service import ResponseFormatterService
from backend.app.services.response_validation_service import ResponseValidationService
from backend.app.services.supabase_auth_service import AuthenticatedUser, SupabaseAuthService
from backend.app.services.retriever_service import RetrieverService
from backend.app.services.tax_calculation_service import TaxCalculationService


LLM_FALLBACK_WARNING = (
    "Gemini không phản hồi kịp; hệ thống trả lời bằng nội dung trích xuất từ nguồn pháp luật."
)


class ChatGatewayService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        embedding_service = EmbeddingService(settings)
        self.query_embedding_service = QueryEmbeddingService(settings, embedding_service)
        self.retriever = RetrieverService(settings, embedding_service)
        self.reranker = RerankerService()
        self.context_builder = ContextBuilderService()
        self.prompt_builder = PromptBuilderService()
        self.tax_calculation_service = TaxCalculationService()
        self.llm_service = LLMService(settings)
        self.response_validation_service = ResponseValidationService()
        self.response_formatter = ResponseFormatterService()
        self.conversation_store = ConversationMemoryStore()
        self.auth_service = SupabaseAuthService(settings)
        self.chat_history_repository = ChatHistoryRepository(settings)

    def search(self, request: SearchRequest) -> SearchResponse:
        validation_result = self._run_guardrails(request)
        if not validation_result.is_valid:
            raise ValueError(f"{validation_result.reason}: {validation_result.message}")

        processed_question = _apply_tax_input_overrides(
            process_question(validation_result.normalized_question),
            request,
        )
        classification, routing = self._classify_and_route(processed_question, None)
        top_k = self._resolve_top_k(request.top_k)
        rerank_top_k = self._resolve_rerank_top_k(request.rerank_top_k, top_k)
        context_max_tokens = self._resolve_context_max_tokens(request.context_max_tokens)
        if not routing.retrieval_required:
            return SearchResponse(
                question=processed_question.standalone_question,
                top_k=top_k,
                citations=[],
                processed_question=processed_question,
                classification=classification,
                routing=routing,
                query_embedding=None,
                retrieval=None,
                reranking=None,
                calculation=None,
                context=None,
                prompt=None,
            )
        return self._search_valid_question(
            request=request,
            processed_question=processed_question,
            classification=classification,
            routing=routing,
            top_k=top_k,
            rerank_top_k=rerank_top_k,
            context_max_tokens=context_max_tokens,
        )

    def _search_valid_question(
        self,
        request: SearchRequest,
        processed_question: ProcessedQuestion,
        classification: QueryClassificationResult,
        routing: QueryRoutingResult,
        top_k: int,
        rerank_top_k: int,
        context_max_tokens: int,
    ) -> SearchResponse:
        query_embedding = self.query_embedding_service.embed_query(
            processed_question=processed_question,
            classification=classification,
            routing=routing,
        )
        retrieval_payload = self.retriever.retrieve_semantic(
            query_embedding=query_embedding.vector,
            top_k=top_k,
            filter_metadata=request.filter_metadata,
            status=request.status,
            effective_date=request.effective_date,
            topic_hint=processed_question.topic,
        )
        reranked_citations, reranking = self.reranker.rerank(
            citations=retrieval_payload.citations,
            processed_question=processed_question,
            classification=classification,
            top_k=rerank_top_k,
        )
        context_payload = self.context_builder.build(
            citations=reranked_citations,
            max_tokens=context_max_tokens,
        )
        calculation = None
        if routing.tax_calculation_required:
            calculation = self.tax_calculation_service.calculate_salary_tax(
                entities=processed_question.entities,
                effective_date=request.effective_date,
                gross_income=request.gross_income,
                income_period=request.income_period,
                mandatory_insurance=request.mandatory_insurance,
                tax_exempt_income=request.tax_exempt_income,
                dependents=request.dependents,
                charity_contributions=request.charity_contributions,
                other_deductions=request.other_deductions,
                resident_status=request.resident_status,
                tax_year=request.tax_year,
                contract_type=request.contract_type,
            )
        prompt = self.prompt_builder.build(
            processed_question=processed_question,
            classification=classification,
            routing=routing,
            context=context_payload.result,
            calculation=calculation,
        )
        return SearchResponse(
            question=processed_question.standalone_question,
            top_k=top_k,
            citations=context_payload.citations,
            processed_question=processed_question,
            classification=classification,
            routing=routing,
            query_embedding=query_embedding.result,
            retrieval=retrieval_payload.result,
            reranking=reranking,
            calculation=calculation,
            context=context_payload.result,
            prompt=prompt,
        )

    def chat(self, request: ChatRequest, authorization: str | None = None) -> ChatResponse:
        authenticated_user = self.auth_service.authenticate_authorization_header(authorization)
        self._assert_persistable_conversation(request, authenticated_user)

        validation_result = self._run_guardrails(request)
        if not validation_result.is_valid:
            classification, routing = self._route_guardrail_failure(validation_result)
            response = self.response_formatter.format_chat_response(
                answer=validation_result.message,
                conversation_id=request.conversation_id,
                mode="blocked",
                citations=[],
                confidence=0.0,
                warning=validation_result.reason,
                classification=classification,
                routing=routing,
            )
            return self._persist_assistant_response(response, authenticated_user)

        conversation_context = self.conversation_store.get(request.conversation_id)
        processed_question = _apply_tax_input_overrides(
            process_question(
                validation_result.normalized_question,
                conversation_context=conversation_context,
            ),
            request,
        )
        classification, routing = self._classify_and_route(processed_question, conversation_context)

        if routing.route == QueryRoute.REJECT:
            response = self.response_formatter.format_chat_response(
                answer=routing.reject_message or "Câu hỏi này nằm ngoài phạm vi hỗ trợ.",
                conversation_id=request.conversation_id,
                mode="rejected",
                citations=[],
                confidence=classification.confidence,
                warning=routing.route.value,
                processed_question=processed_question,
                classification=classification,
                routing=routing,
            )
            return self._persist_assistant_response(response, authenticated_user)

        if routing.route == QueryRoute.CLARIFICATION_REQUIRED:
            response = self.response_formatter.format_chat_response(
                answer=routing.clarification_message or "Bạn vui lòng cung cấp thêm thông tin.",
                conversation_id=request.conversation_id,
                mode="clarification_required",
                citations=[],
                confidence=classification.confidence,
                warning=routing.route.value,
                processed_question=processed_question,
                classification=classification,
                routing=routing,
            )
            return self._persist_assistant_response(response, authenticated_user)

        top_k = self._resolve_top_k(request.top_k)
        rerank_top_k = self._resolve_rerank_top_k(request.rerank_top_k, top_k)
        context_max_tokens = self._resolve_context_max_tokens(request.context_max_tokens)
        search_response = self._search_valid_question(
            request=request,
            processed_question=processed_question,
            classification=classification,
            routing=routing,
            top_k=top_k,
            rerank_top_k=rerank_top_k,
            context_max_tokens=context_max_tokens,
        )
        self.conversation_store.update(request.conversation_id, processed_question)
        confidence = (
            mean(citation.similarity for citation in search_response.citations)
            if search_response.citations
            else None
        )
        if search_response.prompt is None:
            raise RuntimeError("Prompt Builder did not produce a prompt for the LLM step.")
        response_mode = "llm"
        try:
            llm_result = self.llm_service.generate(search_response.prompt)
            response_validation = self.response_validation_service.validate(
                llm_result=llm_result,
                context=search_response.context,
                calculation=search_response.calculation,
                routing=routing,
            )
            answer = response_validation.safe_answer or llm_result.answer or llm_result.raw_text
            warning = _merge_warning_text(llm_result.warning, response_validation.warning)
        except Exception:
            response_mode = "llm_fallback"
            llm_result = None
            response_validation = None
            answer = _build_extractive_fallback_answer(search_response.citations)
            warning = LLM_FALLBACK_WARNING

        response = self.response_formatter.format_chat_response(
            answer=answer,
            conversation_id=request.conversation_id,
            mode=response_mode,
            citations=search_response.citations,
            confidence=_validated_confidence(
                confidence,
                response_validation.is_valid if response_validation else True,
            ),
            warning=warning,
            processed_question=processed_question,
            classification=classification,
            routing=routing,
            query_embedding=search_response.query_embedding,
            retrieval=search_response.retrieval,
            reranking=search_response.reranking,
            calculation=search_response.calculation,
            context=search_response.context,
            prompt=search_response.prompt,
            llm=llm_result,
            response_validation=response_validation,
        )
        return self._persist_assistant_response(response, authenticated_user)

    def _assert_persistable_conversation(
        self,
        request: ChatRequest,
        authenticated_user: AuthenticatedUser | None,
    ) -> None:
        if authenticated_user is None or not request.conversation_id:
            return
        self.chat_history_repository.assert_user_owns_conversation(
            conversation_id=request.conversation_id,
            user_id=authenticated_user.id,
        )

    def _persist_assistant_response(
        self,
        response: ChatResponse,
        authenticated_user: AuthenticatedUser | None,
    ) -> ChatResponse:
        if authenticated_user is None or not response.conversation_id:
            return response

        assistant_message_id = self.chat_history_repository.insert_assistant_message(
            conversation_id=response.conversation_id,
            user_id=authenticated_user.id,
            response=response,
        )
        return response.model_copy(update={"assistant_message_id": assistant_message_id})

    def _run_guardrails(self, request: SearchRequest) -> ValidationResult:
        validation_result = validate_chat_question(request.question)
        context = self.conversation_store.get(getattr(request, "conversation_id", None))
        if (
            not validation_result.is_valid
            and validation_result.reason == "UNKNOWN_SCOPE"
            and context
            and is_follow_up_question(normalize_text(request.question))
        ):
            validation_result = ValidationResult(
                is_valid=True,
                normalized_question=normalize_text(request.question),
            )

        log_validation(
            conversation_id=getattr(request, "conversation_id", None),
            original_question=request.question,
            result=validation_result,
        )
        return validation_result

    def _classify_and_route(
        self,
        processed_question: ProcessedQuestion,
        conversation_context: dict | None,
    ) -> tuple[QueryClassificationResult, QueryRoutingResult]:
        classification = classify_query(
            processed_question.standalone_question,
            has_conversation_context=conversation_context is not None,
        )
        if classification.intent != QueryIntent.FOLLOW_UP:
            processed_question.intent = classification.intent.value
        routing = route_query(classification, processed_question.entities)
        return classification, routing

    @staticmethod
    def _route_guardrail_failure(
        validation_result: ValidationResult,
    ) -> tuple[QueryClassificationResult, QueryRoutingResult]:
        intent = QueryIntent.OUT_OF_SCOPE if validation_result.reason == "OUT_OF_SCOPE" else QueryIntent.UNCLEAR
        classification = QueryClassificationResult(
            intent=intent,
            confidence=1.0,
            reason=validation_result.reason,
        )
        routing = route_query(
            classification,
            entities=ProcessedQuestion(
                original_question="",
                normalized_question=validation_result.normalized_question,
                standalone_question=validation_result.normalized_question,
                intent=intent.value,
                topic=None,
                entities={},
                retrieval_query=validation_result.normalized_question,
            ).entities,
        )
        return classification, routing

    def _resolve_top_k(self, top_k: int | None) -> int:
        value = top_k or self.settings.default_top_k
        if value < 1:
            raise ValueError("top_k must be greater than or equal to 1.")
        if value > self.settings.max_top_k:
            raise ValueError(f"top_k must be less than or equal to {self.settings.max_top_k}.")
        return value

    def _resolve_rerank_top_k(self, rerank_top_k: int | None, retrieval_top_k: int) -> int:
        value = rerank_top_k or self.settings.default_rerank_top_k
        if value < 1:
            raise ValueError("rerank_top_k must be greater than or equal to 1.")
        if value > self.settings.max_rerank_top_k:
            raise ValueError(
                f"rerank_top_k must be less than or equal to {self.settings.max_rerank_top_k}."
            )
        return min(value, retrieval_top_k)

    def _resolve_context_max_tokens(self, context_max_tokens: int | None) -> int:
        value = context_max_tokens or self.settings.default_context_max_tokens
        if value < 100:
            raise ValueError("context_max_tokens must be greater than or equal to 100.")
        if value > self.settings.max_context_tokens:
            raise ValueError(
                f"context_max_tokens must be less than or equal to {self.settings.max_context_tokens}."
            )
        return value


def _apply_tax_input_overrides(
    processed_question: ProcessedQuestion,
    request: SearchRequest,
) -> ProcessedQuestion:
    entity_updates = {}
    if request.gross_income is not None:
        entity_updates["income"] = request.gross_income
    if request.income_period is not None:
        entity_updates["income_period"] = request.income_period
    if request.mandatory_insurance is not None:
        entity_updates["insurance"] = request.mandatory_insurance
    if request.dependents is not None:
        entity_updates["dependents"] = request.dependents
    if request.resident_status is not None:
        entity_updates["resident_status"] = request.resident_status
    if request.tax_year is not None:
        entity_updates["tax_year"] = request.tax_year

    if not entity_updates:
        return processed_question

    return processed_question.model_copy(
        update={
            "entities": processed_question.entities.model_copy(update=entity_updates),
        }
    )


def _validated_confidence(confidence: float | None, is_valid: bool) -> float | None:
    if is_valid:
        return confidence
    if confidence is None:
        return 0.0
    return min(confidence, 0.3)


def _merge_warning_text(*warnings: str | None) -> str | None:
    values = [warning.strip() for warning in warnings if warning and warning.strip()]
    if not values:
        return None
    return " | ".join(dict.fromkeys(values))


def _build_extractive_fallback_answer(citations: list[Citation]) -> str:
    if not citations:
        return "Hệ thống chưa tìm thấy đủ căn cứ pháp lý phù hợp để trả lời câu hỏi này."

    personal_deduction_answer = _personal_deduction_answer(citations)
    if personal_deduction_answer:
        return personal_deduction_answer

    snippets = []
    for citation in citations[:2]:
        content = _compact_text(citation.content)
        if len(content) > 420:
            content = content[:420].rsplit(" ", 1)[0].rstrip() + "..."
        snippets.append(f"- {content} [{citation.citation_id}]")

    return (
        "Gemini chưa phản hồi kịp. Dưới đây là nội dung pháp luật liên quan được "
        "trích xuất từ nguồn đã tìm thấy:\n"
        + "\n".join(snippets)
    )


def _personal_deduction_answer(citations: list[Citation]) -> str | None:
    preferred_citations = sorted(
        citations,
        key=lambda citation: 0 if citation.document_number == "954/2020/UBTVQH14" else 1,
    )
    for citation in preferred_citations:
        content = _compact_text(citation.content)
        personal_match = re.search(
            r"Mức giảm trừ đối với (?:đối tượng nộp thuế|người nộp thuế)\s+là\s+([^;.\n]+(?:\([^)]+\))?)",
            content,
            flags=re.IGNORECASE,
        )
        if not personal_match:
            continue

        answer = (
            "Mức giảm trừ gia cảnh cho bản thân người nộp thuế là "
            f"{personal_match.group(1).strip()} [{citation.citation_id}]."
        )
        dependent_match = re.search(
            r"Mức giảm trừ đối với mỗi người phụ thuộc\s+là\s+([^;.\n]+)",
            content,
            flags=re.IGNORECASE,
        )
        if dependent_match:
            answer += (
                " Mức giảm trừ đối với mỗi người phụ thuộc là "
                f"{dependent_match.group(1).strip()} [{citation.citation_id}]."
            )
        return answer

    return None


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
