from __future__ import annotations

from typing import Any

from backend.app.question_processing.entity_extractor import extract_entities
from backend.app.question_processing.intent_classifier import classify_intent, detect_topic
from backend.app.question_processing.normalizer import normalize_question
from backend.app.question_processing.query_rewriter import rewrite_follow_up_question
from backend.app.question_processing.retrieval_query_builder import build_retrieval_query
from backend.app.schemas.question_processing import ProcessedQuestion


def process_question(
    question: str,
    conversation_context: dict[str, Any] | None = None,
) -> ProcessedQuestion:
    normalized_question = normalize_question(question)
    initial_entities = extract_entities(normalized_question)

    standalone_question = rewrite_follow_up_question(
        current_question=normalized_question,
        current_entities=initial_entities,
        conversation_context=conversation_context,
    )

    entities = extract_entities(standalone_question)
    intent = classify_intent(standalone_question)
    topic = detect_topic(standalone_question)
    retrieval_query = build_retrieval_query(
        intent=intent,
        topic=topic,
        question=standalone_question,
        entities=entities,
    )

    return ProcessedQuestion(
        original_question=question,
        normalized_question=normalized_question,
        standalone_question=standalone_question,
        intent=intent,
        topic=topic,
        entities=entities,
        retrieval_query=retrieval_query,
    )
