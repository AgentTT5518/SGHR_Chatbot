"""
Tests for backend.chat.orchestrator

Mocks the Anthropic client, session_manager, context_manager, and tool registry
so no real API calls or DB access occur. Tests the SSE event flow, tool dispatch,
and error paths.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.chat.orchestrator import (
    FALLBACK_MAX_ITERATIONS,
    _extract_sources_from_tool_results,
    _sse,
    _tool_display_name,
    orchestrate,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _collect(gen) -> list[dict]:
    """Drain an async generator and parse all SSE payloads."""
    events = []
    async for line in gen:
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


@dataclass
class FakeContentBlock:
    """Mimics an Anthropic content block."""
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict | None = None


@dataclass
class FakeMessage:
    """Mimics the final message from the Anthropic streaming API."""
    content: list


class FakeStreamEvent:
    """Mimics a streaming event."""
    def __init__(self, event_type: str, content_block=None, text: str = ""):
        self.type = event_type
        self.content_block = content_block
        self.text = text


class _FakeAsyncStream:
    """Async context manager + async iterator that mimics client.messages.stream()."""

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


def _make_text_stream(text_chunks: list[str]):
    """Build a mock stream context that yields text events and returns a text-only message."""
    events = [FakeStreamEvent("text", text=chunk) for chunk in text_chunks]
    final_content = [FakeContentBlock(type="text", text="".join(text_chunks))]
    return _FakeAsyncStream(events, FakeMessage(content=final_content))


def _make_tool_use_stream(tool_name: str, tool_id: str, tool_input: dict):
    """Build a mock stream that emits a tool_use content block."""
    tool_block = FakeContentBlock(type="tool_use", name=tool_name, id=tool_id, input=tool_input)
    events = [FakeStreamEvent("content_block_start", content_block=tool_block)]
    final_content = [FakeContentBlock(type="tool_use", name=tool_name, id=tool_id, input=tool_input)]
    return _FakeAsyncStream(events, FakeMessage(content=final_content))


# ── Common fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_session_and_context():
    """Patch session_manager and context_manager for all orchestrator tests."""
    from backend.chat.context_manager import SessionContext

    fake_ctx = SessionContext(summary="", facts={}, recent_messages=[], token_count=0)

    with (
        patch("backend.chat.orchestrator.session_manager.get_or_create", new=AsyncMock()),
        patch("backend.chat.orchestrator.session_manager.add_message", new=AsyncMock()),
        patch("backend.chat.orchestrator.context_manager.build_context", new=AsyncMock(return_value=fake_ctx)),
        patch("backend.chat.orchestrator.context_manager.format_context_for_prompt", return_value=("", [])),
        patch("backend.chat.orchestrator.context_manager.maybe_update_summary", new=AsyncMock()),
        patch("backend.chat.orchestrator.count_tokens", new=AsyncMock(return_value=500)),
        patch("backend.chat.orchestrator.register_all_tools"),
        patch("backend.chat.orchestrator.get_all_schemas", return_value=[]),
    ):
        yield


# ── Unit tests ───────────────────────────────────────────────────────────────


class TestHelpers:
    def test_sse_formats_correctly(self):
        result = _sse({"token": "hello", "done": False})
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
        parsed = json.loads(result[6:])
        assert parsed["token"] == "hello"

    def test_tool_display_name_known(self):
        assert "Employment Act" in _tool_display_name("search_employment_act")

    def test_tool_display_name_unknown(self):
        result = _tool_display_name("some_new_tool")
        assert "some_new_tool" in result

    def test_extract_sources_from_tool_results_empty(self):
        assert _extract_sources_from_tool_results([]) == []

    def test_extract_sources_from_tool_results_with_sources(self):
        messages = [
            {"role": "user", "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": (
                        "Source: Employment Act, Part IV, s 38 — Hours of work\n"
                        "URL: \n\n"
                        "Some text about hours of work.\n\n"
                        "Source: MOM — Annual Leave\n"
                        "URL: https://www.mom.gov.sg/annual-leave\n\n"
                        "Some text about annual leave."
                    ),
                }
            ]},
        ]
        sources = _extract_sources_from_tool_results(messages)
        assert len(sources) == 2
        assert sources[0]["label"] == "Employment Act, Part IV, s 38 — Hours of work"
        assert sources[1]["url"] == "https://www.mom.gov.sg/annual-leave"

    def test_extract_sources_deduplicates(self):
        messages = [
            {"role": "user", "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "Source: Employment Act, s 38\nURL: \n\nText",
                },
                {
                    "type": "tool_result",
                    "tool_use_id": "t2",
                    "content": "Source: Employment Act, s 38\nURL: \n\nMore text",
                },
            ]},
        ]
        sources = _extract_sources_from_tool_results(messages)
        assert len(sources) == 1

    def test_extract_sources_ignores_non_tool_result(self):
        messages = [
            {"role": "assistant", "content": "Some text with Source: fake"},
            {"role": "user", "content": "A plain user message"},
        ]
        sources = _extract_sources_from_tool_results(messages)
        assert sources == []


# ── Integration tests (SSE event flow) ───────────────────────────────────────


class TestOrchestrateDirectAnswer:
    """Claude responds with text only — no tool calls."""

    @pytest.mark.asyncio
    async def test_streams_text_tokens(self):
        text_stream = _make_text_stream(["Hello", " world"])
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = text_stream

        with patch("backend.chat.orchestrator.get_client", return_value=mock_client):
            events = await _collect(orchestrate("s1", "u1", "Hi there"))

        token_events = [e for e in events if "token" in e and not e.get("done")]
        assert any(e["token"] == "Hello" for e in token_events)
        assert any(e["token"] == " world" for e in token_events)

    @pytest.mark.asyncio
    async def test_final_event_has_done_and_sources(self):
        text_stream = _make_text_stream(["Answer"])
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = text_stream

        with patch("backend.chat.orchestrator.get_client", return_value=mock_client):
            events = await _collect(orchestrate("s2", "u1", "question"))

        final = events[-1]
        assert final["done"] is True
        assert "sources" in final

    @pytest.mark.asyncio
    async def test_persists_messages(self):
        text_stream = _make_text_stream(["Answer"])
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = text_stream
        mock_add = AsyncMock()

        with (
            patch("backend.chat.orchestrator.get_client", return_value=mock_client),
            patch("backend.chat.orchestrator.session_manager.add_message", mock_add),
        ):
            await _collect(orchestrate("s3", "u1", "test question"))

        assert mock_add.call_count == 2
        roles = [c.args[1] for c in mock_add.call_args_list]
        assert roles == ["user", "assistant"]


class TestOrchestrateSingleToolCall:
    """Claude calls one tool, then answers."""

    @pytest.mark.asyncio
    async def test_single_tool_then_answer(self):
        # First call: tool_use, second call: text answer
        tool_stream = _make_tool_use_stream(
            "search_employment_act", "tool_1", {"query": "overtime"}
        )
        text_stream = _make_text_stream(["Based on the Employment Act..."])

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [tool_stream, text_stream]

        with (
            patch("backend.chat.orchestrator.get_client", return_value=mock_client),
            patch("backend.chat.orchestrator.dispatch_tool", new=AsyncMock(return_value="Source: Employment Act, s 38\nURL: \n\nOvertime provisions...")),
        ):
            events = await _collect(orchestrate("s4", "u1", "What is overtime?"))

        # Should have: status event, token events, done event
        status_events = [e for e in events if "status" in e]
        assert len(status_events) == 1
        assert "Employment Act" in status_events[0]["detail"]

        token_events = [e for e in events if "token" in e and not e.get("done")]
        assert len(token_events) > 0

        final = events[-1]
        assert final["done"] is True
        assert len(final["sources"]) > 0

    @pytest.mark.asyncio
    async def test_tool_error_handled_gracefully(self):
        tool_stream = _make_tool_use_stream(
            "search_employment_act", "tool_1", {"query": "overtime"}
        )
        text_stream = _make_text_stream(["I encountered an issue..."])

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [tool_stream, text_stream]

        with (
            patch("backend.chat.orchestrator.get_client", return_value=mock_client),
            patch("backend.chat.orchestrator.dispatch_tool", new=AsyncMock(side_effect=RuntimeError("DB connection failed"))),
        ):
            events = await _collect(orchestrate("s5", "u1", "question"))

        # Should still complete — tool error passed back to Claude
        final = events[-1]
        assert final["done"] is True


class TestOrchestrateMultiToolChain:
    """Claude calls multiple tools across iterations."""

    @pytest.mark.asyncio
    async def test_two_tool_calls_then_answer(self):
        # Iteration 1: tool_use
        tool_stream_1 = _make_tool_use_stream(
            "check_eligibility", "tool_1", {"salary_monthly": 3000, "role": "non_workman", "employment_type": "full_time"}
        )
        # Iteration 2: tool_use
        tool_stream_2 = _make_tool_use_stream(
            "search_employment_act", "tool_2", {"query": "Part IV eligibility"}
        )
        # Iteration 3: text answer
        text_stream = _make_text_stream(["Based on your salary..."])

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [tool_stream_1, tool_stream_2, text_stream]

        with (
            patch("backend.chat.orchestrator.get_client", return_value=mock_client),
            patch("backend.chat.orchestrator.dispatch_tool", new=AsyncMock(return_value="Tool result text")),
        ):
            events = await _collect(orchestrate("s6", "u1", "Am I eligible for overtime?"))

        status_events = [e for e in events if "status" in e]
        assert len(status_events) == 2  # two tool calls

        final = events[-1]
        assert final["done"] is True


class TestOrchestrateMaxIterations:
    """Max iterations guard emits fallback."""

    @pytest.mark.asyncio
    async def test_max_iterations_fallback(self):
        # All iterations return tool_use — should hit max
        tool_streams = [
            _make_tool_use_stream(
                "search_employment_act", f"tool_{i}", {"query": f"query {i}"}
            )
            for i in range(5)
        ]

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = tool_streams

        with (
            patch("backend.chat.orchestrator.get_client", return_value=mock_client),
            patch("backend.chat.orchestrator.dispatch_tool", new=AsyncMock(return_value="Some result")),
        ):
            events = await _collect(orchestrate("s7", "u1", "complex question"))

        final = events[-1]
        assert final["done"] is True
        assert FALLBACK_MAX_ITERATIONS in final["token"]


class TestOrchestrateAPIError:
    """API errors are handled gracefully."""

    @pytest.mark.asyncio
    async def test_api_error_yields_error_event(self):
        import anthropic

        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(side_effect=anthropic.APIStatusError(
            message="rate limited",
            response=MagicMock(status_code=429, headers={}),
            body={},
        ))
        stream_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = stream_ctx

        with patch("backend.chat.orchestrator.get_client", return_value=mock_client):
            events = await _collect(orchestrate("s8", "u1", "question"))

        assert events[-1]["done"] is True
        assert "error" in events[-1]

    @pytest.mark.asyncio
    async def test_unexpected_error_yields_error_event(self):
        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("unexpected"))
        stream_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = stream_ctx

        with patch("backend.chat.orchestrator.get_client", return_value=mock_client):
            events = await _collect(orchestrate("s9", "u1", "question"))

        assert events[-1]["done"] is True
        assert "error" in events[-1]
        assert "unexpected" in events[-1]["error"]


class TestSSEEventOrder:
    """Verify correct ordering of SSE events."""

    @pytest.mark.asyncio
    async def test_status_before_tokens_before_done(self):
        tool_stream = _make_tool_use_stream(
            "search_employment_act", "tool_1", {"query": "leave"}
        )
        text_stream = _make_text_stream(["The answer is..."])

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [tool_stream, text_stream]

        with (
            patch("backend.chat.orchestrator.get_client", return_value=mock_client),
            patch("backend.chat.orchestrator.dispatch_tool", new=AsyncMock(return_value="Result")),
        ):
            events = await _collect(orchestrate("s10", "u1", "leave entitlement"))

        # Find indices
        status_idx = next(i for i, e in enumerate(events) if "status" in e)
        token_idx = next(i for i, e in enumerate(events) if "token" in e and not e.get("done"))
        done_idx = next(i for i, e in enumerate(events) if e.get("done"))

        assert status_idx < token_idx < done_idx
