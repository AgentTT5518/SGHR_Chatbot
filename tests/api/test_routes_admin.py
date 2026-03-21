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


# ── GET /admin/verified-answers ──────────────────────────────────────────────


def test_list_verified_answers(client):
    mock_answers = [{"id": "id-1", "question": "Q1", "answer": "A1", "sources": []}]
    with patch("backend.memory.semantic_cache.list_verified_answers", return_value=mock_answers):
        resp = client.get("/admin/verified-answers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["answers"]) == 1
    assert data["answers"][0]["question"] == "Q1"


# ── POST /admin/verified-answers ─────────────────────────────────────────────


def test_create_verified_answer(client):
    with patch("backend.memory.semantic_cache.add_verified_answer", return_value="new-id"):
        resp = client.post("/admin/verified-answers", json={
            "question": "What is CPF?",
            "answer": "CPF is the Central Provident Fund.",
            "sources": [],
        })
    assert resp.status_code == 201
    assert resp.json()["id"] == "new-id"


# ── DELETE /admin/verified-answers/{id} ──────────────────────────────────────


def test_delete_verified_answer(client):
    with patch("backend.memory.semantic_cache.remove_verified_answer") as mock_rm:
        resp = client.delete("/admin/verified-answers/some-id")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    mock_rm.assert_called_once_with("some-id")


# ── GET /admin/feedback/candidates ───────────────────────────────────────────


def test_feedback_candidates(client):
    mock_feedback = [
        {"id": 1, "session_id": "sess-1", "message_index": 1, "rating": "up", "comment": None, "created_at": "2024-01-01"},
    ]
    mock_history = [
        {"role": "user", "content": "What is leave?", "created_at": "2024-01-01"},
        {"role": "assistant", "content": "Leave is 14 days.", "created_at": "2024-01-01"},
    ]
    with patch("backend.chat.session_manager.get_feedback", new_callable=AsyncMock, return_value=mock_feedback), \
         patch("backend.chat.session_manager.get_full_history", new_callable=AsyncMock, return_value=mock_history):
        resp = client.get("/admin/feedback/candidates")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["candidates"]) == 1
    assert data["candidates"][0]["question"] == "What is leave?"
    assert data["candidates"][0]["answer"] == "Leave is 14 days."


# ── GET /admin/faq-patterns ─────────────────────────────────────────────────


def test_faq_patterns_returns_structure(client):
    mock_patterns = [{"cluster_id": 0, "count": 5, "representative_query": "Q1", "sample_queries": ["Q1"]}]
    mock_gaps = [{"cluster_id": 0, "count": 2, "representative_query": "G1", "sample_queries": ["G1"], "gap_type": "thumbs_down"}]

    with patch("backend.memory.faq_analyzer.analyze_query_patterns", new_callable=AsyncMock, return_value=mock_patterns), \
         patch("backend.memory.faq_analyzer.identify_gaps", new_callable=AsyncMock, return_value=mock_gaps):
        resp = client.get("/admin/faq-patterns?days=14")

    assert resp.status_code == 200
    data = resp.json()
    assert "top_patterns" in data
    assert "knowledge_gaps" in data
    assert len(data["top_patterns"]) == 1
    assert data["top_patterns"][0]["count"] == 5
    assert data["knowledge_gaps"][0]["gap_type"] == "thumbs_down"


def test_faq_patterns_default_days(client):
    with patch("backend.memory.faq_analyzer.analyze_query_patterns", new_callable=AsyncMock, return_value=[]) as mock_analyze, \
         patch("backend.memory.faq_analyzer.identify_gaps", new_callable=AsyncMock, return_value=[]):
        resp = client.get("/admin/faq-patterns")

    assert resp.status_code == 200
    mock_analyze.assert_called_once_with(days=30)


def test_faq_patterns_handles_error(client):
    with patch("backend.memory.faq_analyzer.analyze_query_patterns", new_callable=AsyncMock, side_effect=Exception("boom")):
        resp = client.get("/admin/faq-patterns")

    assert resp.status_code == 500
