from __future__ import annotations

from threading import Lock
from typing import Any

from backend.app.schemas.question_processing import ProcessedQuestion


class ConversationMemoryStore:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def get(self, conversation_id: str | None) -> dict[str, Any] | None:
        if not conversation_id:
            return None
        with self._lock:
            item = self._items.get(conversation_id)
            return dict(item) if item else None

    def update(self, conversation_id: str | None, processed_question: ProcessedQuestion) -> None:
        if not conversation_id:
            return
        with self._lock:
            self._items[conversation_id] = {
                "last_standalone_question": processed_question.standalone_question,
                "last_entities": processed_question.entities.model_dump(),
                "last_intent": processed_question.intent,
                "last_topic": processed_question.topic,
            }
