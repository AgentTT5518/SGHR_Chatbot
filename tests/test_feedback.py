"""
Tests for feedback endpoints:
  POST /api/feedback
  GET  /admin/feedback
  GET  /admin/feedback/stats
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from tests.conftest import ADMIN_HEADERS


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── POST /api/feedback ────────────────────────────────────────────────────────

def test_submit_feedback_thumbs_up(client):
    with patch("backend.chat.session_manager.session_exists", new=AsyncMock(return_value=True)), \
         patch("backend.chat.session_manager.add_feedback", new=AsyncMock(return_value=1)):
        resp = client.post(
            "/api/feedback",
            json={"session_id": "abc123", "message_index": 2, "rating": "up"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["id"] == 1


def test_submit_feedback_thumbs_down_with_comment(client):
    with patch("backend.chat.session_manager.session_exists", new=AsyncMock(return_value=True)), \
         patch("backend.chat.session_manager.add_feedback", new=AsyncMock(return_value=5)):
        resp = client.post(
            "/api/feedback",
            json={
                "session_id": "abc123",
                "message_index": 4,
                "rating": "down",
                "comment": "Incorrect information",
            },
        )
    assert resp.status_code == 201
    assert resp.json()["id"] == 5


def test_submit_feedback_invalid_rating(client):
    resp = client.post(
        "/api/feedback",
        json={"session_id": "abc123", "message_index": 0, "rating": "maybe"},
    )
    assert resp.status_code == 422


def test_submit_feedback_missing_fields(client):
    resp = client.post("/api/feedback", json={"session_id": "abc123"})
    assert resp.status_code == 422


def test_submit_feedback_nonexistent_session(client):
    with patch("backend.chat.session_manager.session_exists", new=AsyncMock(return_value=False)):
        resp = client.post(
            "/api/feedback",
            json={"session_id": "ghost", "message_index": 0, "rating": "up"},
        )
    assert resp.status_code == 404


def test_submit_feedback_db_error_returns_500(client):
    with patch("backend.chat.session_manager.session_exists", new=AsyncMock(return_value=True)), \
         patch("backend.chat.session_manager.add_feedback", new=AsyncMock(side_effect=Exception("DB error"))):
        resp = client.post(
            "/api/feedback",
            json={"session_id": "abc123", "message_index": 0, "rating": "up"},
        )
    assert resp.status_code == 500


# ── GET /admin/feedback ───────────────────────────────────────────────────────

def test_list_feedback_returns_records(client):
    fake_records = [
        {
            "id": 1,
            "session_id": "sess1",
            "message_index": 2,
            "rating": "up",
            "comment": None,
            "created_at": "2026-03-16T10:00:00",
        }
    ]
    with patch(
        "backend.chat.session_manager.get_feedback",
        new=AsyncMock(return_value=fake_records),
    ):
        resp = client.get("/admin/feedback", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["records"] == fake_records
    assert data["limit"] == 50
    assert data["offset"] == 0


def test_list_feedback_pagination(client):
    with patch(
        "backend.chat.session_manager.get_feedback",
        new=AsyncMock(return_value=[]),
    ) as mock_get:
        resp = client.get("/admin/feedback?limit=10&offset=20", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["limit"] == 10
    assert data["offset"] == 20


def test_list_feedback_invalid_limit(client):
    resp = client.get("/admin/feedback?limit=0", headers=ADMIN_HEADERS)
    assert resp.status_code == 400


def test_list_feedback_limit_too_large(client):
    resp = client.get("/admin/feedback?limit=999", headers=ADMIN_HEADERS)
    assert resp.status_code == 400


def test_list_feedback_requires_admin_key(client):
    resp = client.get("/admin/feedback")
    assert resp.status_code == 401


# ── GET /admin/feedback/stats ─────────────────────────────────────────────────

def test_feedback_stats(client):
    fake_stats = {"total": 10, "up": 7, "down": 3}
    with patch(
        "backend.chat.session_manager.get_feedback_stats",
        new=AsyncMock(return_value=fake_stats),
    ):
        resp = client.get("/admin/feedback/stats", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    assert resp.json() == fake_stats


def test_feedback_stats_empty(client):
    with patch(
        "backend.chat.session_manager.get_feedback_stats",
        new=AsyncMock(return_value={"total": 0, "up": 0, "down": 0}),
    ):
        resp = client.get("/admin/feedback/stats", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0


def test_feedback_stats_requires_admin_key(client):
    resp = client.get("/admin/feedback/stats")
    assert resp.status_code == 401
