"""
Verified Q&A semantic cache — stores admin-approved answers in ChromaDB.

Two-tier confidence matching:
- High (>= high_threshold): return answer directly, no disclaimer
- Medium (>= medium_threshold): return answer with disclaimer
- Below medium: cache miss, fall through to orchestrator
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from backend.config import settings
from backend.ingestion.embedder import embed_query
from backend.lib.logger import get_logger
from backend.retrieval.vector_store import get_collection

log = get_logger("memory.semantic_cache")

COLLECTION_NAME = "verified_answers"


@dataclass
class CacheResult:
    """Result from a semantic cache lookup."""
    answer: str
    sources: list[dict[str, Any]]
    confidence: str  # "high" | "medium"
    disclaimer: str | None


def _get_similarity(distance: float) -> float:
    """Convert ChromaDB cosine distance to similarity score.

    ChromaDB returns distance (0 = identical, 2 = opposite for cosine).
    Similarity = 1 - distance for cosine space.
    """
    return 1.0 - distance


def check_cache(query: str) -> CacheResult | None:
    """
    Check if a similar verified answer exists in the cache.

    Returns CacheResult if similarity meets threshold, else None.
    Synchronous because ChromaDB and embedder are synchronous.
    """
    col = get_collection(COLLECTION_NAME)
    if col.count() == 0:
        return None

    query_embedding = embed_query(query)
    results: dict[str, Any] = col.query(  # type: ignore[assignment]
        query_embeddings=[query_embedding],  # type: ignore[arg-type]
        n_results=1,
        include=["documents", "metadatas", "distances"],
    )

    if not results["ids"] or not results["ids"][0]:
        return None

    distance: float = results["distances"][0][0]
    similarity = _get_similarity(distance)
    metadata: dict[str, Any] = results["metadatas"][0][0]
    answer: str = results["documents"][0][0]

    # Parse sources from metadata
    sources: list[dict[str, Any]] = []
    sources_raw = metadata.get("sources", "")
    if sources_raw:
        try:
            sources = json.loads(str(sources_raw))
        except (json.JSONDecodeError, TypeError):
            pass

    if similarity >= settings.cache_high_threshold:
        log.info(
            "Cache hit (high confidence)",
            extra={"similarity": round(similarity, 4), "query": query[:80]},
        )
        return CacheResult(
            answer=answer,
            sources=sources,
            confidence="high",
            disclaimer=None,
        )

    if similarity >= settings.cache_medium_threshold:
        log.info(
            "Cache hit (medium confidence)",
            extra={"similarity": round(similarity, 4), "query": query[:80]},
        )
        return CacheResult(
            answer=answer,
            sources=sources,
            confidence="medium",
            disclaimer="Based on a similar previously answered question. Please verify the details apply to your specific situation.",
        )

    log.debug(
        "Cache miss",
        extra={"similarity": round(similarity, 4), "query": query[:80]},
    )
    return None


def add_verified_answer(question: str, answer: str, sources: list[dict[str, Any]]) -> str:
    """
    Add a verified Q&A pair to the cache. Returns the document ID.

    Synchronous because ChromaDB and embedder are synchronous.
    """
    doc_id = str(uuid.uuid4())
    col = get_collection(COLLECTION_NAME)
    embedding = embed_query(question)

    col.add(
        ids=[doc_id],
        embeddings=[embedding],  # type: ignore[arg-type]
        documents=[answer],
        metadatas=[{
            "question": question,
            "sources": json.dumps(sources),
        }],
    )
    log.info("Added verified answer", extra={"id": doc_id, "question": question[:80]})
    return doc_id


def remove_verified_answer(answer_id: str) -> None:
    """Remove a verified answer from the cache."""
    col = get_collection(COLLECTION_NAME)
    col.delete(ids=[answer_id])
    log.info("Removed verified answer", extra={"id": answer_id})


def list_verified_answers() -> list[dict[str, Any]]:
    """Return all cached verified answers."""
    col = get_collection(COLLECTION_NAME)
    if col.count() == 0:
        return []

    results: dict[str, Any] = col.get(include=["documents", "metadatas"])  # type: ignore[assignment]
    output: list[dict[str, Any]] = []
    docs: list[str] = results["documents"] or []
    metas: list[dict[str, Any]] = results["metadatas"] or []
    for doc_id, doc, meta in zip(results["ids"], docs, metas):
        sources: list[dict[str, Any]] = []
        sources_raw = meta.get("sources", "")
        if sources_raw:
            try:
                sources = json.loads(str(sources_raw))
            except (json.JSONDecodeError, TypeError):
                pass
        output.append({
            "id": doc_id,
            "question": meta.get("question", ""),
            "answer": doc,
            "sources": sources,
        })
    return output
