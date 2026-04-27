"""
Builds and persists:
  - ChromaDB vector collections (one per source type)
  - BM25 indices (one per source type)

Run directly to (re)build the index:
    python -m src.indexer [--rebuild]
"""

from __future__ import annotations

import argparse
import logging
import os
import pickle
from pathlib import Path
from typing import Dict, List, Tuple

import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from src.chunker import Chunk, load_all_chunks
from src.utils import load_config

logger = logging.getLogger(__name__)

BM25_CACHE_PATH = "bm25_indices.pkl"


class Indexer:
    def __init__(self, config=None):
        cfg = config or load_config()
        self.embed_model_name: str = cfg["embedding"]["model"]
        self.chroma_dir: str = cfg["chroma"]["persist_directory"]
        self.collections_names: List[str] = cfg["chroma"]["collections"]

        self._embedder: SentenceTransformer | None = None
        self._chroma_client: chromadb.ClientAPI | None = None
        self._collections: Dict[str, chromadb.Collection] = {}
        self._bm25_indices: Dict[str, BM25Okapi] = {}
        self._bm25_chunks: Dict[str, List[Chunk]] = {}

    # ------------------------------------------------------------------
    # Lazy-loaded resources
    # ------------------------------------------------------------------

    @property
    def embedder(self) -> SentenceTransformer:
        if self._embedder is None:
            logger.info("Loading embedding model: %s", self.embed_model_name)
            self._embedder = SentenceTransformer(self.embed_model_name)
        return self._embedder

    @property
    def chroma_client(self) -> chromadb.ClientAPI:
        if self._chroma_client is None:
            self._chroma_client = chromadb.PersistentClient(path=self.chroma_dir)
        return self._chroma_client

    # ------------------------------------------------------------------
    # Build index
    # ------------------------------------------------------------------

    def build(self, chunks: List[Chunk], rebuild: bool = False) -> None:
        """Index all chunks. Skips if already indexed (unless rebuild=True)."""
        if rebuild:
            self._drop_existing_collections()
            if Path(BM25_CACHE_PATH).exists():
                os.remove(BM25_CACHE_PATH)

        # Group chunks by source type
        grouped: Dict[str, List[Chunk]] = {name: [] for name in self.collections_names}
        for chunk in chunks:
            if chunk.source_type in grouped:
                grouped[chunk.source_type].append(chunk)

        # Build vector and BM25 indices per source
        for source_type, source_chunks in grouped.items():
            if not source_chunks:
                continue
            logger.info("Indexing %d chunks for source='%s'", len(source_chunks), source_type)
            self._build_vector_index(source_type, source_chunks, rebuild)
            self._build_bm25_index(source_type, source_chunks)

        self._save_bm25_cache()
        logger.info("Indexing complete.")

    def _drop_existing_collections(self) -> None:
        for name in self.collections_names:
            try:
                self.chroma_client.delete_collection(name)
                logger.debug("Dropped collection '%s'", name)
            except Exception:
                pass

    def _build_vector_index(
        self, source_type: str, chunks: List[Chunk], rebuild: bool
    ) -> None:
        collection = self.chroma_client.get_or_create_collection(
            name=source_type,
            metadata={"hnsw:space": "cosine"},
        )
        self._collections[source_type] = collection

        # Skip if already populated and not rebuilding
        if not rebuild and collection.count() == len(chunks):
            logger.info("Collection '%s' already up to date, skipping.", source_type)
            return

        texts = [c.text for c in chunks]
        logger.info("Embedding %d texts for '%s'...", len(texts), source_type)
        embeddings = self.embedder.encode(
            texts, batch_size=32, show_progress_bar=False, normalize_embeddings=True
        ).tolist()

        collection.upsert(
            ids=[c.chunk_id for c in chunks],
            embeddings=embeddings,
            documents=texts,
            metadatas=[
                {**c.metadata, "source_type": c.source_type, "source_file": c.source_file}
                for c in chunks
            ],
        )

    def _build_bm25_index(self, source_type: str, chunks: List[Chunk]) -> None:
        tokenized = [c.text.lower().split() for c in chunks]
        self._bm25_indices[source_type] = BM25Okapi(tokenized)
        self._bm25_chunks[source_type] = chunks

    def _save_bm25_cache(self) -> None:
        data = {
            "indices": self._bm25_indices,
            "chunks": self._bm25_chunks,
        }
        with open(BM25_CACHE_PATH, "wb") as f:
            pickle.dump(data, f)
        logger.debug("BM25 cache saved to %s", BM25_CACHE_PATH)

    # ------------------------------------------------------------------
    # Load existing index (for retrieval without rebuilding)
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load ChromaDB collections and BM25 indices from disk."""
        for name in self.collections_names:
            try:
                self._collections[name] = self.chroma_client.get_collection(name)
            except Exception as e:
                logger.warning("Could not load collection '%s': %s", name, e)

        if Path(BM25_CACHE_PATH).exists():
            with open(BM25_CACHE_PATH, "rb") as f:
                data = pickle.load(f)
            self._bm25_indices = data["indices"]
            self._bm25_chunks = data["chunks"]
        else:
            logger.warning("BM25 cache not found at %s", BM25_CACHE_PATH)

    # ------------------------------------------------------------------
    # Accessors for retriever
    # ------------------------------------------------------------------

    def get_collection(self, source_type: str) -> chromadb.Collection | None:
        if source_type not in self._collections:
            try:
                self._collections[source_type] = self.chroma_client.get_collection(source_type)
            except Exception:
                return None
        return self._collections[source_type]

    def get_bm25(self, source_type: str) -> Tuple[BM25Okapi | None, List[Chunk]]:
        return self._bm25_indices.get(source_type), self._bm25_chunks.get(source_type, [])


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Build DataFlow RAG index")
    parser.add_argument("--rebuild", action="store_true", help="Force full rebuild")
    parser.add_argument("--data-dir", default="data", help="Path to data directory")
    args = parser.parse_args()

    chunks = load_all_chunks(args.data_dir)
    logger.info("Loaded %d total chunks", len(chunks))

    indexer = Indexer()
    indexer.build(chunks, rebuild=args.rebuild)


if __name__ == "__main__":
    main()
