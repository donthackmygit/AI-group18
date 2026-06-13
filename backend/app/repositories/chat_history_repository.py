from __future__ import annotations

from typing import Any

from backend.app.core.config import Settings
from backend.app.core.database import get_database_connection
from backend.app.schemas.rag import ChatResponse


VERIFY_CONVERSATION_SQL = """
    select id
    from public.conversations
    where id = %(conversation_id)s::uuid
      and user_id = %(user_id)s::uuid
    limit 1;
"""


INSERT_ASSISTANT_MESSAGE_SQL = """
    insert into public.messages (
        conversation_id,
        user_id,
        role,
        content,
        citations,
        retrieval_metadata
    )
    values (
        %(conversation_id)s::uuid,
        %(user_id)s::uuid,
        'assistant',
        %(content)s,
        %(citations)s,
        %(retrieval_metadata)s
    )
    returning id;
"""


class ChatHistoryRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def assert_user_owns_conversation(self, conversation_id: str, user_id: str) -> None:
        psycopg, dict_row, _ = self._load_database_dependencies()
        with get_database_connection(self.settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    VERIFY_CONVERSATION_SQL,
                    {"conversation_id": conversation_id, "user_id": user_id},
                )
                row = cur.fetchone()
            if not row:
                raise PermissionError("Conversation does not exist or does not belong to this user.")

    def insert_assistant_message(
        self,
        *,
        conversation_id: str,
        user_id: str,
        response: ChatResponse,
    ) -> str:
        psycopg, dict_row, Jsonb = self._load_database_dependencies()
        metadata = _build_retrieval_metadata(response)
        params = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "content": response.answer,
            "citations": Jsonb([citation.model_dump(mode="json") for citation in response.citations]),
            "retrieval_metadata": Jsonb(metadata),
        }

        with get_database_connection(self.settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(INSERT_ASSISTANT_MESSAGE_SQL, params)
                row = cur.fetchone()
            conn.commit()
            return str(row["id"])

    @staticmethod
    def _load_database_dependencies() -> tuple[Any, Any, Any]:
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg.types.json import Jsonb
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Missing database dependency. Install project requirements before persisting chat: "
                "python -m pip install -r requirements.txt"
            ) from exc
        return psycopg, dict_row, Jsonb


def _build_retrieval_metadata(response: ChatResponse) -> dict[str, Any]:
    return {
        "mode": response.mode,
        "confidence": response.confidence,
        "warnings": response.warnings,
        "calculation": (
            response.calculation.model_dump(mode="json")
            if response.calculation
            else None
        ),
        "classification": (
            response.classification.model_dump(mode="json")
            if response.classification
            else None
        ),
        "routing": (
            response.routing.model_dump(mode="json")
            if response.routing
            else None
        ),
        "query_embedding": (
            response.query_embedding.model_dump(mode="json")
            if response.query_embedding
            else None
        ),
        "retrieval": (
            response.retrieval.model_dump(mode="json")
            if response.retrieval
            else None
        ),
        "reranking": (
            response.reranking.model_dump(mode="json")
            if response.reranking
            else None
        ),
        "tax_calculation": (
            response.tax_calculation.model_dump(mode="json")
            if response.tax_calculation
            else None
        ),
        "response_validation": (
            response.response_validation.model_dump(mode="json")
            if response.response_validation
            else None
        ),
        "response_formatter": (
            response.response_formatter.model_dump(mode="json")
            if response.response_formatter
            else None
        ),
    }
