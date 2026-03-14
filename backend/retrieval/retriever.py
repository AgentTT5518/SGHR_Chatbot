"""
RAG retriever: embeds a query and returns the most relevant chunks
from both the Employment Act and MOM guidelines collections.
"""
from __future__ import annotations

from backend.ingestion.embedder import embed_query
from backend.retrieval import vector_store

# Relative threshold floor: never filter tighter than this distance.
# Tune empirically after ingestion.
THRESHOLD_FLOOR = 0.25
THRESHOLD_MULTIPLIER = 1.5

# Section 2 keywords that trigger automatic definition inclusion
DEFINITION_KEYWORDS = {
    "workman", "employee", "employer", "basic rate of pay",
    "salary", "ordinary rate of pay", "shift worker", "part-time employee",
    "contract of service", "apprentice",
}


def retrieve(query: str, n_per_collection: int = 10) -> list[dict]:
    """
    Retrieve the most relevant chunks for a query.
    Queries both collections with n_per_collection each, merges and globally ranks,
    applies a relative threshold (with floor), and returns top 8.
    """
    q_embedding = embed_query(query)

    ea_results = vector_store.query("employment_act", q_embedding, n=n_per_collection)
    mom_results = vector_store.query("mom_guidelines", q_embedding, n=n_per_collection)

    combined = ea_results + mom_results
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
