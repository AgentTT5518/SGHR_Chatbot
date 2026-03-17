"""
Tests for backend.retrieval.vector_store

Mocks chromadb.PersistentClient so no real DB is needed.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

import backend.retrieval.vector_store as vs_mod
from backend.retrieval.vector_store import (
    get_client,
    get_collection,
    is_ready,
    query,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_singletons(monkeypatch):
    """Reset module-level _client and _collections before each test."""
    monkeypatch.setattr(vs_mod, "_client", None)
    monkeypatch.setattr(vs_mod, "_collections", {})


def _mock_client(collection_names: list[str] = None, count: int = 10) -> MagicMock:
    client = MagicMock()
    col = MagicMock()
    col.count.return_value = count
    col.query.return_value = {
        "ids": [["id1", "id2"]],
        "documents": [["doc1", "doc2"]],
        "metadatas": [[{"source": "EA"}, {"source": "MOM"}]],
        "distances": [[0.1, 0.3]],
    }
    client.get_or_create_collection.return_value = col
    names = collection_names or ["employment_act", "mom_guidelines"]
    # MagicMock(name=n) sets mock's internal name, not .name attr — use PropertyMock
    col_mocks = []
    for n in names:
        m = MagicMock()
        m.name = n  # set as instance attribute so c.name returns the string
        col_mocks.append(m)
    client.list_collections.return_value = col_mocks
    return client, col


# ── get_client ────────────────────────────────────────────────────────────────

def test_get_client_lazy_loads():
    mock_client = MagicMock()
    with patch("backend.retrieval.vector_store.chromadb.PersistentClient", return_value=mock_client) as cls:
        client = get_client()
    cls.assert_called_once()
    assert client is mock_client


def test_get_client_singleton():
    mock_client = MagicMock()
    with patch("backend.retrieval.vector_store.chromadb.PersistentClient", return_value=mock_client) as cls:
        c1 = get_client()
        c2 = get_client()
    cls.assert_called_once()
    assert c1 is c2


# ── get_collection ────────────────────────────────────────────────────────────

def test_get_collection_creates_and_caches():
    mock_client, mock_col = _mock_client()
    with patch("backend.retrieval.vector_store.chromadb.PersistentClient", return_value=mock_client):
        col1 = get_collection("employment_act")
        col2 = get_collection("employment_act")
    mock_client.get_or_create_collection.assert_called_once()
    assert col1 is col2


def test_get_collection_cosine_space():
    mock_client, _ = _mock_client()
    with patch("backend.retrieval.vector_store.chromadb.PersistentClient", return_value=mock_client):
        get_collection("employment_act")
    _, kwargs = mock_client.get_or_create_collection.call_args
    assert kwargs["metadata"]["hnsw:space"] == "cosine"


# ── query ─────────────────────────────────────────────────────────────────────

def test_query_returns_structured_results():
    mock_client, mock_col = _mock_client(count=5)
    with patch("backend.retrieval.vector_store.chromadb.PersistentClient", return_value=mock_client):
        results = query("employment_act", [0.1, 0.2, 0.3], n=5)
    assert len(results) == 2
    assert results[0]["id"] == "id1"
    assert results[0]["text"] == "doc1"
    assert results[0]["metadata"] == {"source": "EA"}
    assert results[0]["distance"] == 0.1


def test_query_empty_collection_returns_empty():
    mock_client, mock_col = _mock_client(count=0)
    with patch("backend.retrieval.vector_store.chromadb.PersistentClient", return_value=mock_client):
        results = query("employment_act", [0.1, 0.2], n=5)
    assert results == []
    mock_col.query.assert_not_called()


def test_query_caps_n_results_at_collection_count():
    mock_client, mock_col = _mock_client(count=3)
    mock_col.query.return_value = {
        "ids": [["id1"]],
        "documents": [["d1"]],
        "metadatas": [[{"s": "x"}]],
        "distances": [[0.2]],
    }
    with patch("backend.retrieval.vector_store.chromadb.PersistentClient", return_value=mock_client):
        query("employment_act", [0.1], n=10)
    _, kwargs = mock_col.query.call_args
    assert kwargs["n_results"] == 3  # min(10, count=3)


# ── is_ready ──────────────────────────────────────────────────────────────────

def test_is_ready_true_when_both_collections_have_docs():
    mock_client, _ = _mock_client(
        collection_names=["employment_act", "mom_guidelines"], count=5
    )
    with patch("backend.retrieval.vector_store.chromadb.PersistentClient", return_value=mock_client):
        assert is_ready() is True


def test_is_ready_false_when_collection_missing():
    mock_client, _ = _mock_client(collection_names=["employment_act"])  # mom missing
    with patch("backend.retrieval.vector_store.chromadb.PersistentClient", return_value=mock_client):
        assert is_ready() is False


def test_is_ready_false_when_empty_collection():
    mock_client, _ = _mock_client(
        collection_names=["employment_act", "mom_guidelines"], count=0
    )
    with patch("backend.retrieval.vector_store.chromadb.PersistentClient", return_value=mock_client):
        assert is_ready() is False


def test_is_ready_false_on_exception():
    with patch("backend.retrieval.vector_store.chromadb.PersistentClient", side_effect=Exception("db error")):
        assert is_ready() is False
