from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
import logging
import re
import unicodedata
from statistics import mean
from time import perf_counter
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
from backend.app.repositories.monitoring_repository import MonitoringRepository
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
from backend.app.schemas.tax_calculation import TaxCalculationResult
from backend.app.services.embedding_service import EmbeddingService
from backend.app.services.context_builder_service import ContextBuilderService
from backend.app.services.llm_service import LLMService, LLMServiceError
from backend.app.services.prompt_builder_service import PromptBuilderService
from backend.app.services.reranker_service import RerankerService
from backend.app.services.response_formatter_service import ResponseFormatterService
from backend.app.services.response_validation_service import ResponseValidationService
from backend.app.services.supabase_auth_service import AuthenticatedUser, SupabaseAuthService
from backend.app.services.retriever_service import RetrieverService
from backend.app.services.tax_calculation_service import TaxCalculationService

logger = logging.getLogger(__name__)
_MONITORING_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="query-monitoring",
)


def shutdown_chat_workers() -> None:
    _MONITORING_EXECUTOR.shutdown(wait=True)

LLM_FALLBACK_WARNING = (
    "LLM chưa tạo được câu trả lời; hệ thống trả lời bằng nội dung trích xuất từ nguồn pháp luật."
)

SOURCE_VALIDATION_WARNING = (
    "Câu trả lời đã dựa trên nguồn tìm thấy, nhưng phần kiểm tra trích dẫn cần rà soát thêm."
)

