# Multi-Source RAG for Technical Support

A Retrieval-Augmented Generation (RAG) system that answers customer questions about a fictional software product **DataFlow Pro**, by intelligently retrieving and combining information from three distinct knowledge sources.

---

## Architecture

```
User Question
      ↓
Vector Search (Top 5 per source)    BM25 Search (Top 5 per source)
      ↓                                         ↓
         ←——— RRF Fusion (up to 30 candidates) ———→
                          ↓
              Cross-Encoder Reranking → Top 5
                          ↓
                 Conflict Detection
              docs (1.0) > blogs (0.6) > forums (0.3)
                          ↓
               DeepSeek LLM → Final Answer
                          ↓
          Answer + Sources + Conflict Warning + Log
```

---

## Features

- **Three knowledge sources**: official documentation, community forums, technical blog posts
- **Source-specific chunking**: Markdown header splitting, Q&A pair chunking, sliding window
- **Hybrid retrieval**: dense vector search (ChromaDB) + sparse BM25, fused with RRF
- **Cross-encoder reranking**: improves precision from 30 candidates to top 5
- **Conflict detection**: detects contradictions between sources and resolves by authority weight
- **Full source logging**: every response shows which chunks and sources were used
- **REST API + Web UI**: FastAPI backend with a clean dark-theme interface

---

## Tech Stack

| Component | Tool |
|-----------|------|
| LLM | DeepSeek API |
| Vector DB | ChromaDB (local) |
| Embeddings | `all-MiniLM-L6-v2` (local) |
| BM25 | `rank_bm25` (local) |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` (local) |
| Framework | FastAPI |

---

## Project Structure

```
dataflow-rag/
├── data/
│   ├── docs/               # Official documentation (Markdown)
│   ├── forums/             # Community forum posts (JSON)
│   └── blogs/              # Technical blog posts (TXT)
├── src/
│   ├── chunker.py          # Three chunking strategies
│   ├── indexer.py          # ChromaDB + BM25 index builder
│   ├── retriever.py        # Hybrid search + RRF fusion
│   ├── reranker.py         # Cross-encoder reranking
│   ├── conflict.py         # Contradiction detection & resolution
│   ├── pipeline.py         # End-to-end orchestration
│   └── utils.py            # Config loading, logging setup
├── static/
│   └── index.html          # Web UI
├── main.py                 # FastAPI application
├── run_queries.py          # Run 10 test queries
├── config.yaml             # Configuration
├── requirements.txt
└── report.md               # Full technical report
```

---

## Setup

**1. Clone the repository**
```bash
git clone https://github.com/frankbigshuai/multi-source-rag-system.git
cd multi-source-rag-system
```

**2. Create conda environment**
```bash
conda create -n dataflow-rag python=3.11 -y
conda activate dataflow-rag
pip install -r requirements.txt
```

**3. Set your DeepSeek API key**
```bash
cp .env.example .env
# Edit .env and add your DEEPSEEK_API_KEY
```

**4. Build the index**
```bash
python -m src.indexer
```

**5. Run test queries**
```bash
python run_queries.py
```

**6. Start the web UI**
```bash
uvicorn main:app --port 8000
# Open http://localhost:8000
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web UI |
| `POST` | `/query` | Ask a question |
| `GET` | `/debug` | View intermediate retrieval results |
| `GET` | `/health` | Health check |
| `POST` | `/rebuild-index` | Force index rebuild |

**Example request:**
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What should the connection timeout be set to?"}'
```

**Example response:**
```json
{
  "answer": "According to the official documentation, the default connection timeout is 30 seconds...",
  "sources": ["data/docs/error_codes.md", "data/forums/posts.json"],
  "source_counts": {"docs": 1, "forums": 3, "blogs": 1},
  "conflicts": "⚠ Conflicting connection_timeout values (blogs: 45, forums: 60, docs: 30). Trusting docs value: 30.",
  "log": "Q='What should the connection timeout be set to?' | sources=[1 from blogs, 1 from docs, 3 from forums]",
  "latency_ms": 3394
}
```

---

## Conflict Detection Example

The system intentionally contains contradicting information across sources:

| Source | Timeout Value |
|--------|-------------|
| **docs** (official) | **30 seconds** ✅ |
| blogs | 45 seconds |
| forums | 60 seconds |

When a user asks about connection timeout, the system detects the contradiction and resolves it by trusting the most authoritative source (docs).

---

## Example Queries

| Query | Key Feature Demonstrated |
|-------|--------------------------|
| How do I install DataFlow Pro? | Documentation retrieval |
| How can I optimize performance? | Blog retrieval |
| What is ERR_601? | Docs + forums combined |
| What should the connection timeout be? | **Conflict detection** ⭐ |
| Does DataFlow Pro support Mars database? | Graceful decline |
| Give me a deployment checklist | Multi-source synthesis |

Full 10 queries with real system responses are in `report.md`.

---

## Report

See [`report.md`](report.md) for:
- Detailed chunking strategy decisions
- Retrieval system design
- Reranking mechanism analysis
- Conflict handling approach
- Performance analysis with real latency data
