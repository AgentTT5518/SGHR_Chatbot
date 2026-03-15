"""
Tests for backend.api.routes_admin

Mocks httpx, ingest pipeline, and vector_store so no network or DB calls
are made.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── POST /admin/ingest ────────────────────────────────────────────────────────

def test_ingest_starts_background_task(client):
    with patch("backend.api.routes_admin._run_ingest") as mock_run:
        resp = client.post("/admin/ingest", json={"force_rescrape": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert data["force_rescrape"] is False


def test_ingest_force_rescrape_flag_passed(client):
    with patch("backend.api.routes_admin._run_ingest") as mock_run:
        resp = client.post("/admin/ingest", json={"force_rescrape": True})
    assert resp.status_code == 200
    assert resp.json()["force_rescrape"] is True


def test_ingest_default_no_force_rescrape(client):
    with patch("backend.api.routes_admin._run_ingest"):
        resp = client.post("/admin/ingest", json={})
    assert resp.status_code == 200
    assert resp.json()["force_rescrape"] is False


# ── GET /admin/health/sources ─────────────────────────────────────────────────

def test_health_sources_all_ok(client):
    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.head = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("backend.api.routes_admin.httpx.AsyncClient", return_value=mock_client):
        resp = client.get("/admin/health/sources")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] == data["total"]
    assert data["failed"] == 0
    assert all(r["ok"] for r in data["results"])


def test_health_sources_handles_connection_error(client):
    mock_client = AsyncMock()
    mock_client.head = AsyncMock(side_effect=httpx.ConnectError("timeout"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("backend.api.routes_admin.httpx.AsyncClient", return_value=mock_client):
        resp = client.get("/admin/health/sources")

    assert resp.status_code == 200
    data = resp.json()
    assert data["failed"] == data["total"]
    assert all(not r["ok"] for r in data["results"])
    assert all("error" in r for r in data["results"])


# ── GET /admin/collections ────────────────────────────────────────────────────

def test_collections_returns_counts(client):
    mock_col = MagicMock()
    mock_col.count.return_value = 42

    # get_collection is imported lazily inside the endpoint body
    with patch("backend.retrieval.vector_store.get_collection", return_value=mock_col):
        resp = client.get("/admin/collections")

    assert resp.status_code == 200
    data = resp.json()
    assert data["employment_act"] == 42
    assert data["mom_guidelines"] == 42


def test_collections_returns_error_on_exception(client):
    with patch("backend.retrieval.vector_store.get_collection", side_effect=Exception("chroma down")):
        resp = client.get("/admin/collections")

    assert resp.status_code == 200
    assert "error" in resp.json()
    assert "chroma down" in resp.json()["error"]
