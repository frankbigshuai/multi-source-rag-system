"""
Cross-encoder reranker.

Takes up to N candidates from the retriever and scores each (query, passage)
pair with a cross-encoder model. Returns the top-K by cross-encoder score.
"""

from __future__ import annotations

import logging
from typing import List

from sentence_transformers import CrossEncoder

from src.retriever import ScoredChunk
from src.utils import load_config

logger = logging.getLogger(__name__)


class Reranker:
    def __init__(self, config=None):
        cfg = config or load_config()
        self.model_name: str = cfg["reranker"]["model"]
        self.top_k: int = cfg["reranker"]["top_k"]
        self._model: CrossEncoder | None = None

    @property
    def model(self) -> CrossEncoder:
        if self._model is None:
            logger.info("Loading cross-encoder reranker: %s", self.model_name)
            self._model = CrossEncoder(self.model_name, max_length=512)
        return self._model

    def rerank(self, query: str, candidates: List[ScoredChunk]) -> List[ScoredChunk]:
        """
        Score every candidate with the cross-encoder and return top-K.
        Scores are stored in ScoredChunk.rerank_score.
        """
        if not candidates:
            return []

        pairs = [(query, sc.chunk.text) for sc in candidates]
        scores: List[float] = self.model.predict(pairs).tolist()

        for sc, score in zip(candidates, scores):
            sc.rerank_score = float(score)

        ranked = sorted(candidates, key=lambda sc: sc.rerank_score, reverse=True)
        top = ranked[: self.top_k]

        logger.debug(
            "[Reranker] %d → %d | top score=%.4f | bottom score=%.4f",
            len(candidates),
            len(top),
            top[0].rerank_score if top else 0,
            top[-1].rerank_score if top else 0,
        )
        return top
