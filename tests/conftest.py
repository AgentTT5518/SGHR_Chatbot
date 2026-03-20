"""
Global test configuration.

Prevents real model downloads in CI by mocking the SentenceTransformer
import before any test module can trigger it.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def _make_mock_model():
    """Return a mock SentenceTransformer that produces deterministic embeddings."""
    mock = MagicMock()
    mock.encode.return_value = np.random.default_rng(42).random((1, 768)).astype(np.float32)
    return mock


@pytest.fixture(autouse=True, scope="session")
def _mock_sentence_transformer():
    """Prevent real SentenceTransformer model download during tests."""
    mock_model = _make_mock_model()
    with patch("backend.ingestion.embedder.SentenceTransformer", return_value=mock_model):
        # Also reset the singleton so it doesn't hold a real model
        with patch("backend.ingestion.embedder._model", None):
            yield
