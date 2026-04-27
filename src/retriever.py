"""
Hybrid retrieval: dense vector search (ChromaDB) + sparse BM25,
combined with Reciprocal Rank Fusion (RRF).

Per source: top-K vector + top-K BM25 → merged with RRF → up to 3*K*2 candidates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from sentence_transformers import SentenceTransformer

from src.chunker import Chunk
from src.indexer import Indexer
from src.utils import load_config

logger = logging.getLogger(__name__)


@dataclass
class ScoredChunk:
    chunk: Chunk
    rrf_score: float
    vector_rank: int = -1    # -1 = not in vector results
    bm25_rank: int = -1      # -1 = not in BM25 results
    rerank_score: float = 0.0


class Retriever:
    def __init__(self, indexer: Indexer, config=None):
        cfg = config or load_config()
        self.indexer = indexer
        self.top_k: int = cfg["retrieval"]["top_k_per_source"]
        self.rrf_k: int = cfg["retrieval"]["rrf_k"]
        self.sources: List[str] = cfg["chroma"]["collections"]
        self._embedder: SentenceTransformer | None = None
        self._embed_model: str = cfg["embedding"]["model"]

    @property
    def embedder(self) -> SentenceTransformer:
        if self._embedder is None:
            self._embedder = SentenceTransformer(self._embed_model)
        return self._embedder

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def search(self, query: str) -> List[ScoredChunk]:
        """
        Run hybrid retrieval across all sources.
        Returns deduplicated candidates ranked by RRF score (descending).
        """
        query_embedding = self.embedder.encode(
            [query], normalize_embeddings=True
        )[0].tolist()

        all_vector_results: Dict[str, List[Tuple[Chunk, int]]] = {}
        all_bm25_results: Dict[str, List[Tuple[Chunk, int]]] = {}

        for source in self.sources:
            v_results = self._vector_search(source, query_embedding)
            b_results = self._bm25_search(source, query)
            all_vector_results[source] = v_results
            all_bm25_results[source] = b_results

            logger.debug(
                "[Retriever] %s — vector: %d, bm25: %d",
                source, len(v_results), len(b_results),
            )

        merged = self._rrf_merge(all_vector_results, all_bm25_results)
        return merged

    # ------------------------------------------------------------------
    # Vector search
    # ------------------------------------------------------------------

    def _vector_search(
        self, source: str, query_embedding: List[float]
    ) -> List[Tuple[Chunk, int]]:
        collection = self.indexer.get_collection(source)
        if collection is None or collection.count() == 0:
            return []

        n_results = min(self.top_k, collection.count())
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        chunks_with_rank: List[Tuple[Chunk, int]] = []
        for rank, (doc_id, doc_text, meta) in enumerate(
            zip(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0],
            )
        ):
            chunk = Chunk(
                chunk_id=doc_id,
                text=doc_text,
                source_type=meta.get("source_type", source),
                source_file=meta.get("source_file", ""),
                metadata={k: v for k, v in meta.items() if k not in ("source_type", "source_file")},
            )
            chunks_with_rank.append((chunk, rank + 1))  # 1-indexed rank

        return chunks_with_rank

    # ------------------------------------------------------------------
    # BM25 search
    # ------------------------------------------------------------------

    def _bm25_search(self, source: str, query: str) -> List[Tuple[Chunk, int]]:
        bm25, chunks = self.indexer.get_bm25(source)
        if bm25 is None or not chunks:
            return []

        tokenized_query = query.lower().split()
        scores = bm25.get_scores(tokenized_query)

        # Get top-k by score
        ranked = sorted(
            enumerate(scores), key=lambda x: x[1], reverse=True
        )[: self.top_k]

        return [(chunks[idx], rank + 1) for rank, (idx, score) in enumerate(ranked) if score > 0]

    # ------------------------------------------------------------------
    # Reciprocal Rank Fusion
    # ------------------------------------------------------------------

    def _rrf_merge(
        self,
        vector_results: Dict[str, List[Tuple[Chunk, int]]],
        bm25_results: Dict[str, List[Tuple[Chunk, int]]],
    ) -> List[ScoredChunk]:
        k = self.rrf_k
        scores: Dict[str, float] = {}
        chunk_store: Dict[str, Chunk] = {}
        vector_ranks: Dict[str, int] = {}
        bm25_ranks: Dict[str, int] = {}

        for source in self.sources:
            for chunk, rank in vector_results.get(source, []):
                cid = chunk.chunk_id
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
                chunk_store[cid] = chunk
                vector_ranks[cid] = rank

            for chunk, rank in bm25_results.get(source, []):
                cid = chunk.chunk_id
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
                chunk_store[cid] = chunk
                bm25_ranks[cid] = rank

        sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)

        return [
            ScoredChunk(
                chunk=chunk_store[cid],
                rrf_score=scores[cid],
                vector_rank=vector_ranks.get(cid, -1),
                bm25_rank=bm25_ranks.get(cid, -1),
            )
            for cid in sorted_ids
        ]