PERSONAL_DEDUCTION_DOCUMENT_NUMBERS = {
    "109/2025/QH15",
    "954/2020/UBTVQH14",
}


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
        self.response_formatter = ResponseFormatterService(settings)
        self.conversation_store = ConversationMemoryStore()
        self.auth_service = SupabaseAuthService(settings)
        self.chat_history_repository = ChatHistoryRepository(settings)
        self.monitoring_repository = MonitoringRepository(settings)

    def warm_up(self) -> None:
        self.query_embedding_service.embedding_service.encode_query("thuế thu nhập cá nhân")

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
        stage_started = perf_counter()
        query_embedding = self.query_embedding_service.embed_query(
            processed_question=processed_question,
            classification=classification,
            routing=routing,
        )
        _log_stage_duration("query_embedding", stage_started)

        stage_started = perf_counter()
        retrieval_payload = self.retriever.retrieve_semantic(
            query_embedding=query_embedding.vector,
            top_k=top_k,
            filter_metadata=request.filter_metadata,
            status=request.status,
            effective_date=request.effective_date,
            topic_hint=processed_question.topic,
        )
        _log_stage_duration("retrieval", stage_started)

        stage_started = perf_counter()
        reranked_citations, reranking = self.reranker.rerank(
            citations=retrieval_payload.citations,
            processed_question=processed_question,
            classification=classification,
            top_k=rerank_top_k,
        )
        _log_stage_duration("reranking", stage_started)

        stage_started = perf_counter()
        context_payload = self.context_builder.build(
            citations=reranked_citations,
            max_tokens=context_max_tokens,
        )
        _log_stage_duration("context_build", stage_started)

        calculation = None
        if routing.tax_calculation_required:
            stage_started = perf_counter()
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
            _log_stage_duration("tax_calculation", stage_started)

        stage_started = perf_counter()
        prompt = self.prompt_builder.build(
            processed_question=processed_question,
            classification=classification,
            routing=routing,
            context=context_payload.result,
            calculation=calculation,
        )
        _log_stage_duration("prompt_build", stage_started)
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
        started_at = perf_counter()
        authenticated_user: AuthenticatedUser | None = None

        try:
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
                return self._persist_and_log_response(
                    request=request,
                    response=response,
                    authenticated_user=authenticated_user,
                    started_at=started_at,
                )

            conversation_context = self.conversation_store.get(request.conversation_id)
            processed_question = _apply_tax_input_overrides(
                process_question(
                    validation_result.normalized_question,
                    conversation_context=conversation_context,
                ),
                request,
            )
            processed_question = _merge_conversation_entities(
                processed_question,
                conversation_context,
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
                return self._persist_and_log_response(
                    request=request,
                    response=response,
                    authenticated_user=authenticated_user,
                    started_at=started_at,
                )

            if routing.route == QueryRoute.CLARIFICATION_REQUIRED:
                self.conversation_store.update(request.conversation_id, processed_question)
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
                return self._persist_and_log_response(
                    request=request,
                    response=response,
                    authenticated_user=authenticated_user,
                    started_at=started_at,
                )

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

            confidence = _retrieval_confidence(search_response.citations)

            if _should_answer_residency_deterministically(processed_question, routing):
                response = self.response_formatter.format_chat_response(
                    answer=_build_residency_answer(processed_question),
                    conversation_id=request.conversation_id,
                    mode="rule_based",
                    citations=search_response.citations,
                    confidence=confidence or classification.confidence,
                    warning=(
                        "Kết quả chỉ mang tính tham khảo, không thay thế ý kiến của cơ quan thuế "
                        "hoặc chuyên gia thuế."
                    ),
                    processed_question=processed_question,
                    classification=classification,
                    routing=routing,
                    query_embedding=search_response.query_embedding,
                    retrieval=search_response.retrieval,
                    reranking=search_response.reranking,
                    calculation=search_response.calculation,
                    context=search_response.context,
                    prompt=search_response.prompt,
                )
                return self._persist_and_log_response(
                    request=request,
                    response=response,
                    authenticated_user=authenticated_user,
                    started_at=started_at,
                )

            if search_response.prompt is None:
                raise RuntimeError("Prompt Builder did not produce a prompt for the LLM step.")

            response_mode = "llm"
            try:
                stage_started = perf_counter()
                llm_result = self.llm_service.generate(search_response.prompt)
                _log_stage_duration("llm_generate", stage_started)

                stage_started = perf_counter()
                response_validation = self.response_validation_service.validate(
                    llm_result=llm_result,
                    context=search_response.context,
                    calculation=search_response.calculation,
                    routing=routing,
                    effective_date=request.effective_date,
                )
                _log_stage_duration("response_validation", stage_started)
                if _has_valid_calculation(search_response.calculation):
                    answer = _build_calculation_answer(search_response.calculation)
                    validation_warning = response_validation.warning
                elif (
                    not response_validation.is_valid
                    and _should_replace_with_source_fallback(response_validation, llm_result)
                    and search_response.citations
                ):
                    response_mode = "llm_fallback"
                    answer = _build_source_review_answer(search_response.citations)
                    validation_warning = _merge_warning_text(
                        response_validation.warning,
                        SOURCE_VALIDATION_WARNING,
                    )
                elif not response_validation.is_valid:
                    answer = (
                        llm_result.answer
                        or llm_result.raw_text
                        or response_validation.safe_answer
                    )
                    validation_warning = _merge_warning_text(
                        response_validation.warning,
                        SOURCE_VALIDATION_WARNING,
                    )
                else:
                    answer = (
                        response_validation.safe_answer
                        or llm_result.answer
                        or llm_result.raw_text
                    )
                    validation_warning = response_validation.warning
                warning = _merge_warning_text(
                    llm_result.warning,
                    validation_warning,
                )

            except LLMServiceError as exc:
                response_mode = "llm_fallback"
                llm_result = None
                response_validation = None
                answer = _build_extractive_fallback_answer(
                    search_response.citations
                )
                logger.warning(
                    "LLM generation failed; using extractive fallback: %s",
                    exc,
                )
                warning = LLM_FALLBACK_WARNING

            response = self.response_formatter.format_chat_response(
                answer=answer,
                conversation_id=request.conversation_id,
                mode=response_mode,
                citations=search_response.citations,
                confidence=_validated_confidence(
                    confidence,
                    response_validation.is_valid if response_validation else True,
                    has_source_fallback=bool(search_response.citations),
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

            return self._persist_and_log_response(
                request=request,
                response=response,
                authenticated_user=authenticated_user,
                started_at=started_at,
            )

        except Exception as exc:
            self._safe_log_error(
                request=request,
                authenticated_user=authenticated_user,
                started_at=started_at,
                exc=exc,
            )
            raise

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

    def _persist_and_log_response(
        self,
        *,
        request: ChatRequest,
        response: ChatResponse,
        authenticated_user: AuthenticatedUser | None,
        started_at: float,
    ) -> ChatResponse:
        persisted_response = self._persist_assistant_response(
            response=response,
            authenticated_user=authenticated_user,
        )

        response_time_ms = int((perf_counter() - started_at) * 1000)

        self._schedule_query_log(
            request=request,
            response=persisted_response,
            user_id=authenticated_user.id if authenticated_user else None,
            response_time_ms=response_time_ms,
        )

        return persisted_response

    def _schedule_query_log(
        self,
        *,
        request: ChatRequest,
        response: ChatResponse,
        user_id: str | None,
        response_time_ms: int,
    ) -> None:
        _MONITORING_EXECUTOR.submit(
            self._insert_query_log_safely,
            request=request,
            response=response,
            user_id=user_id,
            response_time_ms=response_time_ms,
        )

    def _insert_query_log_safely(
        self,
        *,
        request: ChatRequest,
        response: ChatResponse,
        user_id: str | None,
        response_time_ms: int,
    ) -> None:
        try:
            self.monitoring_repository.insert_query_log(
                request=request,
                response=response,
                user_id=user_id,
                response_time_ms=response_time_ms,
            )
        except Exception:
            logger.exception("Failed to write query monitoring log")

    def _safe_log_error(
        self,
        *,
        request: ChatRequest,
        authenticated_user: AuthenticatedUser | None,
        started_at: float,
        exc: Exception,
    ) -> None:
        response_time_ms = int((perf_counter() - started_at) * 1000)

        try:
            self.monitoring_repository.insert_query_error(
                request=request,
                user_id=authenticated_user.id if authenticated_user else None,
                response_time_ms=response_time_ms,
                exc=exc,
            )
        except Exception:
            logger.exception("Failed to write query error monitoring log")

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


def _merge_conversation_entities(
    processed_question: ProcessedQuestion,
    conversation_context: dict | None,
) -> ProcessedQuestion:
    if not conversation_context:
        return processed_question

    last_entities = conversation_context.get("last_entities") or {}
    if not isinstance(last_entities, dict):
        return processed_question

    current_entities = processed_question.entities.model_dump()
    merged_entities = {
        key: current_entities.get(key) if current_entities.get(key) is not None else last_entities.get(key)
        for key in current_entities
    }
    if merged_entities == current_entities:
        return processed_question

    return processed_question.model_copy(
        update={
            "entities": processed_question.entities.model_copy(update=merged_entities),
        }
    )


def _retrieval_confidence(citations: list[Citation]) -> float | None:
    if not citations:
        return None

    similarities = [citation.similarity for citation in citations if citation.similarity is not None]
    if not similarities:
        return None

    best = max(similarities)
    average = mean(similarities)
    # Prefer the best legal source, but keep the average in the score so a
    # single lucky chunk cannot dominate the confidence completely.
    return (best * 0.65) + (average * 0.35)


def _validated_confidence(
    confidence: float | None,
    is_valid: bool,
    *,
    has_source_fallback: bool = False,
) -> float | None:
    if is_valid:
        return confidence
    if confidence is None:
        return 0.0
    if has_source_fallback:
        return max(min(confidence, 0.8), 0.55)
    return min(confidence, 0.3)


def _log_stage_duration(stage: str, started_at: float) -> None:
    elapsed_ms = int((perf_counter() - started_at) * 1000)
    if elapsed_ms >= 1000:
        logger.info("Chat pipeline stage '%s' took %sms", stage, elapsed_ms)
    else:
        logger.debug("Chat pipeline stage '%s' took %sms", stage, elapsed_ms)


def _merge_warning_text(*warnings: str | None) -> str | None:
    values = [warning.strip() for warning in warnings if warning and warning.strip()]
    if not values:
        return None
    return " | ".join(dict.fromkeys(values))


def _has_valid_calculation(calculation: TaxCalculationResult | None) -> bool:
    return bool(calculation and calculation.applied and calculation.tax_amount is not None)


def _should_answer_residency_deterministically(
    processed_question: ProcessedQuestion,
    routing: QueryRoutingResult,
) -> bool:
    if routing.tax_calculation_required:
        return False
    q = _ascii_fold(processed_question.standalone_question)
    return (
        processed_question.entities.days_in_vietnam is not None
        and "cu tru" in q
        and "thue" in q
    )


def _build_residency_answer(processed_question: ProcessedQuestion) -> str:
    entities = processed_question.entities
    days = entities.days_in_vietnam or 0
    is_resident = days >= 183
    status = "cá nhân cư trú" if is_resident else "cá nhân không cư trú"
    comparator = "từ 183 ngày trở lên" if is_resident else "dưới 183 ngày"

    details = []
    if entities.nationality:
        details.append(f"quốc tịch/người {entities.nationality}")
    if entities.work_start_month:
        details.append(f"làm việc tại Việt Nam từ tháng {entities.work_start_month}")
    details.append(f"có mặt tại Việt Nam {days} ngày trong năm")

    if is_resident:
        tax_rule = (
            "Về nguyên tắc, cá nhân cư trú chịu thuế TNCN theo biểu thuế lũy tiến từng phần "
            "đối với thu nhập từ tiền lương, tiền công sau khi trừ các khoản giảm trừ được áp dụng. "
            "Nếu muốn tính ra số tiền cụ thể, bạn cần cung cấp thu nhập, bảo hiểm bắt buộc, "
            "số người phụ thuộc và các khoản miễn/giảm trừ liên quan."
        )
    else:
        tax_rule = (
            "Về nguyên tắc, cá nhân không cư trú thường bị tính thuế theo thuế suất toàn phần "
            "đối với thu nhập phát sinh tại Việt Nam, không áp dụng giảm trừ gia cảnh như cá nhân cư trú."
        )

    return (
        "Dựa trên các dữ kiện đã cung cấp, bạn thuộc diện "
        f"{status}.\n\n"
        f"- Dữ kiện đã ghi nhận: {'; '.join(details)}.\n"
        f"- Lý do: thời gian có mặt tại Việt Nam là {days} ngày, tức {comparator} trong năm.\n"
        f"- Cách tính thuế: {tax_rule}"
    )


def _ascii_fold(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _should_replace_with_source_fallback(response_validation: object, llm_result: object) -> bool:
    answer = (getattr(llm_result, "answer", None) or getattr(llm_result, "raw_text", None) or "").strip()
    if not answer:
        return True

    fatal_issue_codes = {
        "EMPTY_ANSWER",
        "INVALID_CITATION_SOURCE",
        "SOURCE_NOT_YET_EFFECTIVE",
        "SOURCE_EXPIRED_AT_REQUESTED_DATE",
        "TAX_CALCULATION_MISMATCH",
    }
    issues = getattr(response_validation, "issues", []) or []
    return any(getattr(issue, "code", None) in fatal_issue_codes for issue in issues)


def _build_calculation_answer(calculation: TaxCalculationResult | None) -> str:
    if not _has_valid_calculation(calculation) or calculation is None:
        return "Hệ thống chưa có đủ dữ liệu để tính thuế TNCN."

    period_text = "tháng"
    if calculation.input and getattr(calculation.input.income_period, "value", calculation.input.income_period) == "yearly":
        period_text = "năm"

    lines = [
        "Mình tạm tính thuế TNCN theo kết quả Tax Calculation Service như sau:",
        f"- Thu nhập tính thuế sau giảm trừ: {_format_vnd(calculation.taxable_income or 0)} đồng/{period_text}.",
        f"- Giảm trừ bản thân: {_format_vnd(calculation.personal_deduction)} đồng/{period_text}.",
        f"- Giảm trừ người phụ thuộc: {_format_vnd(calculation.dependent_deduction)} đồng/{period_text}.",
    ]

    if calculation.mandatory_insurance:
        lines.insert(
            1,
            f"- Bảo hiểm bắt buộc đã trừ: {_format_vnd(calculation.mandatory_insurance)} đồng/{period_text}.",
        )

    if calculation.bracket_breakdown:
        lines.append("- Tính theo từng bậc:")
        for index, bracket in enumerate(calculation.bracket_breakdown, start=1):
            upper = (
                "trở lên"
                if bracket.upper_bound is None
                else f"đến {_format_vnd(bracket.upper_bound)} đồng"
            )
            lines.append(
                "  "
                f"Bậc {index}: {_format_vnd(bracket.taxable_amount)} đồng "
                f"({upper}) x {bracket.rate:.0%} = {_format_vnd(bracket.tax_amount)} đồng."
            )

    lines.append(
        f"=> Thuế TNCN tạm tính phải nộp: {_format_vnd(calculation.tax_amount or 0)} đồng/{period_text}."
    )
    return "\n".join(lines)


def _format_vnd(value: int) -> str:
    return f"{int(value):,}".replace(",", ".")


def _build_source_review_answer(citations: list[Citation]) -> str:
    if not citations:
        return "Hệ thống chưa tìm thấy đủ căn cứ pháp lý phù hợp để trả lời câu hỏi này."

    snippets = []
    for index, citation in enumerate(citations[:3], start=1):
        content = _compact_text(citation.content)
        if len(content) > 520:
            content = content[:520].rsplit(" ", 1)[0].rstrip() + "..."
        source_label = _source_label(citation)
        snippets.append(f"{index}. {source_label}: {content}")

    return (
        "Mình tìm thấy các đoạn tài liệu liên quan, nhưng phần kiểm tra trích dẫn của câu trả lời "
        "cần rà soát thêm. Nội dung tham khảo gần nhất:\n"
        + "\n".join(snippets)
        + "\n\nBạn nên đối chiếu phần nguồn tham khảo bên dưới trước khi dùng cho quyết định chính thức."
    )


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
        "LLM chưa tạo được câu trả lời. Dưới đây là nội dung pháp luật liên quan được "
        "trích xuất từ nguồn đã tìm thấy:\n"
        + "\n".join(snippets)
    )


def _personal_deduction_answer(citations: list[Citation]) -> str | None:
    preferred_citations = sorted(
        citations,
        key=_personal_deduction_sort_key,
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


def _personal_deduction_sort_key(citation: Citation) -> tuple[int, int, int, int]:
    status_rank = 0 if citation.status == "effective" else 1
    authority_rank = (
        0
        if citation.document_number in PERSONAL_DEDUCTION_DOCUMENT_NUMBERS
        else 1
    )
    effective_date_rank = -_date_ordinal(citation.effective_date)
    source_rank = citation.rerank_rank or citation.retrieval_rank or 9999

    return (
        status_rank,
        authority_rank,
        effective_date_rank,
        source_rank,
    )


def _date_ordinal(value: object) -> int:
    if isinstance(value, date):
        return value.toordinal()

    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value[:10]).toordinal()
        except ValueError:
            return 0

    return 0


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _source_label(citation: Citation) -> str:
    parts = [
        citation.document_number,
        citation.document_title,
        citation.article,
        citation.article_title,
    ]
    label = " - ".join(str(part).strip() for part in parts if part and str(part).strip())
    return label or citation.chunk_id or "Nguồn tham khảo"
