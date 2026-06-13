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
            current = self._items.get(conversation_id) or {}
            current_entities = current.get("last_entities") or {}
            next_entities = processed_question.entities.model_dump()
            merged_entities = {
                **current_entities,
                **{
                    key: value
                    for key, value in next_entities.items()
                    if value is not None
                },
            }
            self._items[conversation_id] = {
                "last_standalone_question": processed_question.standalone_question,
                "last_entities": merged_entities,
                "last_intent": processed_question.intent or current.get("last_intent"),
                "last_topic": processed_question.topic or current.get("last_topic"),
            }
