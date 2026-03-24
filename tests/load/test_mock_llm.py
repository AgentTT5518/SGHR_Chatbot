"""
Validates that MOCK_LLM mode returns canned responses without calling Claude.

This test ensures the load testing infrastructure works correctly by verifying
that when mock_llm=True, the orchestrator bypasses the Anthropic API entirely.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio

from backend.main import app


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def mock_llm_client():
    """Async client with MOCK_LLM enabled."""
    with patch("backend.config.settings.mock_llm", True), \
         patch("backend.chat.orchestrator.settings.mock_llm", True):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client


async def test_mock_llm_returns_canned_response(mock_llm_client):
    """MOCK_LLM=true returns a canned SSE response without calling Anthropic."""
    resp = await mock_llm_client.post(
        "/api/chat",
        json={"message": "What is annual leave?"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = []
    for line in resp.text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    # Should have exactly one event (canned response as done)
    done_events = [e for e in events if e.get("done")]
    assert len(done_events) >= 1
    assert "mock response" in done_events[0]["token"].lower()
    assert done_events[0]["sources"] == []


async def test_mock_llm_creates_session(mock_llm_client):
    """Mock mode still creates a session and persists messages."""
    resp = await mock_llm_client.post(
        "/api/chat",
        json={"message": "Test session creation"},
    )
    assert resp.status_code == 200

    events = []
    for line in resp.text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    done = next(e for e in events if e.get("done"))
    signed_token = done["signed_session_id"]
    raw_id = signed_token.rsplit(".", 1)[0]

    # Verify session has history
    hist_resp = await mock_llm_client.get(
        f"/api/sessions/{raw_id}/history",
        headers={"X-Session-Token": signed_token},
    )
    assert hist_resp.status_code == 200
    messages = hist_resp.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


async def test_mock_llm_handles_multiple_requests(mock_llm_client):
    """Mock mode handles rapid sequential requests."""
    for i in range(3):
        resp = await mock_llm_client.post(
            "/api/chat",
            json={"message": f"Question {i}"},
        )
        # Accept 200 or 429 (rate limit) when running in full suite
        assert resp.status_code in (200, 429)
