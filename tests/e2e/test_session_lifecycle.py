"""
E2E: Session lifecycle — create via chat, retrieve history, delete, confirm cleanup.
"""
from __future__ import annotations

import pytest

from tests.e2e.conftest import make_text_stream, parse_sse_events


pytestmark = pytest.mark.asyncio


async def _create_session(e2e_client, mock_anthropic, mock_orchestrator_deps) -> tuple[str, str]:
    """Helper: send a chat message and return (raw_id, signed_token)."""
    mock_anthropic.messages.stream.return_value = make_text_stream("Test response.")
    resp = await e2e_client.post(
        "/api/chat",
        json={"message": "Test message for session lifecycle"},
    )
    assert resp.status_code == 200
    events = parse_sse_events(resp.text)
    done = next(e for e in events if e.get("done"))
    signed_token = done["signed_session_id"]
    raw_id = signed_token.rsplit(".", 1)[0]
    return raw_id, signed_token


async def test_create_and_retrieve_history(e2e_client, mock_anthropic, mock_orchestrator_deps):
    """Create a session via chat, then fetch its history."""
    raw_id, signed_token = await _create_session(e2e_client, mock_anthropic, mock_orchestrator_deps)

    resp = await e2e_client.get(
        f"/api/sessions/{raw_id}/history",
        headers={"X-Session-Token": signed_token},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == raw_id
    assert len(data["messages"]) >= 2
    roles = [m["role"] for m in data["messages"]]
    assert "user" in roles
    assert "assistant" in roles


async def test_delete_session(e2e_client, mock_anthropic, mock_orchestrator_deps):
    """Delete a session and confirm it's gone."""
    raw_id, signed_token = await _create_session(e2e_client, mock_anthropic, mock_orchestrator_deps)

    # Delete
    del_resp = await e2e_client.delete(
        f"/api/sessions/{raw_id}",
        headers={"X-Session-Token": signed_token},
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # History should now 404
    hist_resp = await e2e_client.get(
        f"/api/sessions/{raw_id}/history",
        headers={"X-Session-Token": signed_token},
    )
    assert hist_resp.status_code == 404


async def test_history_requires_valid_token(e2e_client, mock_anthropic, mock_orchestrator_deps):
    """Fetching history with an invalid token returns 403."""
    raw_id, _ = await _create_session(e2e_client, mock_anthropic, mock_orchestrator_deps)

    resp = await e2e_client.get(
        f"/api/sessions/{raw_id}/history",
        headers={"X-Session-Token": "fake-token.badsig"},
    )
    assert resp.status_code == 403


async def test_nonexistent_session_returns_404(e2e_client, mock_anthropic, mock_orchestrator_deps):
    """Fetching history for a non-existent session returns 404."""
    from backend.lib.session_signer import create_signed_session

    # Create a valid signed token for a session that doesn't exist in DB
    signed = create_signed_session()
    raw_id = signed.rsplit(".", 1)[0]

    resp = await e2e_client.get(
        f"/api/sessions/{raw_id}/history",
        headers={"X-Session-Token": signed},
    )
    assert resp.status_code == 404


async def test_multi_message_session_history(e2e_client, mock_anthropic, mock_orchestrator_deps):
    """Multiple messages in one session produce ordered history."""
    # First message
    mock_anthropic.messages.stream.return_value = make_text_stream("Answer one.")
    resp1 = await e2e_client.post(
        "/api/chat",
        json={"message": "Question one"},
    )
    events1 = parse_sse_events(resp1.text)
    signed_token = next(e for e in events1 if e.get("done"))["signed_session_id"]

    # Second message
    mock_anthropic.messages.stream.return_value = make_text_stream("Answer two.")
    await e2e_client.post(
        "/api/chat",
        json={"session_id": signed_token, "message": "Question two"},
    )

    # Fetch history — should have 4 messages (2 user + 2 assistant)
    raw_id = signed_token.rsplit(".", 1)[0]
    hist_resp = await e2e_client.get(
        f"/api/sessions/{raw_id}/history",
        headers={"X-Session-Token": signed_token},
    )
    data = hist_resp.json()
    assert len(data["messages"]) >= 4
    # Check ordering: user, assistant, user, assistant
    roles = [m["role"] for m in data["messages"][:4]]
    assert roles == ["user", "assistant", "user", "assistant"]
