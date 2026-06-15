from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import Settings
from backend.app.question_processing.entity_extractor import extract_entities
from backend.app.question_processing.memory import ConversationMemoryStore
from backend.app.question_processing.processor import process_question
from backend.app.repositories.chat_history_repository import _conversation_context_from_metadata
from backend.app.routing.query_classifier import classify_query
from backend.app.routing.query_router import route_query
from backend.app.schemas.context import ContextBuilderStrategy, ContextBuildResult
from backend.app.schemas.llm import LLMGenerationResult, LLMProvider
from backend.app.schemas.query_embedding import QueryEmbeddingResult
from backend.app.schemas.query_route import QueryIntent, QueryRoute
from backend.app.schemas.question_processing import ExtractedEntities
from backend.app.services.chat_service import _merge_conversation_entities
from backend.app.services.response_formatter_service import ResponseFormatterService
from backend.app.services.tax_calculation_service import TaxCalculationService
from scripts.chunker import MAX_CHARS_PER_CHUNK, OVERLAP_TOKENS, split_plain_text, token_tail


VND = int


def vi(value: str) -> str:
    return value.encode("ascii").decode("unicode_escape")


def assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_true(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)


def assert_in(item: Any, values: Any, label: str) -> None:
    if item not in values:
        raise AssertionError(f"{label}: {item!r} not found in {values!r}")


def route(question: str, context: dict[str, Any] | None = None):
    processed = process_question(question, conversation_context=context)
    processed = _merge_conversation_entities(processed, context)
    classification = classify_query(
        processed.standalone_question,
        has_conversation_context=context is not None,
    )
    routing = route_query(classification, processed.entities)
    return processed, classification, routing


def test_entity_extraction() -> None:
    entities = extract_entities(
        vi("L\\u01b0\\u01a1ng gross 45tr/th\\u00e1ng, BHXH 4.5tr, c\\u00f3 1 ng\\u01b0\\u1eddi ph\\u1ee5 thu\\u1ed9c")
    )
    assert_equal(entities.income, VND(45_000_000), "extract gross salary")
    assert_equal(entities.income_period, "monthly", "extract monthly period")
    assert_equal(entities.insurance, VND(4_500_000), "extract decimal insurance")
    assert_equal(entities.dependents, 1, "extract dependents")

    entities = extract_entities(
        vi("Kh\\u00f4ng \\u0111\\u00f3ng b\\u1ea3o hi\\u1ec3m, kh\\u00f4ng c\\u00f3 ng\\u01b0\\u1eddi ph\\u1ee5 thu\\u1ed9c, c\\u00e1 nh\\u00e2n c\\u01b0 tr\\u00fa")
    )
    assert_equal(entities.insurance, 0, "extract zero insurance")
    assert_equal(entities.dependents, 0, "extract zero dependents")
    assert_equal(entities.resident_status, "resident", "extract resident status")

    entities = extract_entities(
        vi("T\\u00f4i l\\u00e0 ng\\u01b0\\u1eddi Nh\\u1eadt, l\\u00e0m vi\\u1ec7c t\\u1ea1i Vi\\u1ec7t Nam t\\u1eeb th\\u00e1ng 7, \\u1edf Vi\\u1ec7t Nam 120 ng\\u00e0y")
    )
    assert_equal(entities.nationality, vi("Nh\\u1eadt"), "extract nationality")
    assert_equal(entities.work_start_month, 7, "extract work start month")
    assert_equal(entities.days_in_vietnam, 120, "extract days in Vietnam")
    assert_equal(entities.resident_status, "non_resident", "derive non-resident from days")


