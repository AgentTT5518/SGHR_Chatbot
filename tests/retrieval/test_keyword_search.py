"""
Tests for backend.retrieval.keyword_search
Uses in-memory documents — no ChromaDB needed.
"""
from __future__ import annotations

import pytest

from backend.retrieval.keyword_search import KeywordSearcher, reset_searcher


def _make_docs(texts: list[str]) -> list[dict]:
    return [{"id": str(i), "text": t, "metadata": {}} for i, t in enumerate(texts)]


class TestKeywordSearcher:
    def setup_method(self):
        reset_searcher()

    def test_not_fitted_returns_empty(self):
        searcher = KeywordSearcher()
        results = searcher.search("annual leave")
        assert results == []

    def test_is_fitted_false_before_fit(self):
        searcher = KeywordSearcher()
        assert not searcher.is_fitted

    def test_is_fitted_true_after_fit(self):
        searcher = KeywordSearcher()
        searcher.fit(_make_docs(["Some employment text"]))
        assert searcher.is_fitted

    def test_search_returns_relevant_doc(self):
        docs = _make_docs([
            "Annual leave entitlement under Singapore Employment Act",
            "Overtime pay calculation for workmen",
            "Maternity leave provisions",
        ])
        searcher = KeywordSearcher()
        searcher.fit(docs)
        results = searcher.search("annual leave")
        assert len(results) > 0
        assert results[0]["text"] == docs[0]["text"]

    def test_search_returns_keyword_score(self):
        docs = _make_docs(["Annual leave entitlement for employees"])
        searcher = KeywordSearcher()
        searcher.fit(docs)
        results = searcher.search("annual leave")
        assert "keyword_score" in results[0]
        assert results[0]["keyword_score"] > 0

    def test_search_zero_score_docs_excluded(self):
        docs = _make_docs(["Completely unrelated document about something else"])
        searcher = KeywordSearcher()
        searcher.fit(docs)
        # "xyz123" should match nothing
        results = searcher.search("xyz123 nonexistent term")
        assert results == []

    def test_search_respects_n_limit(self):
        docs = _make_docs([f"Leave document {i} about annual sick leave" for i in range(20)])
        searcher = KeywordSearcher()
        searcher.fit(docs)
        results = searcher.search("leave", n=5)
        assert len(results) <= 5

    def test_fit_empty_corpus_returns_empty_search(self):
        searcher = KeywordSearcher()
        searcher.fit([])
        results = searcher.search("anything")
        assert results == []

    def test_original_doc_not_mutated(self):
        docs = _make_docs(["Annual leave"])
        original_keys = set(docs[0].keys())
        searcher = KeywordSearcher()
        searcher.fit(docs)
        searcher.search("leave")
        # Original docs must be unchanged
        assert set(docs[0].keys()) == original_keys


class TestResetSearcher:
    def test_reset_clears_cache(self):
        from unittest.mock import MagicMock, patch
        from backend.retrieval import keyword_search

        # Pre-populate cache with a dummy
        keyword_search._searcher = MagicMock()
        reset_searcher()
        assert keyword_search._searcher is None
