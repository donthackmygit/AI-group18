from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RerankingStrategy(str, Enum):
    HEURISTIC = "HEURISTIC"


class RerankedCandidate(BaseModel):
    chunk_id: str
    retrieval_rank: int
    rerank_rank: int
    similarity: float
    semantic_rank: int | None = None
    keyword_rank: int | None = None
    keyword_score: float | None = None
    hybrid_score: float | None = None
    rerank_score: float
    keyword_overlap: float
    topic_score: float
    metadata_boost: float
    reasons: list[str] = Field(default_factory=list)


class RerankingResult(BaseModel):
    strategy: RerankingStrategy
    applied: bool
    input_count: int
    output_count: int
    requested_top_k: int
    score_min: float | None = None
    score_max: float | None = None
    score_avg: float | None = None
    candidates: list[RerankedCandidate] = Field(default_factory=list)
    note: str | None = None
