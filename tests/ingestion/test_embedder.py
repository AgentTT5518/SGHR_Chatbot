"""
Tests for backend.ingestion.embedder

Mocks SentenceTransformer so the 440 MB model is never downloaded.
"""
from __future__ import annotations

import numpy as np
from unittest.mock import MagicMock, patch

import pytest

import backend.ingestion.embedder as embedder_mod
from backend.ingestion.embedder import embed_documents, embed_query, get_model


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_mock_model(dim: int = 4) -> MagicMock:
    """Return a mock SentenceTransformer that produces fixed-size embeddings."""
    mock = MagicMock()
    mock.encode.side_effect = lambda texts, **kwargs: np.ones((len(texts), dim))
    return mock


@pytest.fixture(autouse=True)
def reset_model_singleton(monkeypatch):
    """Reset the module-level _model singleton before each test."""
    monkeypatch.setattr(embedder_mod, "_model", None)


# ── get_model ─────────────────────────────────────────────────────────────────

def test_get_model_lazy_loads():
    mock = _make_mock_model()
    with patch("backend.ingestion.embedder.SentenceTransformer", return_value=mock) as mock_cls:
        model = get_model()
    mock_cls.assert_called_once()
    assert model is mock


def test_get_model_singleton(monkeypatch):
    mock = _make_mock_model()
    with patch("backend.ingestion.embedder.SentenceTransformer", return_value=mock) as mock_cls:
        m1 = get_model()
        m2 = get_model()
    mock_cls.assert_called_once()  # only one instantiation
    assert m1 is m2


# ── embed_documents ───────────────────────────────────────────────────────────

def test_embed_documents_returns_list_of_lists():
    mock = _make_mock_model(dim=4)
    monkeypatch_model = MagicMock(return_value=mock)
    with patch("backend.ingestion.embedder.SentenceTransformer", monkeypatch_model):
        result = embed_documents(["text one", "text two"])
    assert isinstance(result, list)
    assert len(result) == 2
    assert isinstance(result[0], list)


def test_embed_documents_correct_dimension():
    mock = _make_mock_model(dim=768)
    with patch("backend.ingestion.embedder.SentenceTransformer", return_value=mock):
        result = embed_documents(["query"])
    assert len(result[0]) == 768


def test_embed_documents_empty_list():
    mock = MagicMock()
    mock.encode.side_effect = lambda texts, **kwargs: np.ones((len(texts), 4))
    with patch("backend.ingestion.embedder.SentenceTransformer", return_value=mock):
        result = embed_documents([])
    assert result == []


# ── embed_query ───────────────────────────────────────────────────────────────

def test_embed_query_returns_flat_list():
    mock = _make_mock_model(dim=4)
    with patch("backend.ingestion.embedder.SentenceTransformer", return_value=mock):
        result = embed_query("What is annual leave?")
    assert isinstance(result, list)
    assert len(result) == 4


def test_embed_query_adds_bge_prefix():
    mock = MagicMock()
    mock.encode.side_effect = lambda texts, **kwargs: np.ones((len(texts), 4))
    with patch("backend.ingestion.embedder.SentenceTransformer", return_value=mock):
        embed_query("overtime pay")
    called_text = mock.encode.call_args[0][0][0]
    assert called_text.startswith("Represent this sentence for searching relevant passages:")
    assert "overtime pay" in called_text
