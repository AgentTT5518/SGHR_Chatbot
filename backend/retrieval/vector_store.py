"""
ChromaDB wrapper for querying document collections.
"""
from __future__ import annotations

import chromadb
from chromadb import Collection

from backend.config import CHROMA_DIR

_client: chromadb.PersistentClient | None = None
_collections: dict[str, Collection] = {}


def get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def get_collection(name: str) -> Collection:
    if name not in _collections:
        _collections[name] = get_client().get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )
    return _collections[name]


def query(collection_name: str, query_embedding: list[float], n: int = 10) -> list[dict]:
    """
    Query a ChromaDB collection.
    Returns list of {id, text, metadata, distance} dicts sorted by distance (ascending).
    """
    col = get_collection(collection_name)
    if col.count() == 0:
        return []

    results = col.query(
        query_embeddings=[query_embedding],
        n_results=min(n, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    output = []
    for doc_id, doc, meta, dist in zip(
        results["ids"][0],
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        output.append({"id": doc_id, "text": doc, "metadata": meta, "distance": dist})
    return output


def get_all_documents(collection_name: str) -> list[dict]:
    """
    Fetch every document from a collection (used for TF-IDF fitting).
    Returns list of {id, text, metadata} dicts.
    """
    col = get_collection(collection_name)
    if col.count() == 0:
        return []
    results = col.get(include=["documents", "metadatas"])
    output = []
    for doc_id, doc, meta in zip(
        results["ids"],
        results["documents"],
        results["metadatas"],
    ):
        output.append({"id": doc_id, "text": doc, "metadata": meta})
    return output


def is_ready() -> bool:
    """Check if both collections exist and have documents."""
    try:
        client = get_client()
        names = [c.name for c in client.list_collections()]
        if "employment_act" not in names or "mom_guidelines" not in names:
            return False
        return (
            get_collection("employment_act").count() > 0
            and get_collection("mom_guidelines").count() > 0
        )
    except Exception:
        return False
