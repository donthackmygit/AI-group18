from __future__ import annotations

from threading import Lock
from typing import Any

import numpy as np

from backend.app.core.config import Settings, configure_model_cache


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model: Any | None = None
        self._lock = Lock()

    def encode_query(self, question: str) -> np.ndarray:
        model = self._get_model()
        embedding = model.encode([f"query: {question}"], normalize_embeddings=True)[0]
        return np.asarray(embedding, dtype=np.float32)

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model

        with self._lock:
            if self._model is not None:
                return self._model

            configure_model_cache()
            try:
                from sentence_transformers import SentenceTransformer
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "Missing embedding dependency. Install project requirements before running retrieval: "
                    "python -m pip install -r requirements.txt"
                ) from exc

            self._model = SentenceTransformer(
                self.settings.embedding_model_name,
                local_files_only=self.settings.embedding_local_files_only,
            )
            return self._model
