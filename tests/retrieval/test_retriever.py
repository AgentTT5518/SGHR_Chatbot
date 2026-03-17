"""
Tests for backend.retrieval.retriever

Mocks embed_query and vector_store.query so no model or DB is loaded.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.retrieval.retriever import (
    DEFINITION_KEYWORDS,
    THRESHOLD_FLOOR,
    THRESHOLD_MULTIPLIER,
    get_section_2,
    needs_definitions,
    retrieve,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _chunk(text: str, distance: float = 0.1, section: str = "38") -> dict:
    return {
        "text": text,
        "metadata": {"source": "Employment Act", "section_number": section},
        "distance": distance,
    }


FAKE_EMBEDDING = [0.1] * 768


# ── retrieve ──────────────────────────────────────────────────────────────────

class TestRetrieve:
    def test_returns_merged_and_sorted_results(self):
        ea = [_chunk("ea text", distance=0.2)]
        mom = [_chunk("mom text", distance=0.1)]

        with (
            patch("backend.retrieval.retriever.embed_query", return_value=FAKE_EMBEDDING),
            patch("backend.retrieval.retriever.vector_store.query", side_effect=[ea, mom]),
        ):
            results = retrieve("annual leave")

        assert results[0]["text"] == "mom text"   # lower distance first
        assert results[1]["text"] == "ea text"

    def test_empty_collections_returns_empty(self):
        with (
            patch("backend.retrieval.retriever.embed_query", return_value=FAKE_EMBEDDING),
            patch("backend.retrieval.retriever.vector_store.query", side_effect=[[], []]),
        ):
            results = retrieve("anything")
        assert results == []

    def test_threshold_filters_distant_results(self):
        # best=0.1, threshold=max(0.1*1.5, 0.25)=0.25; distance 0.5 should be excluded
        chunks = [
            _chunk("close", distance=0.1),
            _chunk("far", distance=0.5),
        ]
        with (
            patch("backend.retrieval.retriever.embed_query", return_value=FAKE_EMBEDDING),
            patch("backend.retrieval.retriever.vector_store.query", side_effect=[chunks, []]),
        ):
            results = retrieve("question")
        assert all(c["text"] != "far" for c in results)

    def test_threshold_floor_applied(self):
        # best=0.01, threshold=max(0.01*1.5, 0.25)=0.25 (floor wins)
        chunks = [
            _chunk("very close", distance=0.01),
            _chunk("medium", distance=0.24),
            _chunk("just outside floor", distance=0.26),
        ]
        with (
            patch("backend.retrieval.retriever.embed_query", return_value=FAKE_EMBEDDING),
            patch("backend.retrieval.retriever.vector_store.query", side_effect=[chunks, []]),
        ):
            results = retrieve("question")
        texts = [r["text"] for r in results]
        assert "very close" in texts
        assert "medium" in texts
        assert "just outside floor" not in texts

    def test_caps_at_8_results(self):
        chunks = [_chunk(f"chunk {i}", distance=0.1 + i * 0.001) for i in range(20)]
        with (
            patch("backend.retrieval.retriever.embed_query", return_value=FAKE_EMBEDDING),
            patch("backend.retrieval.retriever.vector_store.query", side_effect=[chunks, []]),
        ):
            results = retrieve("question")
        assert len(results) <= 8

    def test_queries_both_collections(self):
        with (
            patch("backend.retrieval.retriever.embed_query", return_value=FAKE_EMBEDDING),
            patch("backend.retrieval.retriever.vector_store.query", side_effect=[[], []]) as mock_q,
        ):
            retrieve("question")
        assert mock_q.call_count == 2
        collection_names = [c.args[0] for c in mock_q.call_args_list]
        assert "employment_act" in collection_names
        assert "mom_guidelines" in collection_names


# ── needs_definitions ─────────────────────────────────────────────────────────

class TestNeedsDefinitions:
    def test_keyword_in_query_returns_true(self):
        assert needs_definitions("what is a workman", []) is True

    def test_keyword_in_chunk_text_returns_true(self):
        chunk = _chunk("the employer must provide payslips")
        assert needs_definitions("payslip rules", [chunk]) is True

    def test_no_keyword_returns_false(self):
        chunk = _chunk("overtime pay is calculated as follows")
        assert needs_definitions("overtime calculation", [chunk]) is False

    def test_case_insensitive_query(self):
        assert needs_definitions("EMPLOYEE rights", []) is True

    def test_case_insensitive_chunk(self):
        chunk = _chunk("The EMPLOYER shall maintain records")
        assert needs_definitions("records", [chunk]) is True

    def test_empty_chunks_no_keyword_returns_false(self):
        assert needs_definitions("annual leave entitlement", []) is False

    def test_multiple_chunks_checked(self):
        chunks = [
            _chunk("general text about leave"),
            _chunk("the contract of service must specify hours"),
        ]
        assert needs_definitions("leave", chunks) is True


# ── get_section_2 ─────────────────────────────────────────────────────────────

class TestGetSection2:
    def test_returns_section_2_chunk(self):
        sec2 = _chunk("Definitions...", distance=0.05, section="2")
        other = _chunk("Other section", distance=0.1, section="10")
        with (
            patch("backend.retrieval.retriever.embed_query", return_value=FAKE_EMBEDDING),
            patch("backend.retrieval.retriever.vector_store.query", return_value=[sec2, other]),
        ):
            result = get_section_2()
        assert result is not None
        assert result["metadata"]["section_number"] == "2"

    def test_returns_none_when_no_section_2(self):
        chunks = [_chunk("section 10 text", section="10")]
        with (
            patch("backend.retrieval.retriever.embed_query", return_value=FAKE_EMBEDDING),
            patch("backend.retrieval.retriever.vector_store.query", return_value=chunks),
        ):
            result = get_section_2()
        assert result is None

    def test_returns_none_on_empty_results(self):
        with (
            patch("backend.retrieval.retriever.embed_query", return_value=FAKE_EMBEDDING),
            patch("backend.retrieval.retriever.vector_store.query", return_value=[]),
        ):
            result = get_section_2()
        assert result is None


# ── hybrid retrieve (RRF) ──────────────────────────────────────────────────────

class TestHybridRetrieve:
    def test_hybrid_falls_back_to_semantic_when_keyword_empty(self):
        ea = [_chunk("ea text", distance=0.2)]
        mom = [_chunk("mom text", distance=0.1)]

        with (
            patch("backend.retrieval.retriever.embed_query", return_value=FAKE_EMBEDDING),
            patch("backend.retrieval.retriever.vector_store.query", side_effect=[ea, mom]),
            patch("backend.retrieval.retriever.settings") as mock_settings,
            patch(
                "backend.retrieval.keyword_search.get_searcher",
                side_effect=Exception("no corpus"),
            ),
        ):
            mock_settings.retrieval_mode = "hybrid"
            from backend.retrieval.retriever import _hybrid_retrieve
            results = _hybrid_retrieve("annual leave", 10)

        assert len(results) > 0

    def test_rrf_merges_lists_by_rank(self):
        from backend.retrieval.retriever import _reciprocal_rank_fusion
        semantic = [
            {"text": "doc A text here", "metadata": {}, "distance": 0.1},
            {"text": "doc B text here", "metadata": {}, "distance": 0.2},
        ]
        keyword = [
            {"text": "doc B text here", "metadata": {}, "keyword_score": 0.9},
            {"text": "doc C text here", "metadata": {}, "keyword_score": 0.5},
        ]
        merged = _reciprocal_rank_fusion(semantic, keyword)
        texts = [d["text"] for d in merged]
        # doc B appears in both lists so should rank high
        assert "doc B text here" in texts
        assert "doc A text here" in texts
        assert "doc C text here" in texts

    def test_rrf_returns_unique_docs(self):
        from backend.retrieval.retriever import _reciprocal_rank_fusion
        doc = {"text": "same document text", "metadata": {}, "distance": 0.1}
        semantic = [doc]
        keyword = [{"text": "same document text", "metadata": {}, "keyword_score": 0.8}]
        merged = _reciprocal_rank_fusion(semantic, keyword)
        texts = [d["text"] for d in merged]
        assert texts.count("same document text") == 1

    def test_apply_threshold_empty_returns_empty(self):
        from backend.retrieval.retriever import _apply_threshold
        assert _apply_threshold([]) == []

    def test_retrieve_uses_semantic_when_mode_is_semantic(self):
        ea = [_chunk("ea text", distance=0.15)]

        with (
            patch("backend.retrieval.retriever.embed_query", return_value=FAKE_EMBEDDING),
            patch("backend.retrieval.retriever.vector_store.query", side_effect=[ea, []]),
            patch("backend.retrieval.retriever.settings") as mock_settings,
        ):
            mock_settings.retrieval_mode = "semantic"
            from backend.retrieval.retriever import retrieve
            results = retrieve("overtime")

        assert len(results) > 0
