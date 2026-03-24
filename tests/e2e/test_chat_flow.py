"""
E2E: Chat flow — POST /api/chat with mocked Claude API, real ChromaDB + SQLite.

Verifies the full request → orchestrator → SSE stream → session creation cycle.
"""
from __future__ import annotations

import json

import pytest

from tests.e2e.conftest import (
    ADMIN_HEADERS,
    make_text_stream,
    make_tool_then_text_stream,
    parse_sse_events,
)


pytestmark = pytest.mark.asyncio


async def test_chat_returns_sse_stream(e2e_client, mock_anthropic, mock_orchestrator_deps):
    """POST /api/chat returns a 200 SSE stream with tokens and a done event."""
    mock_anthropic.messages.stream.return_value = make_text_stream(
        "Annual leave in Singapore is governed by the Employment Act."
    )

    resp = await e2e_client.post(
        "/api/chat",
        json={"message": "What is annual leave?"},
    )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = parse_sse_events(resp.text)
    assert len(events) >= 2  # at least one token + done

    done_events = [e for e in events if e.get("done")]
    assert len(done_events) == 1
    assert "signed_session_id" in done_events[0]


async def test_chat_creates_session_in_db(e2e_client, mock_anthropic, mock_orchestrator_deps):
    """A chat request creates a session and persists messages in SQLite."""
    mock_anthropic.messages.stream.return_value = make_text_stream("Hello!")

    resp = await e2e_client.post(
        "/api/chat",
        json={"message": "Hi there"},
    )
    assert resp.status_code == 200

    events = parse_sse_events(resp.text)
    done = next(e for e in events if e.get("done"))
    signed_token = done["signed_session_id"]

    # Use the signed token to fetch history
    raw_id = signed_token.rsplit(".", 1)[0]
    hist_resp = await e2e_client.get(
        f"/api/sessions/{raw_id}/history",
        headers={"X-Session-Token": signed_token},
    )
    assert hist_resp.status_code == 200
    data = hist_resp.json()
    assert data["session_id"] == raw_id
    assert len(data["messages"]) >= 2  # user + assistant


async def test_chat_with_tool_use(e2e_client, mock_anthropic, mock_orchestrator_deps):
    """Chat triggers a tool call (search), then streams the final answer."""
    streams = make_tool_then_text_stream(
        tool_name="search_employment_act",
        tool_input={"query": "annual leave entitlement"},
        final_text="You are entitled to 7 days of annual leave.",
    )
    mock_anthropic.messages.stream.side_effect = streams

    resp = await e2e_client.post(
        "/api/chat",
        json={"message": "How many days of annual leave am I entitled to?"},
    )
    assert resp.status_code == 200

    events = parse_sse_events(resp.text)
    # Should have a thinking/status event for tool use
    status_events = [e for e in events if e.get("status") == "thinking"]
    assert len(status_events) >= 1

    done = next(e for e in events if e.get("done"))
    assert "sources" in done


async def test_chat_with_session_continuity(e2e_client, mock_anthropic, mock_orchestrator_deps):
    """Second message with same session_id continues the conversation."""
    # First message
    mock_anthropic.messages.stream.return_value = make_text_stream("First answer.")
    resp1 = await e2e_client.post(
        "/api/chat",
        json={"message": "First question"},
    )
    events1 = parse_sse_events(resp1.text)
    signed_token = next(e for e in events1 if e.get("done"))["signed_session_id"]

    # Second message using same session
    mock_anthropic.messages.stream.return_value = make_text_stream("Follow-up answer.")
    resp2 = await e2e_client.post(
        "/api/chat",
        json={"session_id": signed_token, "message": "Follow-up question"},
    )
    assert resp2.status_code == 200

    events2 = parse_sse_events(resp2.text)
    done2 = next(e for e in events2 if e.get("done"))
    # Same session token should be returned
    assert done2["signed_session_id"] == signed_token


async def test_chat_returns_sources_in_done_event(e2e_client, mock_anthropic, mock_orchestrator_deps):
    """The done event includes a sources array."""
    mock_anthropic.messages.stream.return_value = make_text_stream("Answer with sources.")

    resp = await e2e_client.post(
        "/api/chat",
        json={"message": "What is the notice period?"},
    )

    events = parse_sse_events(resp.text)
    done = next(e for e in events if e.get("done"))
    assert "sources" in done
    assert isinstance(done["sources"], list)


async def test_chat_invalid_session_token(e2e_client, mock_anthropic, mock_orchestrator_deps):
    """A tampered session token returns 403."""
    resp = await e2e_client.post(
        "/api/chat",
        json={"session_id": "tampered-session.invalidsig", "message": "hi"},
    )
    assert resp.status_code == 403
