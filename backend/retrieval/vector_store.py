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


def query(
    collection_name: str,
    query_embedding: list[float],
    n: int = 10,
    where: dict | None = None,
    include_embeddings: bool = False,
) -> list[dict]:
    """
    Query a ChromaDB collection.
    Returns list of {id, text, metadata, distance} dicts sorted by distance (ascending).
    Optional `where` dict is passed directly to ChromaDB as a metadata filter.
    When `include_embeddings` is True, each result also contains an `embedding` field.
    """
    col = get_collection(collection_name)
    if col.count() == 0:
        return []

    include_fields = ["documents", "metadatas", "distances"]
    if include_embeddings:
        include_fields.append("embeddings")

    query_kwargs: dict = {
        "query_embeddings": [query_embedding],
        "n_results": min(n, col.count()),
        "include": include_fields,
    }
    if where:
        query_kwargs["where"] = where

    results = col.query(**query_kwargs)

    embeddings_list = results.get("embeddings", [None])[0] if include_embeddings else None

    output = []
    for i, (doc_id, doc, meta, dist) in enumerate(zip(
        results["ids"][0],
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    )):
        entry: dict = {"id": doc_id, "text": doc, "metadata": meta, "distance": dist}
        if include_embeddings and embeddings_list is not None:
            entry["embedding"] = embeddings_list[i]
        output.append(entry)
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
