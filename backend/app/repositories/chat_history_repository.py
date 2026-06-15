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

FETCH_RECENT_ASSISTANT_METADATA_SQL = """
    select retrieval_metadata
    from public.messages
    where conversation_id = %(conversation_id)s::uuid
      and user_id = %(user_id)s::uuid
      and role = 'assistant'
      and retrieval_metadata is not null
    order by created_at desc
    limit %(limit)s;
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

    def fetch_latest_conversation_context(
        self,
        *,
        conversation_id: str,
        user_id: str,
        limit: int = 8,
    ) -> dict[str, Any] | None:
        _, dict_row, _ = self._load_database_dependencies()
        params = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "limit": max(1, min(limit, 20)),
        }

        with get_database_connection(self.settings) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(FETCH_RECENT_ASSISTANT_METADATA_SQL, params)
                rows = cur.fetchall()

        for row in rows:
            metadata = row.get("retrieval_metadata") or {}
            context = _conversation_context_from_metadata(metadata)
            if context:
                return context

        return None

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
        "processed_question": (
            response.processed_question.model_dump(mode="json")
            if response.processed_question
            else None
        ),
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
        "debug": response.debug,
    }


def _conversation_context_from_metadata(metadata: dict[str, Any]) -> dict[str, Any] | None:
    processed_question = metadata.get("processed_question")
    if not isinstance(processed_question, dict):
        debug = metadata.get("debug") or {}
        if isinstance(debug, dict):
            processed_question = debug.get("processed_question")

    if isinstance(processed_question, dict):
        entities = _compact_entities(processed_question.get("entities") or {})
        if entities:
            return {
                "last_standalone_question": processed_question.get("standalone_question"),
                "last_entities": entities,
                "last_intent": processed_question.get("intent"),
                "last_topic": processed_question.get("topic"),
            }

    calculation = metadata.get("tax_calculation")
    if not isinstance(calculation, dict):
        debug = metadata.get("debug") or {}
        if isinstance(debug, dict):
            calculation = debug.get("tax_calculation")

    if isinstance(calculation, dict):
        calculation_input = calculation.get("input") or {}
        entities = _compact_entities(
            {
                "income": calculation_input.get("gross_income"),
                "income_period": calculation_input.get("income_period"),
                "insurance": calculation_input.get("mandatory_insurance"),
                "dependents": calculation_input.get("dependents"),
                "resident_status": calculation_input.get("resident_status"),
                "tax_year": calculation_input.get("tax_year"),
            }
        )
        if entities:
            return {
                "last_standalone_question": None,
                "last_entities": entities,
                "last_intent": "TAX_CALCULATION",
                "last_topic": "Tính thuế TNCN",
            }

    return None


def _compact_entities(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item is not None and item != ""
    }
