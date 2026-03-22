"""
Global test configuration.

Patches SentenceTransformer constructor and ChromaDB readiness check so that
tests using TestClient(app) never trigger a real model download or require
a running ChromaDB instance.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.lib.session_signer import create_signed_session

# ── Auth test helpers ─────────────────────────────────────────────────────────

ADMIN_HEADERS: dict[str, str] = {"X-Admin-Key": "dev-only-key"}


def make_signed_session() -> tuple[str, str]:
    """Return ``(raw_session_id, signed_token)``."""
    signed = create_signed_session()
    raw = signed.rsplit(".", 1)[0]
    return raw, signed


def _fake_encode(texts, **kwargs):
    """Return deterministic embeddings matching BGE dimensions."""
    rng = np.random.default_rng(42)
    if isinstance(texts, str):
        texts = [texts]
    return rng.random((len(texts), 768)).astype(np.float32)


_mock_model = MagicMock()
_mock_model.encode.side_effect = _fake_encode


@pytest.fixture(autouse=True, scope="session")
def _prevent_model_download():
    """
    Prevent SentenceTransformer model download across all tests.

    Individual tests that patch SentenceTransformer themselves will
    override this session-scoped patch (inner patch wins).
    """
    with patch(
        "backend.ingestion.embedder.SentenceTransformer",
        return_value=_mock_model,
    ):
        yield
