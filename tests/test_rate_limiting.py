"""
Tests for rate limiting behaviour.
Verifies that the slowapi limiter is installed and that the 429 handler works.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.lib.limiter import limiter


@pytest.fixture(autouse=True)
def reset_limiter():
    """Clear the in-memory limiter storage between tests."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_chat_rate_limit_allows_single_request(client):
    """A single request within the limit must succeed (not 429)."""
    with patch("backend.chat.rag_chain.stream_rag_response", return_value=iter([])):
        resp = client.post(
            "/api/chat",
            json={"session_id": "sess1", "message": "hello", "user_role": "employee"},
        )
    assert resp.status_code != 429


def test_admin_ingest_rate_limit_allows_single_request(client):
    with patch("backend.api.routes_admin._run_ingest"):
        resp = client.post("/admin/ingest", json={})
    assert resp.status_code != 429


def test_rate_limit_handler_is_registered():
    """Verify the 429 exception handler is present in the app."""
    from slowapi.errors import RateLimitExceeded
    handlers = {k: v for k, v in app.exception_handlers.items()}
    assert RateLimitExceeded in handlers


def test_limiter_attached_to_app_state():
    """limiter must be stored in app.state for slowapi to function."""
    assert hasattr(app.state, "limiter")
    assert app.state.limiter is limiter