def test_single_turn_routing() -> None:
    processed, classification, routing = route(
        vi("L\\u01b0\\u01a1ng 30 tri\\u1ec7u m\\u1ed7i th\\u00e1ng, c\\u00f3 2 ng\\u01b0\\u1eddi ph\\u1ee5 thu\\u1ed9c th\\u00ec n\\u1ed9p thu\\u1ebf TNCN bao nhi\\u00eau?")
    )
    assert_equal(classification.intent, QueryIntent.TAX_CALCULATION, "salary question intent")
    assert_equal(routing.route, QueryRoute.CLARIFICATION_REQUIRED, "salary question route")
    assert_equal(set(routing.missing_fields), {"mandatory_insurance", "resident_status"}, "salary missing fields")
    assert_equal(processed.entities.income, VND(30_000_000), "salary income")
    assert_equal(processed.entities.dependents, 2, "salary dependents")

    _, classification, routing = route(
        vi("L\\u01b0\\u01a1ng 30 tri\\u1ec7u/th\\u00e1ng, b\\u1ea3o hi\\u1ec3m 5 tri\\u1ec7u, 2 ng\\u01b0\\u1eddi ph\\u1ee5 thu\\u1ed9c, c\\u00e1 nh\\u00e2n c\\u01b0 tr\\u00fa, n\\u1ed9p thu\\u1ebf bao nhi\\u00eau?")
    )
    assert_equal(classification.intent, QueryIntent.TAX_CALCULATION, "complete salary intent")
    assert_equal(routing.route, QueryRoute.RAG_WITH_TAX_CALCULATION, "complete salary route")

    _, classification, routing = route(
        vi("M\\u1ee9c gi\\u1ea3m tr\\u1eeb gia c\\u1ea3nh cho b\\u1ea3n th\\u00e2n l\\u00e0 bao nhi\\u00eau?")
    )
    assert_equal(classification.intent, QueryIntent.LEGAL_LOOKUP, "personal deduction intent")
    assert_equal(routing.route, QueryRoute.RAG_ONLY, "personal deduction route")

    _, classification, routing = route(vi("Thu\\u1ebf VAT cho h\\u00f3a \\u0111\\u01a1n n\\u00e0y l\\u00e0 bao nhi\\u00eau?"))
    assert_equal(classification.intent, QueryIntent.OUT_OF_SCOPE, "VAT intent")
    assert_equal(routing.route, QueryRoute.REJECT, "VAT reject route")

    _, _, routing = route(
        vi("S\\u1ed1 ti\\u1ec1n b\\u1ea3o hi\\u1ec3m b\\u1eaft bu\\u1ed9c: 5 tri\\u1ec7u. C\\u00e1 nh\\u00e2n c\\u01b0 tr\\u00fa")
    )
    assert_equal(routing.route, QueryRoute.CLARIFICATION_REQUIRED, "fact-only route without context")


