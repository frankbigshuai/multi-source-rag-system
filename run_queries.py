"""
Run 10 predefined test queries against the RAG pipeline and print results.

Usage:
    python run_queries.py                    # uses existing index
    python run_queries.py --rebuild          # forces index rebuild
    python run_queries.py --output results.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, List

from src.pipeline import RAGPipeline
from src.utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

TEST_QUERIES: List[Dict[str, Any]] = [
    {
        "id": 1,
        "question": "How do I install DataFlow Pro?",
        "expected_source": "docs",
        "note": "Should pull from install_guide.md"
    },
    {
        "id": 2,
        "question": "My system is running slowly. How can I optimize performance?",
        "expected_source": "blogs",
        "note": "Performance tuning — should pull from performance_tips.txt"
    },
    {
        "id": 3,
        "question": "What is ERR_601 and how do I fix it?",
        "expected_source": "docs+forums",
        "note": "Error code in docs + forum discussion"
    },
    {
        "id": 4,
        "question": "What should the connection timeout be set to?",
        "expected_source": "conflict",
        "note": "Conflict trigger: docs=30s, blogs=45s, forums=60s"
    },
    {
        "id": 5,
        "question": "How do I configure plugins in v2.3? Are they compatible with v2.2?",
        "expected_source": "docs+forums",
        "note": "Version conflict: v2.3 plugins not backward compatible"
    },
    {
        "id": 6,
        "question": "Give me a complete deployment checklist for DataFlow Pro in production.",
        "expected_source": "all",
        "note": "Multi-source: docs + blogs + forums all contribute"
    },
    {
        "id": 7,
        "question": "What does ERR_999 mean and how should I debug it?",
        "expected_source": "docs+forums",
        "note": "BM25 exact match on ERR_999 (rare code)"
    },
    {
        "id": 8,
        "question": "Why is multi-threading not recommended on Windows for DataFlow Pro?",
        "expected_source": "docs+forums",
        "note": "Requires reasoning about POSIX threads on Windows"
    },
    {
        "id": 9,
        "question": "Does DataFlow Pro support connecting to a Mars database?",
        "expected_source": "none",
        "note": "Should politely decline — Mars DB not supported"
    },
    {
        "id": 10,
        "question": "What are the best practices summary for running DataFlow Pro in production?",
        "expected_source": "all",
        "note": "Multi-source synthesis from blogs + forums + docs"
    },
]

SEPARATOR = "=" * 80


def run_all_queries(pipeline: RAGPipeline, queries: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    if queries is None:
        queries = TEST_QUERIES
    results = []
    for item in queries:
        qid = item["id"]
        question = item["question"]
        print(f"\n{SEPARATOR}")
        print(f"Query {qid:02d}: {question}")
        print(f"Expected: {item['expected_source']} | Note: {item['note']}")
        print(SEPARATOR)

        try:
            response = pipeline.query(question)

            print(f"\nANSWER:\n{response.answer}")
            print(f"\nSOURCES: {response.sources}")
            print(f"SOURCE BREAKDOWN: {response.source_counts}")
            if response.conflicts:
                print(f"\n{response.conflicts}")
            print(f"\nLOG: {response.log_summary}")
            print(f"LATENCY: {response.latency_ms:.0f}ms")

            results.append({
                "id": qid,
                "question": question,
                "expected_source": item["expected_source"],
                "note": item["note"],
                "answer": response.answer,
                "sources": response.sources,
                "source_counts": response.source_counts,
                "conflicts": response.conflicts,
                "log": response.log_summary,
                "latency_ms": round(response.latency_ms, 1),
                "top_chunks": [
                    {
                        "chunk_id": sc.chunk.chunk_id,
                        "source_type": sc.chunk.source_type,
                        "rerank_score": round(sc.rerank_score, 4),
                        "rrf_score": round(sc.rrf_score, 6),
                    }
                    for sc in response.top_chunks
                ],
                "conflict_details": response.conflict_report.conflicts,
            })

        except Exception as e:
            logger.exception("Query %d failed", qid)
            print(f"ERROR: {e}")
            results.append({
                "id": qid,
                "question": question,
                "error": str(e),
            })

    return results


def main():
    parser = argparse.ArgumentParser(description="Run test queries against DataFlow RAG")
    parser.add_argument("--rebuild", action="store_true", help="Force index rebuild")
    parser.add_argument("--output", type=str, default=None, help="Save results to JSON file")
    parser.add_argument("--query-id", type=int, default=None, help="Run a single query by ID")
    args = parser.parse_args()

    print("Initializing RAG pipeline...")
    pipeline = RAGPipeline()
    if args.rebuild:
        pipeline.initialize(rebuild=True)
    else:
        try:
            pipeline.load_existing()
            print("Index loaded from disk.")
        except Exception as e:
            print(f"Could not load existing index ({e}). Building...")
            pipeline.initialize(rebuild=False)

    queries_to_run = TEST_QUERIES
    if args.query_id is not None:
        queries_to_run = [q for q in TEST_QUERIES if q["id"] == args.query_id]
        if not queries_to_run:
            print(f"No query with ID {args.query_id}")
            sys.exit(1)

    results = run_all_queries(pipeline, queries_to_run)

    print(f"\n{SEPARATOR}")
    print(f"Ran {len(results)} queries.")
    avg_latency = sum(r.get("latency_ms", 0) for r in results) / max(len(results), 1)
    print(f"Average latency: {avg_latency:.0f}ms")

    if args.output:
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "total_queries": len(results),
            "average_latency_ms": round(avg_latency, 1),
            "results": results,
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
