"""
FastAPI application for the DataFlow Pro Multi-Source RAG system.

Endpoints:
  POST /query   — answer a question
  GET  /debug   — show intermediate results for a question
  GET  /health  — liveness check
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.pipeline import RAGPipeline
from src.utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

pipeline = RAGPipeline()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — loading index...")
    try:
        pipeline.load_existing()
        logger.info("Index loaded from disk.")
    except Exception as e:
        logger.warning("Could not load existing index (%s). Building from scratch...", e)
        pipeline.initialize(rebuild=False)
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="DataFlow Pro RAG API",
    description="Multi-source RAG system for DataFlow Pro technical support",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
def serve_ui():
    return FileResponse("static/index.html")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str

    model_config = {"json_schema_extra": {"example": {"question": "How do I install DataFlow Pro?"}}}


class QueryResponse(BaseModel):
    answer: str
    sources: List[str]
    source_counts: Dict[str, int]
    conflicts: Optional[str]
    log: str
    latency_ms: float


class DebugChunk(BaseModel):
    chunk_id: str
    source_type: str
    source_file: str
    rerank_score: float
    rrf_score: float
    text_preview: str


class DebugResponse(BaseModel):
    question: str
    total_candidates: int
    top_chunks: List[DebugChunk]
    conflict_details: List[Dict[str, Any]]
    resolution_note: str
    log: str
    latency_ms: float


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "healthy", "pipeline_ready": pipeline._ready}


@app.post("/query", response_model=QueryResponse)
def query_endpoint(request: QueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    logger.info("POST /query question=%r", request.question)
    try:
        result = pipeline.query(request.question)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("Pipeline error")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

    return QueryResponse(
        answer=result.answer,
        sources=result.sources,
        source_counts=result.source_counts,
        conflicts=result.conflicts,
        log=result.log_summary,
        latency_ms=round(result.latency_ms, 1),
    )


@app.get("/debug", response_model=DebugResponse)
def debug_endpoint(question: str = Query(..., description="Question to debug")):
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    logger.info("GET /debug question=%r", question)
    try:
        result = pipeline.query(question)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    top_chunks = [
        DebugChunk(
            chunk_id=sc.chunk.chunk_id,
            source_type=sc.chunk.source_type,
            source_file=sc.chunk.source_file,
            rerank_score=round(sc.rerank_score, 4),
            rrf_score=round(sc.rrf_score, 6),
            text_preview=sc.chunk.text[:300] + ("..." if len(sc.chunk.text) > 300 else ""),
        )
        for sc in result.top_chunks
    ]

    return DebugResponse(
        question=question,
        total_candidates=len(result.all_candidates),
        top_chunks=top_chunks,
        conflict_details=result.conflict_report.conflicts,
        resolution_note=result.conflict_report.resolution_note,
        log=result.log_summary,
        latency_ms=round(result.latency_ms, 1),
    )


@app.post("/rebuild-index")
def rebuild_index():
    """Force a full index rebuild (slow — use only when data changes)."""
    logger.info("POST /rebuild-index — rebuilding...")
    pipeline.initialize(rebuild=True)
    return {"status": "rebuilt"}


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
