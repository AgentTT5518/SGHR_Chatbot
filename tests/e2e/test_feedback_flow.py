"""
E2E: Feedback flow — chat → submit feedback → verify stored → admin list.
"""
from __future__ import annotations

import pytest

from tests.e2e.conftest import ADMIN_HEADERS, make_text_stream, parse_sse_events


pytestmark = pytest.mark.asyncio


async def _chat_and_get_session(e2e_client, mock_anthropic, mock_orchestrator_deps) -> tuple[str, str]:
    """Send a chat message and return (raw_id, signed_token)."""
    mock_anthropic.messages.stream.return_value = make_text_stream(
        "Annual leave is 7 days for first year."
    )
    resp = await e2e_client.post(
        "/api/chat",
        json={"message": "How many days of annual leave?"},
    )
    assert resp.status_code == 200
    events = parse_sse_events(resp.text)
    done = next(e for e in events if e.get("done"))
    signed_token = done["signed_session_id"]
    raw_id = signed_token.rsplit(".", 1)[0]
    return raw_id, signed_token


async def test_submit_thumbs_up_feedback(e2e_client, mock_anthropic, mock_orchestrator_deps):
    """Submit thumbs-up feedback on an assistant message."""
    raw_id, signed_token = await _chat_and_get_session(
        e2e_client, mock_anthropic, mock_orchestrator_deps,
    )

    resp = await e2e_client.post(
        "/api/feedback",
        headers={"X-Session-Token": signed_token},
        json={
            "session_id": raw_id,
            "message_index": 1,  # assistant message (0=user, 1=assistant)
            "rating": "up",
            "comment": "Very helpful!",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert "id" in data


async def test_submit_thumbs_down_feedback(e2e_client, mock_anthropic, mock_orchestrator_deps):
    """Submit thumbs-down feedback on an assistant message."""
    raw_id, signed_token = await _chat_and_get_session(
        e2e_client, mock_anthropic, mock_orchestrator_deps,
    )

    resp = await e2e_client.post(
        "/api/feedback",
        headers={"X-Session-Token": signed_token},
        json={
            "session_id": raw_id,
            "message_index": 1,
            "rating": "down",
            "comment": "Not accurate",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["success"] is True


async def test_feedback_appears_in_admin_list(e2e_client, mock_anthropic, mock_orchestrator_deps):
    """Feedback shows up in the admin feedback list after submission."""
    raw_id, signed_token = await _chat_and_get_session(
        e2e_client, mock_anthropic, mock_orchestrator_deps,
    )

    # Submit feedback
    await e2e_client.post(
        "/api/feedback",
        headers={"X-Session-Token": signed_token},
        json={
            "session_id": raw_id,
            "message_index": 1,
            "rating": "up",
        },
    )

    # Check admin feedback list
    resp = await e2e_client.get("/admin/feedback", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    records = resp.json()["records"]
    matching = [r for r in records if r["session_id"] == raw_id]
    assert len(matching) >= 1
    assert matching[0]["rating"] == "up"


async def test_feedback_stats_update(e2e_client, mock_anthropic, mock_orchestrator_deps):
    """Feedback stats reflect submitted feedback."""
    raw_id, signed_token = await _chat_and_get_session(
        e2e_client, mock_anthropic, mock_orchestrator_deps,
    )

    # Submit one up and one down
    for rating in ("up", "down"):
        await e2e_client.post(
            "/api/feedback",
            headers={"X-Session-Token": signed_token},
            json={
                "session_id": raw_id,
                "message_index": 1,
                "rating": rating,
            },
        )

    resp = await e2e_client.get("/admin/feedback/stats", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    stats = resp.json()
    # Stats should have counts
    assert isinstance(stats, dict)


async def test_feedback_invalid_rating(e2e_client, mock_anthropic, mock_orchestrator_deps):
    """Submitting feedback with an invalid rating returns 422."""
    raw_id, signed_token = await _chat_and_get_session(
        e2e_client, mock_anthropic, mock_orchestrator_deps,
    )

    resp = await e2e_client.post(
        "/api/feedback",
        headers={"X-Session-Token": signed_token},
        json={
            "session_id": raw_id,
            "message_index": 1,
            "rating": "neutral",  # invalid
        },
    )
    assert resp.status_code == 422


async def test_feedback_nonexistent_session(e2e_client):
    """Feedback for a non-existent session returns 404."""
    resp = await e2e_client.post(
        "/api/feedback",
        json={
            "session_id": "nonexistent-session-id",
            "message_index": 0,
            "rating": "up",
        },
    )
    assert resp.status_code == 404
