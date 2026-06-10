from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.app.core.config import Settings
from backend.app.schemas.query_embedding import QueryEmbeddingResult
from backend.app.schemas.question_processing import ProcessedQuestion
from backend.app.schemas.query_route import (
    QueryClassificationResult,
    QueryIntent,
    QueryRoute,
    QueryRoutingResult,
)
from backend.app.services.embedding_service import EmbeddingService


@dataclass(frozen=True)
class QueryEmbeddingPayload:
    vector: np.ndarray
    result: QueryEmbeddingResult


class QueryEmbeddingService:
    def __init__(self, settings: Settings, embedding_service: EmbeddingService) -> None:
        self.settings = settings
        self.embedding_service = embedding_service

    def embed_query(
        self,
        processed_question: ProcessedQuestion,
        classification: QueryClassificationResult,
        routing: QueryRoutingResult,
    ) -> QueryEmbeddingPayload:
        input_text, input_source = select_embedding_input(
            processed_question=processed_question,
            classification=classification,
            routing=routing,
        )
        vector = self.embedding_service.encode_query(input_text)
        vector = np.asarray(vector, dtype=np.float32)
        norm = float(np.linalg.norm(vector))

        return QueryEmbeddingPayload(
            vector=vector,
            result=QueryEmbeddingResult(
                model_name=self.settings.embedding_model_name,
                input_text=input_text,
                input_source=input_source,
                dimension=int(vector.shape[0]),
                normalized=True,
                vector_norm=norm,
                vector_preview=[float(value) for value in vector[:5]],
            ),
        )


def select_embedding_input(
    processed_question: ProcessedQuestion,
    classification: QueryClassificationResult,
    routing: QueryRoutingResult,
) -> tuple[str, str]:
    if routing.route == QueryRoute.RAG_WITH_TAX_CALCULATION:
        return processed_question.retrieval_query, "retrieval_query"

    if classification.intent in {QueryIntent.DEFINITION, QueryIntent.PROCEDURE_GUIDE}:
        return processed_question.retrieval_query, "retrieval_query"

    return processed_question.standalone_question, "standalone_question"
