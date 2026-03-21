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

    with (
        patch("backend.api.routes_chat.settings.use_orchestrator", False),
        patch("backend.api.routes_chat.rag_chain.stream_rag_response", side_effect=_fake_stream),
    ):
        resp = client.post("/api/chat", json={
            "session_id": "test-sess-1",
            "message": "What is annual leave?",
        })

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "Hello" in resp.text


def test_chat_default_role_is_employee(client):
    captured = {}

    async def _capture(session_id, user_message, user_role, user_id=None):
        captured["user_role"] = user_role
        yield 'data: {"token": "", "done": true, "sources": []}\n\n'

    with (
        patch("backend.api.routes_chat.settings.use_orchestrator", False),
        patch("backend.api.routes_chat.rag_chain.stream_rag_response", side_effect=_capture),
    ):
        client.post("/api/chat", json={
            "session_id": "test-sess-2",
            "message": "hello",
        })

    assert captured.get("user_role") == "employee"


def test_chat_passes_hr_role(client):
    captured = {}

    async def _capture(session_id, user_message, user_role, user_id=None):
        captured["user_role"] = user_role
        yield 'data: {"token": "", "done": true, "sources": []}\n\n'

    with (
        patch("backend.api.routes_chat.settings.use_orchestrator", False),
        patch("backend.api.routes_chat.rag_chain.stream_rag_response", side_effect=_capture),
    ):
        client.post("/api/chat", json={
            "session_id": "test-sess-3",
            "message": "hello",
            "user_role": "hr",
        })

    assert captured.get("user_role") == "hr"


def test_chat_missing_message_returns_422(client):
    resp = client.post("/api/chat", json={"session_id": "test-sess-4"})
    assert resp.status_code == 422


# ── GET /api/sessions/{session_id}/history ────────────────────────────────────

def test_get_history_returns_messages(client):
    messages = [
        {"role": "user", "content": "Q1", "created_at": "2026-01-01T00:00:00"},
        {"role": "assistant", "content": "A1", "created_at": "2026-01-01T00:00:01"},
    ]
    with (
        patch("backend.api.routes_chat.session_manager.session_exists", new=AsyncMock(return_value=True)),
        patch("backend.api.routes_chat.session_manager.get_full_history", new=AsyncMock(return_value=messages)),
    ):
        resp = client.get("/api/sessions/known-sess/history")

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "known-sess"
    assert len(data["messages"]) == 2


def test_get_history_404_for_unknown_session(client):
    with patch("backend.api.routes_chat.session_manager.session_exists", new=AsyncMock(return_value=False)):
        resp = client.get("/api/sessions/ghost/history")
    assert resp.status_code == 404


# ── DELETE /api/sessions/{session_id} ────────────────────────────────────────

def test_delete_session_returns_success(client):
    with patch("backend.api.routes_chat.session_manager.delete_session", new=AsyncMock()):
        resp = client.delete("/api/sessions/del-sess")
    assert resp.status_code == 200
    assert resp.json() == {"success": True}
