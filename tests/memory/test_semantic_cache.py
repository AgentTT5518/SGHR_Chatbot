"""
Tests for backend.memory.semantic_cache — mock ChromaDB, test two-tier thresholds.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.memory.semantic_cache import (
    CacheResult,
    add_verified_answer,
    check_cache,
    list_verified_answers,
    remove_verified_answer,
)


@pytest.fixture
def mock_collection():
    """Return a mock ChromaDB collection."""
    col = MagicMock()
    col.count.return_value = 0
    return col


@pytest.fixture(autouse=True)
def _patch_collection(mock_collection):
    with patch("backend.memory.semantic_cache.get_collection", return_value=mock_collection):
        yield


@pytest.fixture(autouse=True)
def _patch_embedder():
    with patch("backend.memory.semantic_cache.embed_query", return_value=[0.1] * 768):
        yield


# ── Cache miss ───────────────────────────────────────────────────────────────


def test_cache_miss_empty_collection(mock_collection):
    mock_collection.count.return_value = 0
    result = check_cache("What is my leave entitlement?")
    assert result is None


def test_cache_miss_low_similarity(mock_collection):
    mock_collection.count.return_value = 1
    mock_collection.query.return_value = {
        "ids": [["id-1"]],
        "documents": [["Some answer"]],
        "metadatas": [[{"question": "Unrelated", "sources": "[]"}]],
        "distances": [[0.5]],  # similarity = 0.5 (below medium threshold)
    }
    result = check_cache("What is my leave entitlement?")
    assert result is None


# ── Cache hit (high confidence) ──────────────────────────────────────────────


def test_cache_hit_high_confidence(mock_collection):
    mock_collection.count.return_value = 1
    mock_collection.query.return_value = {
        "ids": [["id-1"]],
        "documents": [["You are entitled to 14 days annual leave."]],
        "metadatas": [[{
            "question": "How many days annual leave?",
            "sources": json.dumps([{"label": "EA Part IV"}]),
        }]],
        "distances": [[0.02]],  # similarity = 0.98 >= 0.95
    }
    result = check_cache("How many days annual leave do I get?")
    assert isinstance(result, CacheResult)
    assert result.confidence == "high"
    assert result.disclaimer is None
    assert "14 days" in result.answer
    assert len(result.sources) == 1


# ── Cache hit (medium confidence) ────────────────────────────────────────────


def test_cache_hit_medium_confidence(mock_collection):
    mock_collection.count.return_value = 1
    mock_collection.query.return_value = {
        "ids": [["id-2"]],
        "documents": [["Notice period is 1 month."]],
        "metadatas": [[{
            "question": "What is the notice period?",
            "sources": "[]",
        }]],
        "distances": [[0.08]],  # similarity = 0.92 (between 0.88 and 0.95)
    }
    result = check_cache("How long is my notice period?")
    assert isinstance(result, CacheResult)
    assert result.confidence == "medium"
    assert result.disclaimer is not None
    assert "similar" in result.disclaimer.lower()


# ── Add / Remove / List ──────────────────────────────────────────────────────


def test_add_verified_answer(mock_collection):
    doc_id = add_verified_answer(
        question="What is CPF?",
        answer="CPF is the Central Provident Fund.",
        sources=[{"label": "MOM"}],
    )
    assert isinstance(doc_id, str)
    mock_collection.add.assert_called_once()
    call_kwargs = mock_collection.add.call_args
    assert call_kwargs.kwargs["documents"] == ["CPF is the Central Provident Fund."]


def test_remove_verified_answer(mock_collection):
    remove_verified_answer("some-id")
    mock_collection.delete.assert_called_once_with(ids=["some-id"])


def test_list_verified_answers_empty(mock_collection):
    mock_collection.count.return_value = 0
    answers = list_verified_answers()
    assert answers == []


def test_list_verified_answers(mock_collection):
    mock_collection.count.return_value = 2
    mock_collection.get.return_value = {
        "ids": ["id-1", "id-2"],
        "documents": ["Answer 1", "Answer 2"],
        "metadatas": [
            {"question": "Q1", "sources": "[]"},
            {"question": "Q2", "sources": json.dumps([{"label": "Source"}])},
        ],
    }
    answers = list_verified_answers()
    assert len(answers) == 2
    assert answers[0]["question"] == "Q1"
    assert answers[1]["sources"] == [{"label": "Source"}]
