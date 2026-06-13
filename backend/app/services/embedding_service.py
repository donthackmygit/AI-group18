from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from typing import Any

import numpy as np

from backend.app.core.config import Settings, configure_model_cache


class EmbeddingService:
    _QUERY_CACHE_MAX_ITEMS = 256

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model: Any | None = None
        self._lock = Lock()
        self._query_cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._query_cache_lock = Lock()

    def encode_query(self, question: str) -> np.ndarray:
        cache_key = self._query_cache_key(question)
        cached = self._get_cached_query(cache_key)
        if cached is not None:
            return cached

        model = self._get_model()
        embedding = model.encode([f"query: {question}"], normalize_embeddings=True)[0]
        vector = np.asarray(embedding, dtype=np.float32)
        self._cache_query(cache_key, vector)
        return vector.copy()

    def encode_passages(self, passages: list[str]) -> np.ndarray:
        if not passages:
            return np.empty((0, 768), dtype=np.float32)

        model = self._get_model()
        embeddings = model.encode(
            [f"passage: {passage}" for passage in passages],
            normalize_embeddings=True,
        )
        return np.asarray(embeddings, dtype=np.float32)

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

    def _query_cache_key(self, question: str) -> str:
        return f"{self.settings.embedding_model_name}:{question.strip()}"

    def _get_cached_query(self, cache_key: str) -> np.ndarray | None:
        with self._query_cache_lock:
            vector = self._query_cache.get(cache_key)
            if vector is None:
                return None
            self._query_cache.move_to_end(cache_key)
            return vector.copy()

    def _cache_query(self, cache_key: str, vector: np.ndarray) -> None:
        with self._query_cache_lock:
            self._query_cache[cache_key] = vector.copy()
            self._query_cache.move_to_end(cache_key)
            while len(self._query_cache) > self._QUERY_CACHE_MAX_ITEMS:
                self._query_cache.popitem(last=False)
