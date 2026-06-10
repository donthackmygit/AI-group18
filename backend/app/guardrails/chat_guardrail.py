from __future__ import annotations

from backend.app.guardrails.input_validator import normalize_text, validate_basic_question
from backend.app.guardrails.injection_guard import validate_prompt_injection
from backend.app.guardrails.scope_guard import validate_scope
from backend.app.guardrails.validation_result import ValidationResult


def validate_chat_question(question: str | None) -> ValidationResult:
    basic_result = validate_basic_question(question)
    if not basic_result.is_valid:
        return basic_result

    normalized_question = normalize_text(question or "")

    injection_result = validate_prompt_injection(normalized_question)
    if not injection_result.is_valid:
        injection_result.normalized_question = normalized_question
        return injection_result

    scope_result = validate_scope(normalized_question)
    if not scope_result.is_valid:
        scope_result.normalized_question = normalized_question
        return scope_result

    return ValidationResult(is_valid=True, normalized_question=normalized_question)
