"""
Tests for backend.api.routes_chat

Uses FastAPI TestClient with mocked rag_chain and session_manager so no DB
or Anthropic API calls are made.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from tests.conftest import make_signed_session


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── POST /api/chat ─────────────────────────────────────────────────────────────

def _sse_lines(*payloads: str) -> str:
    """Build a minimal SSE response body from JSON payload strings."""
    return "".join(f"data: {p}\n\n" for p in payloads)


def test_chat_streams_response(client):
    sse_body = _sse_lines(
        '{"token": "Hello", "done": false}',
        '{"token": " there", "done": false}',
        '{"token": "", "done": true, "sources": []}',
    )

    async def _fake_stream(session_id, user_message, user_role, user_id=None):
        for line in sse_body.split("\n\n"):
            if line.strip():
                yield line + "\n\n"

    raw_id, signed = make_signed_session()
    with (
        patch("backend.api.routes_chat.settings.use_orchestrator", False),
        patch("backend.api.routes_chat.rag_chain.stream_rag_response", side_effect=_fake_stream),
    ):
        resp = client.post("/api/chat", json={
            "session_id": signed,
            "message": "What is annual leave?",
        })

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "Hello" in resp.text


def test_chat_new_session_when_null(client):
    """When session_id is null, server creates a new signed session."""
    async def _fake_stream(session_id, user_message, user_role, user_id=None):
        yield 'data: {"token": "", "done": true, "sources": []}\n\n'

    with (
        patch("backend.api.routes_chat.settings.use_orchestrator", False),
        patch("backend.api.routes_chat.rag_chain.stream_rag_response", side_effect=_fake_stream),
    ):
        resp = client.post("/api/chat", json={
            "session_id": None,
            "message": "hello",
        })

    assert resp.status_code == 200
    # The done event should contain a signed_session_id
    assert "signed_session_id" in resp.text


def test_chat_default_role_is_employee(client):
    captured = {}

    async def _capture(session_id, user_message, user_role, user_id=None):
        captured["user_role"] = user_role
        yield 'data: {"token": "", "done": true, "sources": []}\n\n'

    raw_id, signed = make_signed_session()
    with (
        patch("backend.api.routes_chat.settings.use_orchestrator", False),
        patch("backend.api.routes_chat.rag_chain.stream_rag_response", side_effect=_capture),
    ):
        client.post("/api/chat", json={
            "session_id": signed,
            "message": "hello",
        })

    assert captured.get("user_role") == "employee"


def test_chat_passes_hr_role(client):
    captured = {}

    async def _capture(session_id, user_message, user_role, user_id=None):
        captured["user_role"] = user_role
        yield 'data: {"token": "", "done": true, "sources": []}\n\n'

    raw_id, signed = make_signed_session()
    with (
        patch("backend.api.routes_chat.settings.use_orchestrator", False),
        patch("backend.api.routes_chat.rag_chain.stream_rag_response", side_effect=_capture),
    ):
        client.post("/api/chat", json={
            "session_id": signed,
            "message": "hello",
            "user_role": "hr",
        })

    assert captured.get("user_role") == "hr"


def test_chat_missing_message_returns_422(client):
    raw_id, signed = make_signed_session()
    resp = client.post("/api/chat", json={"session_id": signed})
    assert resp.status_code == 422


def test_chat_rejects_tampered_session(client):
    resp = client.post("/api/chat", json={
        "session_id": "fake-id.baaaaadsig",
        "message": "hello",
    })
    assert resp.status_code == 403


# ── GET /api/sessions/{session_id}/history ────────────────────────────────────

def test_get_history_returns_messages(client):
    raw_id, signed = make_signed_session()
    messages = [
        {"role": "user", "content": "Q1", "created_at": "2026-01-01T00:00:00"},
        {"role": "assistant", "content": "A1", "created_at": "2026-01-01T00:00:01"},
    ]
    with (
        patch("backend.api.routes_chat.session_manager.session_exists", new=AsyncMock(return_value=True)),
        patch("backend.api.routes_chat.session_manager.get_full_history", new=AsyncMock(return_value=messages)),
    ):
        resp = client.get(
            f"/api/sessions/{raw_id}/history",
            headers={"X-Session-Token": signed},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == raw_id
    assert len(data["messages"]) == 2


def test_get_history_404_for_unknown_session(client):
    raw_id, signed = make_signed_session()
    with patch("backend.api.routes_chat.session_manager.session_exists", new=AsyncMock(return_value=False)):
        resp = client.get(
            f"/api/sessions/{raw_id}/history",
            headers={"X-Session-Token": signed},
        )
    assert resp.status_code == 404


def test_get_history_403_for_tampered_token(client):
    resp = client.get(
        "/api/sessions/some-id/history",
        headers={"X-Session-Token": "some-id.badsig"},
    )
    assert resp.status_code == 403


# ── DELETE /api/sessions/{session_id} ────────────────────────────────────────

def test_delete_session_returns_success(client):
    raw_id, signed = make_signed_session()
    with patch("backend.api.routes_chat.session_manager.delete_session", new=AsyncMock()):
        resp = client.delete(
            f"/api/sessions/{raw_id}",
            headers={"X-Session-Token": signed},
        )
    assert resp.status_code == 200
    assert resp.json() == {"success": True}


def test_delete_session_403_without_valid_token(client):
    resp = client.delete(
        "/api/sessions/some-id",
        headers={"X-Session-Token": "some-id.badsig"},
    )
    assert resp.status_code == 403
