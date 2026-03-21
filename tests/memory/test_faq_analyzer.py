"""
Tests for backend.memory.faq_analyzer — mock SQLite and embedder,
verify clustering logic and edge cases.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from backend.memory.faq_analyzer import (
    analyze_query_patterns,
    identify_gaps,
    _build_clusters,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_embedding(seed: float) -> list[float]:
    """Create a deterministic 768-dim embedding from a seed value."""
    rng = np.random.RandomState(int(seed * 1000))
    vec = rng.randn(768).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return vec.tolist()


def _make_similar_embeddings(base_seed: float, n: int) -> list[list[float]]:
    """Create N similar embeddings (small perturbations of a base)."""
    rng = np.random.RandomState(int(base_seed * 1000))
    base = rng.randn(768).astype(np.float32)
    base /= np.linalg.norm(base)
    result = []
    for i in range(n):
        noise = rng.randn(768).astype(np.float32) * 0.01
        vec = base + noise
        vec /= np.linalg.norm(vec)
        result.append(vec.tolist())
    return result


# ── _build_clusters unit tests ──────────────────────────────────────────────


def test_build_clusters_empty():
    clusters = _build_clusters([], np.array([]).reshape(0, 768))
    assert clusters == []


def test_build_clusters_single_query():
    emb = np.array([_make_embedding(1.0)])
    clusters = _build_clusters(["What is leave?"], emb)
    assert len(clusters) == 1
    assert clusters[0]["count"] == 1
    assert clusters[0]["representative_query"] == "What is leave?"


def test_build_clusters_groups_similar():
    """Two groups of similar queries should form two clusters."""
    group_a = ["What is annual leave?", "How many days annual leave?", "Annual leave entitlement?"]
    group_b = ["What is CPF?", "CPF contribution rates?", "How does CPF work?"]

    emb_a = _make_similar_embeddings(1.0, 3)
    emb_b = _make_similar_embeddings(99.0, 3)
    embeddings = np.array(emb_a + emb_b)

    clusters = _build_clusters(group_a + group_b, embeddings)
    assert len(clusters) == 2
    # Sorted by count descending, both have 3
    assert all(c["count"] == 3 for c in clusters)


def test_build_clusters_caps_at_top_n():
    """Should return at most TOP_N_CLUSTERS clusters."""
    queries = [f"Query {i}" for i in range(100)]
    # Each pair forms its own cluster with distinct embeddings
    embeddings = []
    for i in range(50):
        embeddings.extend(_make_similar_embeddings(float(i), 2))
    emb_array = np.array(embeddings)

    clusters = _build_clusters(queries, emb_array)
    assert len(clusters) <= 10


# ── analyze_query_patterns ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_empty_messages():
    """No messages → empty patterns list."""
    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall.return_value = []
    mock_conn.execute.return_value = mock_cursor
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch("backend.memory.faq_analyzer.aiosqlite.connect", return_value=mock_conn):
        result = await analyze_query_patterns(days=30)

    assert result == []


@pytest.mark.asyncio
async def test_analyze_few_messages():
    """Fewer than min_samples queries — returns individual entries without error."""
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, key: "What is annual leave?"

    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall.return_value = [mock_row]
    mock_conn.execute.return_value = mock_cursor
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch("backend.memory.faq_analyzer.aiosqlite.connect", return_value=mock_conn), \
         patch("backend.memory.faq_analyzer.embed_documents", return_value=[_make_embedding(1.0)]):
        result = await analyze_query_patterns(days=30)

    assert len(result) == 1
    assert result[0]["count"] == 1


@pytest.mark.asyncio
async def test_analyze_normal_clustering():
    """Multiple similar queries should cluster together."""
    queries = ["What is annual leave?", "How many days annual leave?", "Annual leave entitlement"]

    mock_rows = []
    for q in queries:
        row = MagicMock()
        row.__getitem__ = lambda self, key, q=q: q
        mock_rows.append(row)

    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall.return_value = mock_rows
    mock_conn.execute.return_value = mock_cursor
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    similar_embs = _make_similar_embeddings(1.0, 3)

    with patch("backend.memory.faq_analyzer.aiosqlite.connect", return_value=mock_conn), \
         patch("backend.memory.faq_analyzer.embed_documents", return_value=similar_embs):
        result = await analyze_query_patterns(days=7)

    assert len(result) >= 1
    # The cluster with all 3 queries should exist
    assert any(c["count"] == 3 for c in result)


# ── identify_gaps ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_identify_gaps_empty():
    """No feedback or escalations → empty gaps."""
    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall.return_value = []
    mock_cursor.fetchone.return_value = None
    mock_conn.execute.return_value = mock_cursor
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch("backend.memory.faq_analyzer.aiosqlite.connect", return_value=mock_conn):
        result = await identify_gaps(days=30)

    assert result == []


@pytest.mark.asyncio
async def test_identify_gaps_thumbs_down():
    """Thumbs-down feedback should produce gap clusters."""
    # Setup: one thumbs-down record pointing to message_index=1
    feedback_row = MagicMock()
    feedback_row.__getitem__ = lambda self, key: {
        "session_id": "sess-1", "message_index": 1,
    }[key]

    user_msg = MagicMock()
    user_msg.__getitem__ = lambda self, key: {
        "role": "user", "content": "How to calculate overtime?",
    }[key]
    asst_msg = MagicMock()
    asst_msg.__getitem__ = lambda self, key: {
        "role": "assistant", "content": "I'm not sure about that.",
    }[key]

    # Track call count to differentiate queries
    call_count = {"n": 0}

    async def mock_execute(sql, params=None):
        call_count["n"] += 1
        cursor = AsyncMock()
        if "FROM feedback" in sql:
            cursor.fetchall.return_value = [feedback_row]
        elif "FROM messages" in sql and "ORDER BY" in sql and "ASC" in sql:
            cursor.fetchall.return_value = [user_msg, asst_msg]
        elif "FROM escalations" in sql:
            cursor.fetchall.return_value = []
        else:
            cursor.fetchall.return_value = []
            cursor.fetchone.return_value = None
        return cursor

    mock_conn = AsyncMock()
    mock_conn.execute = mock_execute
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch("backend.memory.faq_analyzer.aiosqlite.connect", return_value=mock_conn), \
         patch("backend.memory.faq_analyzer.embed_documents", return_value=[_make_embedding(1.0)]):
        result = await identify_gaps(days=30)

    # Single query → single entry (below min_samples for DBSCAN cluster)
    assert len(result) == 1
    assert result[0]["representative_query"] == "How to calculate overtime?"


@pytest.mark.asyncio
async def test_identify_gaps_days_filter():
    """Days parameter should be passed through to cutoff calculation."""
    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall.return_value = []
    mock_cursor.fetchone.return_value = None
    mock_conn.execute.return_value = mock_cursor
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch("backend.memory.faq_analyzer.aiosqlite.connect", return_value=mock_conn):
        result = await identify_gaps(days=7)

    assert result == []
    # Verify the cutoff was used (first execute call is the feedback query)
    first_call_args = mock_conn.execute.call_args_list[0]
    cutoff_param = first_call_args[0][1][0]  # (sql, (cutoff, limit))
    # Cutoff should be ~7 days ago, not 30
    assert "T" in cutoff_param  # ISO format
