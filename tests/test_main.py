"""
Tests for backend.main (FastAPI app, lifespan, /health endpoint)

Mocks all startup dependencies so the full app lifecycle can be exercised
without a real ChromaDB, embedding model, or SQLite DB.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_ok_when_model_and_chroma_ready(self):
        mock_model = MagicMock()

        with (
            patch("backend.main.vector_store.is_ready", return_value=True),
            patch("backend.ingestion.embedder._model", mock_model, create=True),
        ):
            with TestClient(app) as client:
                resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["chroma"] == "ready"

    def test_health_degraded_when_chroma_not_ready(self):
        mock_model = MagicMock()

        with (
            patch("backend.main.vector_store.is_ready", return_value=False),
            patch("backend.ingestion.embedder._model", mock_model, create=True),
        ):
            with TestClient(app) as client:
                resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["chroma"] == "not_ready"

    def test_health_returns_model_status(self):
        with patch("backend.main.vector_store.is_ready", return_value=True):
            with TestClient(app) as client:
                resp = client.get("/health")

        assert resp.status_code == 200
        assert resp.json()["model"] in ("loaded", "loading")

    def test_health_handles_import_error_gracefully(self):
        with (
            patch("backend.main.vector_store.is_ready", return_value=False),
            patch("backend.ingestion.embedder._model", None),
        ):
            with TestClient(app) as client:
                resp = client.get("/health")

        assert resp.status_code == 200
        assert resp.json()["status"] == "degraded"
