"""
E2E test configuration.

These tests use httpx.AsyncClient with the real FastAPI app. Only the Anthropic
Claude API is mocked (to avoid costs). ChromaDB and SQLite are real.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

from backend.main import app


# ── Anthropic mock helpers ────────────────────────────────────────────────────


@dataclass
class FakeContentBlock:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict | None = None


@dataclass
class FakeMessage:
    content: list


class FakeStreamEvent:
    def __init__(self, event_type: str, content_block: Any = None, text: str = ""):
        self.type = event_type
        self.content_block = content_block
        self.text = text


class FakeAsyncStream:
    """Async context manager + iterator mimicking client.messages.stream()."""

    def __init__(self, events: list, final_message: FakeMessage):
        self._events = events
        self._final_message = final_message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def __aiter__(self):
        return self._iter_events()

    async def _iter_events(self):
        for ev in self._events:
            yield ev

    async def get_final_message(self):
        return self._final_message


def make_text_stream(text: str) -> FakeAsyncStream:
    """Build a mock stream that yields a text-only response."""
    events = [FakeStreamEvent("text", text=text)]
    final_content = [FakeContentBlock(type="text", text=text)]
    return FakeAsyncStream(events, FakeMessage(content=final_content))


def make_tool_then_text_stream(
    tool_name: str,
    tool_input: dict,
    final_text: str,
) -> list[FakeAsyncStream]:
    """Return two streams: first triggers a tool call, second returns text."""
    # First stream: tool_use
    tool_block = FakeContentBlock(
        type="tool_use", id="toolu_e2e_1", name=tool_name, input=tool_input,
    )
    tool_events = [
        FakeStreamEvent("content_block_start", content_block=tool_block),
    ]
    tool_final = FakeMessage(content=[tool_block])
    first = FakeAsyncStream(tool_events, tool_final)

    # Second stream: text answer
    second = make_text_stream(final_text)
    return [first, second]


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def e2e_client():
    """Async HTTP client wired to the real FastAPI app."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.fixture
def mock_anthropic():
    """Patch the Anthropic client used by the orchestrator.

    Returns a mock client whose ``messages.stream`` can be configured per test.
    Usage in tests::

        mock_anthropic.messages.stream.side_effect = [make_text_stream("hi")]
    """
    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.stream = MagicMock()
    mock_client.count_tokens = AsyncMock(return_value=MagicMock(input_tokens=100))

    with patch("backend.chat.orchestrator.get_client", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_orchestrator_deps():
    """Mock heavy dependencies of the orchestrator (profile, cache, context).

    Keeps tool dispatch real but avoids expensive or flaky side-effects.
    """
    with (
        patch("backend.chat.orchestrator.semantic_cache.check_cache", return_value=None),
        patch("backend.chat.orchestrator.profile_store.get_profile", new_callable=AsyncMock, return_value=None),
        patch("backend.chat.orchestrator.fact_extractor.extract_profile_facts", new_callable=AsyncMock, return_value={}),
        patch("backend.chat.orchestrator.context_manager.build_context", new_callable=AsyncMock, return_value=MagicMock(summary="", recent_pairs=[])),
        patch("backend.chat.orchestrator.context_manager.format_context_for_prompt", return_value=("", [])),
        patch("backend.chat.orchestrator.context_manager.maybe_update_summary", new_callable=AsyncMock),
        patch("backend.chat.orchestrator.count_tokens", new_callable=AsyncMock, return_value=100),
    ):
        yield


ADMIN_HEADERS: dict[str, str] = {"X-Admin-Key": "dev-only-key"}


def parse_sse_events(text: str) -> list[dict]:
    """Parse SSE response body into a list of JSON events."""
    events = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events
