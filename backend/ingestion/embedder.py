"""
Embedding wrapper using sentence-transformers BGE model.
"""
from __future__ import annotations

from sentence_transformers import SentenceTransformer

from backend.config import settings

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print(f"  Loading embedding model: {settings.embedding_model}")
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed_documents(texts: list[str], batch_size: int = 64) -> list[list[float]]:
    """Embed document chunks (no special prefix needed for BGE documents)."""
    model = get_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    return embeddings.tolist()


def embed_query(query: str) -> list[float]:
    """
    Embed a user query with the BGE retrieval instruction prefix.
    BGE recommends this prefix for query-side embeddings only.
    """
    model = get_model()
    prefixed = f"Represent this sentence for searching relevant passages: {query}"
    embedding = model.encode([prefixed], normalize_embeddings=True)
    return embedding[0].tolist()
