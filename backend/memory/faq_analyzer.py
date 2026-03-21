"""
FAQ pattern analyzer — clusters user queries to surface frequent topics
and knowledge gaps for admin review.

Uses DBSCAN on BGE embeddings to find natural query clusters without
requiring a pre-specified cluster count.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from sklearn.cluster import DBSCAN

import aiosqlite

from backend.config import SESSIONS_DB
from backend.ingestion.embedder import embed_documents
from backend.lib.logger import get_logger

log = get_logger("memory.faq_analyzer")

DB_PATH = str(SESSIONS_DB)

# ── Constants ────────────────────────────────────────────────────────────────

MAX_QUERIES = 500          # Cap to prevent slow embedding
DBSCAN_EPS = 0.3           # Cosine distance threshold (lower = tighter clusters)
DBSCAN_MIN_SAMPLES = 2     # Minimum queries to form a cluster
TOP_N_CLUSTERS = 10        # Return at most N clusters


# ── Helpers ──────────────────────────────────────────────────────────────────

def _cutoff_iso(days: int) -> str:
    """Return ISO timestamp for N days ago."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _build_clusters(
    queries: list[str],
    embeddings: np.ndarray,
) -> list[dict[str, Any]]:
    """Run DBSCAN on embeddings and return cluster summaries sorted by size."""
    if len(queries) < DBSCAN_MIN_SAMPLES:
        # Not enough data to cluster — return each query as its own cluster
        return [
            {
                "cluster_id": i,
                "count": 1,
                "representative_query": q,
                "sample_queries": [q],
            }
            for i, q in enumerate(queries)
        ]

    clusterer = DBSCAN(eps=DBSCAN_EPS, min_samples=DBSCAN_MIN_SAMPLES, metric="cosine")
    labels: np.ndarray = clusterer.fit_predict(embeddings)

    # Group queries by cluster label (-1 = noise / unclustered)
    cluster_map: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        label_int = int(label)
        if label_int == -1:
            continue  # skip noise
        cluster_map.setdefault(label_int, []).append(idx)

    clusters: list[dict[str, Any]] = []
    for label_int, indices in cluster_map.items():
        member_queries = [queries[i] for i in indices]
        # Representative = query closest to cluster centroid
        centroid = embeddings[indices].mean(axis=0)
        dists = np.linalg.norm(embeddings[indices] - centroid, axis=1)
        rep_idx = indices[int(np.argmin(dists))]
        clusters.append({
            "cluster_id": label_int,
            "count": len(indices),
            "representative_query": queries[rep_idx],
            "sample_queries": member_queries[:5],  # cap samples
        })

    # Sort by count descending
    clusters.sort(key=lambda c: c["count"], reverse=True)
    return clusters[:TOP_N_CLUSTERS]


# ── Public API ───────────────────────────────────────────────────────────────

async def analyze_query_patterns(days: int = 30) -> list[dict[str, Any]]:
    """
    Fetch recent user messages, embed them, cluster by similarity.
    Returns top clusters sorted by frequency.
    """
    cutoff = _cutoff_iso(days)

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """
            SELECT content FROM messages
            WHERE role = 'user' AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (cutoff, MAX_QUERIES),
        )
        rows = await cursor.fetchall()

    queries = [row["content"] for row in rows]

    if not queries:
        log.info("No user queries found for pattern analysis", extra={"days": days})
        return []

    log.info(
        "Embedding queries for pattern analysis",
        extra={"count": len(queries), "days": days},
    )
    embeddings = embed_documents(queries)
    emb_array = np.array(embeddings)

    clusters = _build_clusters(queries, emb_array)
    log.info(
        "Query pattern analysis complete",
        extra={"clusters_found": len(clusters), "total_queries": len(queries)},
    )
    return clusters


async def identify_gaps(days: int = 30) -> list[dict[str, Any]]:
    """
    Find queries associated with negative signals (thumbs-down feedback
    or escalations) and cluster them to surface knowledge gaps.
    """
    cutoff = _cutoff_iso(days)
    gap_queries: list[tuple[str, str]] = []  # (query_text, gap_type)

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # 1. Thumbs-down feedback → find preceding user query
        cursor = await conn.execute(
            """
            SELECT f.session_id, f.message_index
            FROM feedback f
            WHERE f.rating = 'down' AND f.created_at >= ?
            ORDER BY f.created_at DESC
            LIMIT ?
            """,
            (cutoff, MAX_QUERIES),
        )
        down_records = await cursor.fetchall()

        for rec in down_records:
            msg_cursor = await conn.execute(
                """
                SELECT role, content FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (rec["session_id"],),
            )
            msgs = list(await msg_cursor.fetchall())
            idx = rec["message_index"]
            # Find user message preceding the rated assistant message
            if 0 < idx <= len(msgs) and msgs[idx - 1]["role"] == "user":
                gap_queries.append((msgs[idx - 1]["content"], "thumbs_down"))

        # 2. Escalations → find user queries from escalated sessions
        cursor = await conn.execute(
            """
            SELECT DISTINCT e.session_id
            FROM escalations e
            WHERE e.created_at >= ?
            LIMIT ?
            """,
            (cutoff, MAX_QUERIES),
        )
        esc_sessions = await cursor.fetchall()

        for esc in esc_sessions:
            msg_cursor = await conn.execute(
                """
                SELECT content FROM messages
                WHERE session_id = ? AND role = 'user'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (esc["session_id"],),
            )
            row = await msg_cursor.fetchone()
            if row:
                gap_queries.append((row["content"], "escalation"))

    if not gap_queries:
        log.info("No knowledge gap queries found", extra={"days": days})
        return []

    texts = [q for q, _ in gap_queries]
    types = [t for _, t in gap_queries]

    log.info(
        "Embedding gap queries for analysis",
        extra={"count": len(texts), "days": days},
    )
    embeddings = embed_documents(texts)
    emb_array = np.array(embeddings)

    clusters = _build_clusters(texts, emb_array)

    # Annotate each cluster with the dominant gap type
    for cluster in clusters:
        sample_indices = [
            i for i, q in enumerate(texts) if q in cluster["sample_queries"]
        ]
        cluster_types = [types[i] for i in sample_indices]
        # Dominant type
        td_count = cluster_types.count("thumbs_down")
        esc_count = cluster_types.count("escalation")
        cluster["gap_type"] = "thumbs_down" if td_count >= esc_count else "escalation"

    log.info(
        "Knowledge gap analysis complete",
        extra={"clusters_found": len(clusters), "total_gap_queries": len(texts)},
    )
    return clusters
