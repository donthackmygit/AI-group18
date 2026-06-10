from __future__ import annotations

from backend.app.guardrails.input_validator import normalize_text


def normalize_question(question: str) -> str:
    return normalize_text(question or "")
