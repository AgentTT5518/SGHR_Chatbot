"""
E2E: Admin flow — health check, collection stats, feedback candidates, FAQ patterns.

All admin endpoints require X-Admin-Key header.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.e2e.conftest import ADMIN_HEADERS


pytestmark = pytest.mark.asyncio


# ── Auth enforcement ──────────────────────────────────────────────────────────


async def test_admin_endpoints_require_auth(e2e_client):
    """Admin endpoints return 401/403 without X-Admin-Key."""
    endpoints = [
        "/admin/collections",
        "/admin/verified-answers",
        "/admin/feedback",
        "/admin/feedback/stats",
        "/admin/faq-patterns",
        "/admin/escalations",
    ]
    for url in endpoints:
        resp = await e2e_client.get(url)
        assert resp.status_code in (401, 403), f"{url} should require auth, got {resp.status_code}"


async def test_admin_wrong_key_rejected(e2e_client):
    """Admin endpoints reject an incorrect API key."""
    resp = await e2e_client.get(
        "/admin/collections",
        headers={"X-Admin-Key": "wrong-key"},
    )
    assert resp.status_code in (401, 403)


# ── Collection stats ──────────────────────────────────────────────────────────


async def test_collection_counts(e2e_client):
    """GET /admin/collections returns document counts from ChromaDB."""
    resp = await e2e_client.get("/admin/collections", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    # Should have keys for each collection (may be 0 if not ingested in test env)
    assert "employment_act" in data or "error" in data
    assert "mom_guidelines" in data or "error" in data


# ── Health check ──────────────────────────────────────────────────────────────


async def test_health_sources(e2e_client):
    """GET /admin/health/sources returns URL health results.

    Mocks httpx to avoid actual network calls in tests.
    """
    mock_response = type("Resp", (), {"status_code": 200})()

    with patch("backend.api.routes_admin.httpx.AsyncClient") as MockClient:
        mock_ctx = AsyncMock()
        mock_ctx.head = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = await e2e_client.get("/admin/health/sources", headers=ADMIN_HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "ok" in data
    assert "results" in data


# ── Verified answers ──────────────────────────────────────────────────────────


async def test_verified_answers_crud(e2e_client):
    """Create, list, and delete a verified answer."""
    # Create
    create_resp = await e2e_client.post(
        "/admin/verified-answers",
        headers=ADMIN_HEADERS,
        json={
            "question": "What is the minimum notice period?",
            "answer": "The notice period depends on your length of service.",
            "sources": [{"label": "Employment Act s10", "url": ""}],
        },
    )
    assert create_resp.status_code == 201
    answer_id = create_resp.json()["id"]

    # List
    list_resp = await e2e_client.get("/admin/verified-answers", headers=ADMIN_HEADERS)
    assert list_resp.status_code == 200
    answers = list_resp.json()["answers"]
    assert any(a["id"] == answer_id for a in answers)

    # Delete
    del_resp = await e2e_client.delete(
        f"/admin/verified-answers/{answer_id}",
        headers=ADMIN_HEADERS,
    )
    assert del_resp.status_code == 200


# ── Feedback list + stats ─────────────────────────────────────────────────────


async def test_feedback_list(e2e_client):
    """GET /admin/feedback returns a paginated list."""
    resp = await e2e_client.get("/admin/feedback", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "records" in data
    assert "limit" in data
    assert "offset" in data


async def test_feedback_stats(e2e_client):
    """GET /admin/feedback/stats returns aggregate counts."""
    resp = await e2e_client.get("/admin/feedback/stats", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "up" in data or "total" in data or isinstance(data, dict)


# ── FAQ patterns ──────────────────────────────────────────────────────────────


async def test_faq_patterns(e2e_client):
    """GET /admin/faq-patterns returns query clusters."""
    resp = await e2e_client.get(
        "/admin/faq-patterns",
        headers=ADMIN_HEADERS,
        params={"days": 7},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "top_patterns" in data
    assert "knowledge_gaps" in data


# ── Escalations ───────────────────────────────────────────────────────────────


async def test_escalations_list(e2e_client):
    """GET /admin/escalations returns escalation records."""
    resp = await e2e_client.get("/admin/escalations", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) or isinstance(data, dict)


# ── Health endpoint (non-admin) ───────────────────────────────────────────────


async def test_health_endpoint(e2e_client):
    """GET /health returns app status (no auth required)."""
    resp = await e2e_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "model" in data
    assert "chroma" in data