def test_multi_turn_tax_flows() -> None:
    store = ConversationMemoryStore()
    conversation_id = "smoke"

    first, _, routing = route(
        vi("L\\u01b0\\u01a1ng 30 tri\\u1ec7u m\\u1ed7i th\\u00e1ng, c\\u00f3 2 ng\\u01b0\\u1eddi ph\\u1ee5 thu\\u1ed9c th\\u00ec n\\u1ed9p thu\\u1ebf TNCN bao nhi\\u00eau?")
    )
    assert_equal(routing.route, QueryRoute.CLARIFICATION_REQUIRED, "initial missing info route")
    store.update(conversation_id, first)

    context = store.get(conversation_id)
    second, classification, routing = route(
        vi("S\\u1ed1 ti\\u1ec1n b\\u1ea3o hi\\u1ec3m b\\u1eaft bu\\u1ed9c: 5 tri\\u1ec7u. C\\u00e1 nh\\u00e2n c\\u01b0 tr\\u00fa"),
        context,
    )
    assert_equal(classification.intent, QueryIntent.TAX_CALCULATION, "follow-up completion intent")
    assert_equal(routing.route, QueryRoute.RAG_WITH_TAX_CALCULATION, "follow-up completion route")
    assert_equal(second.entities.income, VND(30_000_000), "follow-up carries income")
    assert_equal(second.entities.insurance, VND(5_000_000), "follow-up carries insurance")
    assert_equal(second.entities.dependents, 2, "follow-up carries dependents")
    assert_equal(second.entities.resident_status, "resident", "follow-up carries resident status")

    result = TaxCalculationService().calculate_salary_tax(entities=second.entities)
    assert_equal(result.applied, True, "follow-up calculation applied")
    assert_equal(result.taxable_income, 0, "follow-up taxable income")
    assert_equal(result.tax_amount, 0, "follow-up tax amount")

    store = ConversationMemoryStore()
    first, _, routing = route(vi("T\\u00f4i c\\u00f3 l\\u01b0\\u01a1ng 35 tri\\u1ec7u/th\\u00e1ng"))
    assert_equal(routing.route, QueryRoute.CLARIFICATION_REQUIRED, "fact-only salary route")
    store.update(conversation_id, first)
    second, _, routing = route(
        vi("Kh\\u00f4ng \\u0111\\u00f3ng b\\u1ea3o hi\\u1ec3m, 0 ng\\u01b0\\u1eddi ph\\u1ee5 thu\\u1ed9c, c\\u00e1 nh\\u00e2n c\\u01b0 tr\\u00fa"),
        store.get(conversation_id),
    )
    assert_equal(routing.route, QueryRoute.RAG_WITH_TAX_CALCULATION, "zero follow-up route")
    assert_equal(second.entities.insurance, 0, "zero follow-up keeps insurance")
    assert_equal(second.entities.dependents, 0, "zero follow-up keeps dependents")
    result = TaxCalculationService().calculate_salary_tax(entities=second.entities)
    assert_equal(result.tax_amount, VND(1_450_000), "zero follow-up 2026 tax amount")


def test_tax_calculation_numbers() -> None:
    service = TaxCalculationService()

    result = service.calculate_salary_tax(
        entities=ExtractedEntities(
            income=30_000_000,
            income_period="monthly",
            dependents=2,
            insurance=5_000_000,
            resident_status="resident",
        ),
    )
    assert_equal(result.rule_id, "pit_salary_resident_progressive_2026", "2026 rule")
    assert_equal(result.tax_amount, VND(0), "2026 resident 30M tax")

    result = service.calculate_salary_tax(
        entities=ExtractedEntities(
            income=30_000_000,
            income_period="monthly",
            dependents=2,
            insurance=5_000_000,
            resident_status="resident",
            tax_year=2025,
        ),
    )
    assert_equal(result.rule_id, "pit_salary_resident_progressive_2020_2025", "2025 rule")
    assert_equal(result.taxable_income, VND(5_200_000), "2025 taxable income")
    assert_equal(result.tax_amount, VND(270_000), "2025 resident 30M tax")

    result = service.calculate_salary_tax(
        entities=ExtractedEntities(
            income=30_000_000,
            income_period="monthly",
            dependents=2,
            insurance=5_000_000,
            resident_status="non_resident",
        ),
    )
    assert_equal(result.tax_amount, VND(6_000_000), "non-resident flat tax")

    result = service.calculate_salary_tax(
        entities=ExtractedEntities(
            income=600_000_000,
            income_period="yearly",
            dependents=0,
            insurance=0,
            resident_status="resident",
        ),
    )
    assert_equal(result.taxable_income, VND(414_000_000), "yearly taxable income")
    assert_equal(result.tax_amount, VND(40_800_000), "yearly progressive tax")


