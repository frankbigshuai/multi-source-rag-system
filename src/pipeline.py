"""
RAG Pipeline: orchestrates retrieval → reranking → conflict detection → LLM generation.

Also handles:
  - Unanswerable question detection (no relevant context found)
  - Structured logging of which sources contributed to each answer
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from openai import OpenAI

from src.conflict import ConflictDetector, ConflictReport, format_conflicts_for_user
from src.indexer import Indexer
from src.retriever import Retriever, ScoredChunk
from src.reranker import Reranker
from src.utils import load_config

logger = logging.getLogger(__name__)


@dataclass
class RAGResponse:
    answer: str
    sources: List[str]
    source_counts: Dict[str, int]
    conflicts: Optional[str]
    conflict_report: ConflictReport
    top_chunks: List[ScoredChunk]
    all_candidates: List[ScoredChunk]
    latency_ms: float
    log_summary: str


SYSTEM_PROMPT = """You are a helpful technical support assistant for DataFlow Pro, \
an enterprise data pipeline platform. Answer the user's question using ONLY \
the provided context passages.

Rules:
- If the context does not contain sufficient information, say so clearly.
- When sources disagree, prefer information from official documentation over blogs or forums.
- Be concise and accurate. Include relevant configuration values or commands when helpful.
- If a question is about a product or feature that does not exist in DataFlow Pro, politely say so."""

UNANSWERABLE_THRESHOLD = 0.0  # rerank score below this → likely unanswerable


class RAGPipeline:
    def __init__(self, config=None):
        self.cfg = config or load_config()
        self.indexer = Indexer(self.cfg)
        self.retriever = Retriever(self.indexer, self.cfg)
        self.reranker = Reranker(self.cfg)
        self.conflict_detector = ConflictDetector(self.cfg)
        self._llm: OpenAI | None = None
        self._ready = False

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self, rebuild: bool = False) -> None:
        """Build or load the index. Call once at startup."""
        from src.chunker import load_all_chunks
        chunks = load_all_chunks("data")
        logger.info("Loaded %d total chunks", len(chunks))
        self.indexer.build(chunks, rebuild=rebuild)
        self._ready = True

    def load_existing(self) -> None:
        """Load a pre-built index from disk (faster startup)."""
        self.indexer.load()
        self._ready = True

    # ------------------------------------------------------------------
    # LLM client
    # ------------------------------------------------------------------

    @property
    def llm(self) -> OpenAI:
        if self._llm is None:
            api_key = self.cfg["deepseek"]["api_key"]
            base_url = self.cfg["deepseek"]["base_url"]
            if not api_key or api_key.startswith("${"):
                raise ValueError(
                    "DEEPSEEK_API_KEY is not set. Copy .env.example to .env and fill in your key."
                )
            self._llm = OpenAI(api_key=api_key, base_url=base_url)
        return self._llm

    # ------------------------------------------------------------------
    # Main query method
    # ------------------------------------------------------------------

    def query(self, question: str) -> RAGResponse:
        if not self._ready:
            raise RuntimeError("Pipeline not initialized. Call initialize() or load_existing().")

        t_start = time.perf_counter()

        # Step 1: Hybrid retrieval
        candidates = self.retriever.search(question)
        logger.info("[Pipeline] %d candidates retrieved for: %r", len(candidates), question)

        # Step 2: Rerank
        top_chunks = self.reranker.rerank(question, candidates)

        # Step 3: Conflict detection
        conflict_report = self.conflict_detector.detect(top_chunks)

        # Step 4: Build prompt context (authority-sorted)
        context_chunks = conflict_report.authoritative_chunks

        # Step 5: Unanswerable check
        if not top_chunks or (top_chunks[0].rerank_score < UNANSWERABLE_THRESHOLD):
            answer = (
                "I don't have reliable information about this topic in the DataFlow Pro "
                "knowledge base. Please consult the official documentation or contact support."
            )
        else:
            context_str = self._build_context(context_chunks)
            answer = self._generate(question, context_str)
            if not answer:
                answer = (
                    "Based on the available documentation, DataFlow Pro does not support "
                    "this feature or product. Please consult the official documentation at "
                    "dataflowpro.io or contact support@dataflowpro.io for assistance."
                )

        # Step 6: Build response metadata
        source_files = list(dict.fromkeys(sc.chunk.source_file for sc in top_chunks))
        source_counts = Counter(sc.chunk.source_type for sc in top_chunks)
        conflict_str = format_conflicts_for_user(conflict_report)
        log_summary = self._build_log_summary(question, top_chunks, source_counts)

        latency_ms = (time.perf_counter() - t_start) * 1000
        logger.info("[Pipeline] %s | latency=%.0fms", log_summary, latency_ms)

        return RAGResponse(
            answer=answer,
            sources=source_files,
            source_counts=dict(source_counts),
            conflicts=conflict_str,
            conflict_report=conflict_report,
            top_chunks=top_chunks,
            all_candidates=candidates,
            latency_ms=latency_ms,
            log_summary=log_summary,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_context(chunks: List[ScoredChunk]) -> str:
        sections: List[str] = []
        for i, sc in enumerate(chunks, 1):
            source_label = f"[{sc.chunk.source_type.upper()} — {sc.chunk.source_file}]"
            sections.append(f"--- Passage {i} {source_label} ---\n{sc.chunk.text}")
        return "\n\n".join(sections)

    def _generate(self, question: str, context: str) -> str:
        user_message = f"Context:\n{context}\n\nQuestion: {question}"
        response = self.llm.chat.completions.create(
            model=self.cfg["deepseek"]["model"],
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=self.cfg["deepseek"]["max_tokens"],
            temperature=self.cfg["deepseek"]["temperature"],
        )
        return (response.choices[0].message.content or "").strip()

    @staticmethod
    def _build_log_summary(
        question: str, top_chunks: List[ScoredChunk], source_counts: Counter
    ) -> str:
        counts_str = ", ".join(f"{cnt} from {src}" for src, cnt in sorted(source_counts.items()))
        chunk_ids = [sc.chunk.chunk_id for sc in top_chunks]
        return f"Q={question!r:.60} | sources=[{counts_str}] | chunks={chunk_ids}"
