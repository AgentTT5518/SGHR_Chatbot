"""
TF-IDF keyword search module.
Fits a TfidfVectorizer over all ChromaDB chunks at first use (lazy singleton).
Used by the hybrid retriever alongside semantic search.
"""
from __future__ import annotations

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from backend.lib.logger import get_logger

log = get_logger("retrieval.keyword_search")

_searcher: "KeywordSearcher | None" = None


class KeywordSearcher:
    def __init__(self) -> None:
        self._vectorizer = TfidfVectorizer(
            strip_accents="unicode",
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            max_features=50_000,
            sublinear_tf=True,
        )
        self._matrix = None
        self._docs: list[dict] = []

    def fit(self, docs: list[dict]) -> None:
        """Fit the vectorizer on a list of {text, metadata} dicts."""
        if not docs:
            log.warning("KeywordSearcher.fit called with empty corpus — skipping")
            return
        self._docs = docs
        texts = [d["text"] for d in docs]
        self._matrix = self._vectorizer.fit_transform(texts)
        log.info("KeywordSearcher fitted", extra={"n_docs": len(docs)})

    def search(self, query: str, n: int = 10) -> list[dict]:
        """
        Return top-n documents by TF-IDF cosine similarity.
        Each result is a copy of the source doc with an added 'keyword_score' field.
        """
        if self._matrix is None or not self._docs:
            return []
        q_vec = self._vectorizer.transform([query])
        scores = (self._matrix @ q_vec.T).toarray().flatten()
        top_indices = np.argsort(scores)[::-1][:n]
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                doc = dict(self._docs[idx])
                doc["keyword_score"] = float(scores[idx])
                results.append(doc)
        return results

    @property
    def is_fitted(self) -> bool:
        return self._matrix is not None


def _load_searcher() -> KeywordSearcher:
    from backend.retrieval.vector_store import get_all_documents
    searcher = KeywordSearcher()
    ea_docs = get_all_documents("employment_act")
    mom_docs = get_all_documents("mom_guidelines")
    all_docs = ea_docs + mom_docs
    if all_docs:
        searcher.fit(all_docs)
    else:
        log.warning("No documents found — keyword search will return empty results")
    return searcher


def get_searcher() -> KeywordSearcher:
    """Return the lazily-initialised singleton KeywordSearcher."""
    global _searcher
    if _searcher is None:
        _searcher = _load_searcher()
    return _searcher


def reset_searcher() -> None:
    """Invalidate the cached searcher. Call after re-ingestion."""
    global _searcher
    _searcher = None
    log.info("KeywordSearcher cache cleared")
