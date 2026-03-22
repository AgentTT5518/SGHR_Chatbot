"""
RAG retriever: embeds a query and returns the most relevant chunks
from both the Employment Act and MOM guidelines collections.
Supports "semantic" (cosine distance only) and "hybrid" (semantic + TF-IDF with RRF) modes.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from backend.config import settings
from backend.ingestion.embedder import embed_query
from backend.lib.logger import get_logger
from backend.retrieval import vector_store

log = get_logger("retrieval.retriever")

# Retrieval constants — now configurable via settings/env.
# Legacy module-level references point to settings for backward compat.
THRESHOLD_FLOOR = settings.threshold_floor if hasattr(settings, "threshold_floor") else 0.25
THRESHOLD_MULTIPLIER = settings.threshold_multiplier if hasattr(settings, "threshold_multiplier") else 1.5
_RRF_K = settings.rrf_k if hasattr(settings, "rrf_k") else 60
_MAX_RESULTS = settings.max_retrieval_results if hasattr(settings, "max_retrieval_results") else 8

# Section 2 keywords that trigger automatic definition inclusion
DEFINITION_KEYWORDS = {
    "workman", "employee", "employer", "basic rate of pay",
    "salary", "ordinary rate of pay", "shift worker", "part-time employee",
    "contract of service", "apprentice",
}


def retrieve(
    query: str,
    n_per_collection: int = 10,
    include_embeddings: bool = False,
) -> list[dict]:
    """
    Retrieve the most relevant chunks for a query.
    Uses hybrid (semantic + keyword) mode by default; falls back to semantic only.
    """
    if settings.retrieval_mode == "hybrid":
        return _hybrid_retrieve(query, n_per_collection, include_embeddings)
    return _semantic_retrieve(query, n_per_collection, include_embeddings)


def retrieve_from_collection(
    query: str,
    collection: str,
    n: int = 10,
    section_filter: str | None = None,
    include_embeddings: bool = False,
) -> list[dict]:
    """
    Retrieve chunks from a single collection.
    Optionally filter by metadata (e.g. section_filter="Part IV" filters by the 'part' field).
    When include_embeddings is True, skips _apply_threshold (caller handles filtering).
    """
    q_embedding = embed_query(query)
    where: dict | None = None
    if section_filter:
        where = {"part": section_filter}
    results = vector_store.query(
        collection, q_embedding, n=n, where=where,
        include_embeddings=include_embeddings,
    )
    if include_embeddings:
        return results
    return _apply_threshold(results)


def retrieve_multi(
    queries: list[str],
    n_per_collection: int = 10,
    collection: str | None = None,
    section_filter: str | None = None,
    include_embeddings: bool = False,
) -> list[dict]:
    """
    Retrieve for multiple query variants in parallel, merge with generalized RRF.
    If collection is set, searches a single collection; otherwise searches all.
    Returns at most _MAX_RESULTS chunks.
    """
    if not queries:
        return []

    def _retrieve_single(q: str) -> list[dict]:
        if collection:
            return retrieve_from_collection(
                q, collection, n=n_per_collection,
                section_filter=section_filter,
                include_embeddings=include_embeddings,
            )
        return retrieve(
            q, n_per_collection=n_per_collection,
            include_embeddings=include_embeddings,
        )

    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        result_lists = list(pool.map(_retrieve_single, queries))

    merged = _reciprocal_rank_fusion(*result_lists)
    return merged[:_MAX_RESULTS]


def _semantic_retrieve(
    query: str,
    n_per_collection: int,
    include_embeddings: bool = False,
) -> list[dict]:
    """Pure semantic retrieval (original logic)."""
    q_embedding = embed_query(query)
    ea_results = vector_store.query(
        "employment_act", q_embedding, n=n_per_collection,
        include_embeddings=include_embeddings,
    )
    mom_results = vector_store.query(
        "mom_guidelines", q_embedding, n=n_per_collection,
        include_embeddings=include_embeddings,
    )
    combined = ea_results + mom_results
    if include_embeddings:
        return combined
    return _apply_threshold(combined)


def _hybrid_retrieve(
    query: str,
    n_per_collection: int,
    include_embeddings: bool = False,
) -> list[dict]:
    """Hybrid retrieval: semantic + TF-IDF keyword search merged with RRF."""
    q_embedding = embed_query(query)
    ea_results = vector_store.query(
        "employment_act", q_embedding, n=n_per_collection,
        include_embeddings=include_embeddings,
    )
    mom_results = vector_store.query(
        "mom_guidelines", q_embedding, n=n_per_collection,
        include_embeddings=include_embeddings,
    )
    semantic_results = ea_results + mom_results

    keyword_results: list[dict] = []
    try:
        from backend.retrieval.keyword_search import get_searcher
        keyword_results = get_searcher().search(query, n=n_per_collection * 2)
    except Exception:
        log.warning("Keyword search failed, falling back to semantic only", exc_info=True)

    if not keyword_results:
        if include_embeddings:
            return semantic_results
        return _apply_threshold(semantic_results)

    merged = _reciprocal_rank_fusion(semantic_results, keyword_results)
    return merged[:_MAX_RESULTS]


def _reciprocal_rank_fusion(
    *ranked_lists: list[dict],
    k: int = _RRF_K,
) -> list[dict]:
    """
    Merge N ranked lists using Reciprocal Rank Fusion.
    Uses doc['id'] as the dedup key (falls back to text[:100] if id is missing).
    """
    scores: dict[str, float] = {}
    docs: dict[str, dict] = {}

    for ranked_list in ranked_lists:
        for rank, doc in enumerate(ranked_list):
            key = doc.get("id") or doc["text"][:100]
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
    return filtered[:_MAX_RESULTS]


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
