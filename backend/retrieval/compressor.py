"""
Contextual compressor — filters retrieval results by embedding similarity.

Uses stored chunk embeddings from ChromaDB and the query embedding
to compute cosine similarity (dot product on normalized BGE vectors).
Replaces _apply_threshold when enabled — a stricter, more principled filter.
"""
from __future__ import annotations

from backend.config import settings
from backend.lib.logger import get_logger

log = get_logger("retrieval.compressor")


def compress(
    query_embedding: list[float],
    chunks: list[dict],
    threshold: float | None = None,
) -> list[dict]:
    """
    Filter chunks by cosine similarity to the query embedding.

    Args:
        query_embedding: The embedded query vector (normalized).
        chunks: List of chunk dicts, each with an 'embedding' field.
        threshold: Minimum cosine similarity to retain a chunk.
                   Defaults to settings.compression_threshold.

    Returns:
        Filtered list sorted by relevance_score descending. Each chunk
        gets a 'relevance_score' field added.
    """
    if not chunks:
        return []

    if threshold is None:
        threshold = settings.compression_threshold

    scored: list[dict] = []
    skipped = 0

    for chunk in chunks:
        embedding = chunk.get("embedding")
        if embedding is None:
            # No embedding available — keep the chunk but without a score
            log.warning(
                "Chunk missing embedding, keeping without score",
                extra={"chunk_id": chunk.get("id", "unknown")},
            )
            chunk["relevance_score"] = None
            scored.append(chunk)
            continue

        similarity = _dot_product(query_embedding, embedding)
        if similarity >= threshold:
            chunk["relevance_score"] = round(similarity, 4)
            scored.append(chunk)
        else:
            skipped += 1

    # Sort by relevance_score descending (None scores go to the end)
    scored.sort(
        key=lambda c: c.get("relevance_score") or 0.0,
        reverse=True,
    )

    if skipped > 0:
        log.info(
            "Contextual compression applied",
            extra={
                "input_count": len(chunks),
                "output_count": len(scored),
                "skipped": skipped,
                "threshold": threshold,
            },
        )

    return scored


def _dot_product(a: list[float], b: list[float]) -> float:
    """Compute dot product of two vectors (cosine similarity for normalized vectors)."""
    return sum(x * y for x, y in zip(a, b))