def test_metadata_context_restore() -> None:
    context = _conversation_context_from_metadata(
        {
            "processed_question": {
                "standalone_question": "salary question",
                "intent": "TAX_CALCULATION",
                "topic": "TAX",
                "entities": {
                    "income": 30_000_000,
                    "income_period": "monthly",
                    "dependents": 2,
                    "insurance": 5_000_000,
                    "resident_status": "resident",
                },
            }
        }
    )
    assert_true(context is not None, "restore context from processed_question")
    assert_equal(context["last_entities"]["income"], VND(30_000_000), "restored income")

    context = _conversation_context_from_metadata(
        {
            "tax_calculation": {
                "input": {
                    "gross_income": 30_000_000,
                    "income_period": "monthly",
                    "mandatory_insurance": 5_000_000,
                    "dependents": 2,
                    "resident_status": "resident",
                    "tax_year": 2026,
                }
            }
        }
    )
    assert_true(context is not None, "restore context from tax calculation")
    assert_equal(context["last_entities"]["insurance"], VND(5_000_000), "restored insurance")


def test_response_formatter_debug() -> None:
    settings = Settings.from_env()
    formatter = ResponseFormatterService(settings)
    response = formatter.format_chat_response(
        answer='```json\\n{"answer":"[SOURCE_1] Thu\\u1ebf t\\u1ea1m t\\u00ednh l\\u00e0 0 \\u0111\\u1ed3ng, taxable_income = 0."}\\n```',
        conversation_id="conversation-1",
        mode="llm",
        citations=[],
        confidence=None,
        query_embedding=QueryEmbeddingResult(
            model_name="test",
            input_text="query",
            input_source="retrieval_query",
            dimension=3,
            normalized=True,
            vector_norm=1.0,
            vector_preview=[0.1, 0.2, 0.3],
        ),
        context=ContextBuildResult(
            strategy=ContextBuilderStrategy.SOURCE_BLOCKS,
            applied=True,
            max_tokens=1000,
            estimated_tokens=20,
            input_count=1,
            unique_count=1,
            included_count=1,
            duplicate_removed_count=0,
            skipped_by_token_limit_count=0,
            truncated_count=0,
            context_text="context " * 100,
            sources=[],
        ),
        llm=LLMGenerationResult(
            provider=LLMProvider.GEMINI,
            model="gemini-test",
            applied=True,
            temperature=0.1,
            max_output_tokens=1000,
            raw_text="raw answer should not be exposed in debug",
            answer="answer should not be exposed in debug",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            estimated_cost_usd=0.001,
        ),
    )
    assert_in("thu nhập tính thuế", response.answer, "formatter replaces technical term")
    assert_true(response.debug is not None, "debug exposed in development")
    assert_true("vector_preview" not in response.debug["query_embedding"], "debug hides vector preview")
    assert_true("context_text" not in response.debug["context"], "debug hides full context")
    assert_true("raw_text" not in response.debug["llm"], "debug hides raw LLM text")
    assert_true("answer" not in response.debug["llm"], "debug hides parsed LLM answer")


def test_chunking_overlap() -> None:
    paragraphs = [
        " ".join(f"p{paragraph_index}_word{word_index}" for word_index in range(160))
        for paragraph_index in range(30)
    ]
    chunks = split_plain_text("\n\n".join(paragraphs), max_chars=MAX_CHARS_PER_CHUNK)
    assert_true(len(chunks) > 1, "chunker splits long text")
    assert_true(all(len(chunk) <= MAX_CHARS_PER_CHUNK for chunk in chunks), "chunks stay under max chars")
    expected_tail = token_tail(chunks[0], OVERLAP_TOKENS).split()
    assert_true(bool(expected_tail), "chunker has overlap tail")
    assert_true(all(word in chunks[1] for word in expected_tail[-8:]), "next chunk includes overlap tail")


TESTS = [
    test_entity_extraction,
    test_single_turn_routing,
    test_multi_turn_tax_flows,
    test_tax_calculation_numbers,
    test_metadata_context_restore,
    test_response_formatter_debug,
    test_chunking_overlap,
]


def main() -> int:
    failed = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")

    if failed:
        print(f"\n{failed} smoke scenario(s) failed.")
        return 1

    print(f"\nAll {len(TESTS)} smoke scenario groups passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
