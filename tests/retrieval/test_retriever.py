"""
Tests for backend.retrieval.retriever

Mocks embed_query and vector_store.query so no model or DB is loaded.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.retrieval.retriever import (
    DEFINITION_KEYWORDS,
    _reciprocal_rank_fusion,
    get_section_2,
    needs_definitions,
    retrieve,
    retrieve_multi,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _chunk(
    text: str, distance: float = 0.1, section: str = "38", chunk_id: str | None = None,
) -> dict:
    return {
        "id": chunk_id or f"chunk_{text[:20]}",
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
            patch("backend.retrieval.retriever.settings") as mock_settings,
        ):
            mock_settings.retrieval_mode = "semantic"
            mock_settings.threshold_floor = 0.25
            mock_settings.threshold_multiplier = 1.5
            mock_settings.max_retrieval_results = 8
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
            patch("backend.retrieval.retriever.settings") as mock_settings,
        ):
            mock_settings.retrieval_mode = "semantic"
            mock_settings.threshold_floor = 0.25
            mock_settings.threshold_multiplier = 1.5
            mock_settings.max_retrieval_results = 8
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
            patch("backend.retrieval.retriever.settings") as mock_settings,
        ):
            mock_settings.retrieval_mode = "semantic"
            mock_settings.threshold_floor = 0.25
            mock_settings.threshold_multiplier = 1.5
            mock_settings.max_retrieval_results = 8
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
            patch("backend.retrieval.retriever.settings") as mock_settings,
        ):
            mock_settings.retrieval_mode = "semantic"
            mock_settings.threshold_floor = 0.25
            mock_settings.threshold_multiplier = 1.5
            mock_settings.max_retrieval_results = 8
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
            mock_settings.threshold_floor = 0.25
            mock_settings.threshold_multiplier = 1.5
            mock_settings.max_retrieval_results = 8
            from backend.retrieval.retriever import _hybrid_retrieve
            results = _hybrid_retrieve("annual leave", 10)

        assert len(results) > 0

    def test_rrf_merges_lists_by_rank(self):
        semantic = [
            {"id": "a", "text": "doc A text here", "metadata": {}, "distance": 0.1},
            {"id": "b", "text": "doc B text here", "metadata": {}, "distance": 0.2},
        ]
        keyword = [
            {"id": "b", "text": "doc B text here", "metadata": {}, "keyword_score": 0.9},
            {"id": "c", "text": "doc C text here", "metadata": {}, "keyword_score": 0.5},
        ]
        merged = _reciprocal_rank_fusion(semantic, keyword)
        texts = [d["text"] for d in merged]
        # doc B appears in both lists so should rank high
        assert "doc B text here" in texts
        assert "doc A text here" in texts
        assert "doc C text here" in texts

    def test_rrf_returns_unique_docs(self):
        doc = {"id": "same", "text": "same document text", "metadata": {}, "distance": 0.1}
        semantic = [doc]
        keyword = [{"id": "same", "text": "same document text", "metadata": {}, "keyword_score": 0.8}]
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
            mock_settings.threshold_floor = 0.25
            mock_settings.threshold_multiplier = 1.5
            mock_settings.max_retrieval_results = 8
            from backend.retrieval.retriever import retrieve
            results = retrieve("overtime")

        assert len(results) > 0


# ── Generalized RRF (Phase 4A) ───────────────────────────────────────────────

class TestGeneralizedRRF:
    def test_rrf_with_three_lists(self):
        list_a = [
            {"id": "a1", "text": "doc A", "metadata": {}, "distance": 0.1},
            {"id": "shared", "text": "shared doc", "metadata": {}, "distance": 0.2},
        ]
        list_b = [
            {"id": "shared", "text": "shared doc", "metadata": {}, "distance": 0.15},
            {"id": "b1", "text": "doc B", "metadata": {}, "distance": 0.3},
        ]
        list_c = [
            {"id": "shared", "text": "shared doc", "metadata": {}, "distance": 0.12},
            {"id": "c1", "text": "doc C", "metadata": {}, "distance": 0.25},
        ]
        merged = _reciprocal_rank_fusion(list_a, list_b, list_c)
        # shared doc appears in all 3 lists → highest RRF score
        assert merged[0]["id"] == "shared"
        assert len(merged) == 4  # a1, shared, b1, c1

    def test_rrf_deduplicates_by_id(self):
        list_a = [{"id": "same_id", "text": "text version 1", "metadata": {}, "distance": 0.1}]
        list_b = [{"id": "same_id", "text": "text version 2", "metadata": {}, "distance": 0.2}]
        merged = _reciprocal_rank_fusion(list_a, list_b)
        assert len(merged) == 1

    def test_rrf_falls_back_to_text_key_when_no_id(self):
        list_a = [{"text": "shared text here", "metadata": {}, "distance": 0.1}]
        list_b = [{"text": "shared text here", "metadata": {}, "distance": 0.2}]
        merged = _reciprocal_rank_fusion(list_a, list_b)
        assert len(merged) == 1

    def test_rrf_single_list_returns_as_is(self):
        docs = [
            {"id": "a", "text": "doc A", "metadata": {}, "distance": 0.1},
            {"id": "b", "text": "doc B", "metadata": {}, "distance": 0.2},
        ]
        merged = _reciprocal_rank_fusion(docs)
        assert len(merged) == 2


# ── retrieve_multi (Phase 4A) ────────────────────────────────────────────────

class TestRetrieveMulti:
    def test_multi_calls_retrieve_for_each_query(self):
        results = [_chunk("chunk 1", chunk_id="c1"), _chunk("chunk 2", chunk_id="c2")]
        with (
            patch("backend.retrieval.retriever.embed_query", return_value=FAKE_EMBEDDING),
            patch("backend.retrieval.retriever.vector_store.query", return_value=results),
            patch("backend.retrieval.retriever.settings") as mock_settings,
        ):
            mock_settings.retrieval_mode = "semantic"
            mock_settings.threshold_floor = 0.25
            mock_settings.threshold_multiplier = 1.5
            mock_settings.max_retrieval_results = 8
            mock_settings.rrf_k = 60
            result = retrieve_multi(["q1", "q2", "q3"])
        assert len(result) <= 8

    def test_multi_with_collection_uses_retrieve_from_collection(self):
        results = [_chunk("chunk 1", chunk_id="c1")]
        with (
            patch("backend.retrieval.retriever.embed_query", return_value=FAKE_EMBEDDING),
            patch("backend.retrieval.retriever.vector_store.query", return_value=results),
        ):
            result = retrieve_multi(
                ["q1", "q2"], collection="employment_act",
            )
        assert len(result) >= 1

    def test_multi_empty_queries_returns_empty(self):
        result = retrieve_multi([])
        assert result == []

    def test_multi_caps_at_8(self):
        # Generate enough unique chunks to exceed 8 after merge
        chunks = [_chunk(f"chunk {i}", distance=0.1 + i * 0.001, chunk_id=f"c{i}") for i in range(10)]
        with (
            patch("backend.retrieval.retriever.embed_query", return_value=FAKE_EMBEDDING),
            patch("backend.retrieval.retriever.vector_store.query", return_value=chunks),
            patch("backend.retrieval.retriever.settings") as mock_settings,
        ):
            mock_settings.retrieval_mode = "semantic"
            mock_settings.threshold_floor = 0.25
            mock_settings.threshold_multiplier = 1.5
            mock_settings.max_retrieval_results = 8
            mock_settings.rrf_k = 60
            result = retrieve_multi(["q1", "q2"])
        assert len(result) <= 8


# ── include_embeddings plumbing ───────────────────────────────────────────────

class TestIncludeEmbeddings:
    def test_retrieve_from_collection_skips_threshold_when_include_embeddings(self):
        # With include_embeddings=True, _apply_threshold should be skipped
        chunks = [
            _chunk("close", distance=0.1, chunk_id="c1"),
            _chunk("far", distance=0.9, chunk_id="c2"),  # would be filtered by threshold
        ]
        with (
            patch("backend.retrieval.retriever.embed_query", return_value=FAKE_EMBEDDING),
            patch("backend.retrieval.retriever.vector_store.query", return_value=chunks),
        ):
            from backend.retrieval.retriever import retrieve_from_collection
            result = retrieve_from_collection(
                "test", collection="employment_act", include_embeddings=True,
            )
        # Both should be returned since threshold is skipped
        assert len(result) == 2

    def test_retrieve_from_collection_applies_threshold_when_no_include_embeddings(self):
        chunks = [
            _chunk("close", distance=0.1, chunk_id="c1"),
            _chunk("far", distance=0.9, chunk_id="c2"),  # should be filtered
        ]
        with (
            patch("backend.retrieval.retriever.embed_query", return_value=FAKE_EMBEDDING),
            patch("backend.retrieval.retriever.vector_store.query", return_value=chunks),
        ):
            from backend.retrieval.retriever import retrieve_from_collection
            result = retrieve_from_collection(
                "test", collection="employment_act", include_embeddings=False,
            )
        # Far chunk should be filtered out
        assert len(result) == 1
