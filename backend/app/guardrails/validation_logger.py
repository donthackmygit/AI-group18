from __future__ import annotations

import logging
import json

from backend.app.guardrails.validation_result import ValidationResult


logger = logging.getLogger("uvicorn.error")


def log_validation(
    *,
    conversation_id: str | None,
    original_question: str | None,
    result: ValidationResult,
) -> None:
    payload = {
        "event": "input_validation",
        "conversation_id": conversation_id,
        "original_question": original_question,
        "normalized_question": result.normalized_question,
        "validation_status": "passed" if result.is_valid else "failed",
        "reason": result.reason,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))
