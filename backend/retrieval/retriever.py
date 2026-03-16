"""
RAG retriever: embeds a query and returns the most relevant chunks
from both the Employment Act and MOM guidelines collections.
Supports "semantic" (cosine distance only) and "hybrid" (semantic + TF-IDF with RRF) modes.
"""
from __future__ import annotations

from backend.config import settings
from backend.ingestion.embedder import embed_query
from backend.lib.logger import get_logger
from backend.retrieval import vector_store

log = get_logger("retrieval.retriever")

# Relative threshold floor: never filter tighter than this distance.
# Tune empirically after ingestion.
THRESHOLD_FLOOR = 0.25
THRESHOLD_MULTIPLIER = 1.5

# RRF smoothing constant
_RRF_K = 60

# Section 2 keywords that trigger automatic definition inclusion
DEFINITION_KEYWORDS = {
    "workman", "employee", "employer", "basic rate of pay",
    "salary", "ordinary rate of pay", "shift worker", "part-time employee",
    "contract of service", "apprentice",
}


def retrieve(query: str, n_per_collection: int = 10) -> list[dict]:
    """
    Retrieve the most relevant chunks for a query.
    Uses hybrid (semantic + keyword) mode by default; falls back to semantic only.
    """
    if settings.retrieval_mode == "hybrid":
        return _hybrid_retrieve(query, n_per_collection)
    return _semantic_retrieve(query, n_per_collection)


def _semantic_retrieve(query: str, n_per_collection: int) -> list[dict]:
    """Pure semantic retrieval (original logic)."""
    q_embedding = embed_query(query)
    ea_results = vector_store.query("employment_act", q_embedding, n=n_per_collection)
    mom_results = vector_store.query("mom_guidelines", q_embedding, n=n_per_collection)
    combined = ea_results + mom_results
    return _apply_threshold(combined)


def _hybrid_retrieve(query: str, n_per_collection: int) -> list[dict]:
    """Hybrid retrieval: semantic + TF-IDF keyword search merged with RRF."""
    q_embedding = embed_query(query)
    ea_results = vector_store.query("employment_act", q_embedding, n=n_per_collection)
    mom_results = vector_store.query("mom_guidelines", q_embedding, n=n_per_collection)
    semantic_results = ea_results + mom_results

    keyword_results: list[dict] = []
    try:
        from backend.retrieval.keyword_search import get_searcher
        keyword_results = get_searcher().search(query, n=n_per_collection * 2)
    except Exception:
        log.warning("Keyword search failed, falling back to semantic only", exc_info=True)

    if not keyword_results:
        return _apply_threshold(semantic_results)

    merged = _reciprocal_rank_fusion(semantic_results, keyword_results)
    return merged[:8]


def _reciprocal_rank_fusion(
    semantic: list[dict],
    keyword: list[dict],
    k: int = _RRF_K,
) -> list[dict]:
    """
    Merge two ranked lists using Reciprocal Rank Fusion.
    Uses the first 100 chars of 'text' as a stable document key.
    """
    scores: dict[str, float] = {}
    docs: dict[str, dict] = {}

    for rank, doc in enumerate(semantic):
        key = doc["text"][:100]
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
        docs[key] = doc

    for rank, doc in enumerate(keyword):
        key = doc["text"][:100]
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
        if key not in docs:
            docs[key] = doc

    ranked_keys = sorted(scores, key=lambda x: scores[x], reverse=True)
    return [docs[key] for key in ranked_keys]


def _apply_threshold(combined: list[dict]) -> list[dict]:
    """Sort by distance, apply relative threshold with floor, cap at 8."""
    if not combined:
        return []
    combined.sort(key=lambda x: x["distance"])
    best = combined[0]["distance"]
    threshold = max(best * THRESHOLD_MULTIPLIER, THRESHOLD_FLOOR)
    filtered = [c for c in combined if c["distance"] <= threshold]
    return filtered[:8]


def needs_definitions(query: str, chunks: list[dict]) -> bool:
    """
    Return True if Section 2 (Definitions) should be prepended to context.
    Triggered when: query or chunk text references defined legal terms.
    """
    query_lower = query.lower()
    if any(kw in query_lower for kw in DEFINITION_KEYWORDS):
        return True
    for chunk in chunks:
        text_lower = chunk["text"].lower()
        if any(kw in text_lower for kw in DEFINITION_KEYWORDS):
            return True
    return False


def get_section_2() -> dict | None:
    """
    Retrieve the Employment Act Section 2 (Definitions) chunk(s).
    Returns the highest-relevance Section 2 chunk or None if not indexed.
    """
    q_embedding = embed_query("definitions employment act section 2")
    results = vector_store.query("employment_act", q_embedding, n=5)
    for r in results:
        meta = r.get("metadata", {})
        if str(meta.get("section_number", "")) == "2":
            return r
    return None
