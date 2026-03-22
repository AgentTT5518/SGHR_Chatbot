"""
Tests for backend.retrieval.compressor

Uses pre-computed embeddings — no model loading required.
"""
from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from backend.retrieval.compressor import compress, _dot_product


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalized(vec: list[float]) -> list[float]:
    """Normalize a vector to unit length."""
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm > 0 else vec


# Unit vectors in different directions
_VEC_QUERY = _normalized([1.0, 0.0, 0.0])
_VEC_SIMILAR = _normalized([0.9, 0.1, 0.0])      # cos sim ≈ 0.994
_VEC_MODERATE = _normalized([0.6, 0.4, 0.0])      # cos sim ≈ 0.832
_VEC_DISSIMILAR = _normalized([0.1, 0.9, 0.0])    # cos sim ≈ 0.110


def _chunk(
    text: str,
    embedding: list[float] | None = None,
    chunk_id: str = "c1",
) -> dict:
    return {
        "id": chunk_id,
        "text": text,
        "metadata": {"source": "test"},
        "distance": 0.1,
        "embedding": embedding,
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestDotProduct:

    def test_identical_vectors(self):
        v = _normalized([1.0, 2.0, 3.0])
        assert abs(_dot_product(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert abs(_dot_product(a, b)) < 1e-6


class TestCompress:

    @patch("backend.retrieval.compressor.settings")
    def test_keeps_similar_chunks(self, mock_settings):
        mock_settings.compression_threshold = 0.45
        chunks = [
            _chunk("similar doc", embedding=_VEC_SIMILAR, chunk_id="c1"),
            _chunk("moderate doc", embedding=_VEC_MODERATE, chunk_id="c2"),
        ]
        result = compress(_VEC_QUERY, chunks)
        assert len(result) == 2
        assert all(c.get("relevance_score") is not None for c in result)

    @patch("backend.retrieval.compressor.settings")
    def test_drops_dissimilar_chunks(self, mock_settings):
        mock_settings.compression_threshold = 0.45
        chunks = [
            _chunk("similar doc", embedding=_VEC_SIMILAR, chunk_id="c1"),
            _chunk("dissimilar doc", embedding=_VEC_DISSIMILAR, chunk_id="c2"),
        ]
        result = compress(_VEC_QUERY, chunks)
        assert len(result) == 1
        assert result[0]["text"] == "similar doc"

    @patch("backend.retrieval.compressor.settings")
    def test_sorted_by_relevance_score_descending(self, mock_settings):
        mock_settings.compression_threshold = 0.1
        chunks = [
            _chunk("moderate doc", embedding=_VEC_MODERATE, chunk_id="c1"),
            _chunk("similar doc", embedding=_VEC_SIMILAR, chunk_id="c2"),
        ]
        result = compress(_VEC_QUERY, chunks)
        assert len(result) == 2
        assert result[0]["relevance_score"] >= result[1]["relevance_score"]

    @patch("backend.retrieval.compressor.settings")
    def test_empty_chunks_returns_empty(self, mock_settings):
        mock_settings.compression_threshold = 0.45
        result = compress(_VEC_QUERY, [])
        assert result == []

    @patch("backend.retrieval.compressor.settings")
    def test_all_below_threshold_returns_empty(self, mock_settings):
        mock_settings.compression_threshold = 0.99
        chunks = [
            _chunk("moderate doc", embedding=_VEC_MODERATE, chunk_id="c1"),
        ]
        result = compress(_VEC_QUERY, chunks)
        assert result == []

    @patch("backend.retrieval.compressor.settings")
    def test_custom_threshold_overrides_settings(self, mock_settings):
        mock_settings.compression_threshold = 0.99  # would drop everything
        chunks = [
            _chunk("similar doc", embedding=_VEC_SIMILAR, chunk_id="c1"),
        ]
        # Explicit threshold overrides the settings value
        result = compress(_VEC_QUERY, chunks, threshold=0.1)
        assert len(result) == 1

    @patch("backend.retrieval.compressor.settings")
    def test_chunk_without_embedding_kept_with_none_score(self, mock_settings):
        mock_settings.compression_threshold = 0.45
        chunks = [
            _chunk("no embedding doc", embedding=None, chunk_id="c1"),
        ]
        result = compress(_VEC_QUERY, chunks)
        assert len(result) == 1
        assert result[0]["relevance_score"] is None

    @patch("backend.retrieval.compressor.settings")
    def test_relevance_score_field_added(self, mock_settings):
        mock_settings.compression_threshold = 0.1
        chunks = [
            _chunk("doc", embedding=_VEC_SIMILAR, chunk_id="c1"),
        ]
        result = compress(_VEC_QUERY, chunks)
        assert "relevance_score" in result[0]
        assert isinstance(result[0]["relevance_score"], float)
