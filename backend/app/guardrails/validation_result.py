from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValidationResult:
    is_valid: bool
    message: str = ""
    reason: str = ""
    normalized_question: str = ""
