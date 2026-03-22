"""
Integration tests for backend.chat.orchestrator — tool dispatch loop.

These tests mock the Anthropic client (returning pre-canned streaming responses)
but use **real tool dispatch** through the registry. The retriever, session_manager,
profile_store, and semantic_cache are mocked to avoid DB/network access.

Test matrix:
1. Single tool call (search) → text response
2. Multi-tool iteration (search → calculation → text response)
3. Max iterations reached → fallback message
4. Tool error handling (tool raises → error result fed back to Claude)
5. Semantic cache hit → skips Claude call entirely
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.chat.orchestrator import (
    FALLBACK_MAX_ITERATIONS,
    orchestrate,
)
from backend.memory.semantic_cache import CacheResult


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _collect(gen) -> list[dict]:
    """Drain an async generator and parse all SSE payloads."""
    events: list[dict] = []
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
    def __init__(self, event_type: str, content_block: Any = None, text: str = ""):
        self.type = event_type
        self.content_block = content_block
        self.text = text


class _FakeAsyncStream:
    """Async context manager + async iterator mimicking client.messages.stream()."""

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


def _make_text_stream(text_chunks: list[str]) -> _FakeAsyncStream:
    """Build a mock stream that yields text events and a text-only final message."""
    events = [FakeStreamEvent("text", text=chunk) for chunk in text_chunks]
    final_content = [FakeContentBlock(type="text", text="".join(text_chunks))]
    return _FakeAsyncStream(events, FakeMessage(content=final_content))


def _make_tool_use_stream(
    tool_name: str, tool_id: str, tool_input: dict
) -> _FakeAsyncStream:
    """Build a mock stream that emits a tool_use content block."""
    tool_block = FakeContentBlock(
        type="tool_use", name=tool_name, id=tool_id, input=tool_input,
    )
    events = [FakeStreamEvent("content_block_start", content_block=tool_block)]
    final_content = [
        FakeContentBlock(type="tool_use", name=tool_name, id=tool_id, input=tool_input),
    ]
    return _FakeAsyncStream(events, FakeMessage(content=final_content))


def _make_multi_tool_stream(
    tools: list[tuple[str, str, dict]],
) -> _FakeAsyncStream:
    """Build a mock stream that emits multiple tool_use blocks in a single turn."""
    events = []
    final_content = []
    for tool_name, tool_id, tool_input in tools:
        block = FakeContentBlock(
            type="tool_use", name=tool_name, id=tool_id, input=tool_input,
        )
        events.append(FakeStreamEvent("content_block_start", content_block=block))
        final_content.append(
            FakeContentBlock(type="tool_use", name=tool_name, id=tool_id, input=tool_input),
        )
    return _FakeAsyncStream(events, FakeMessage(content=final_content))


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _mock_session_context_and_memory():
    """Patch session_manager, context_manager, profile_store, semantic_cache."""
    from backend.chat.context_manager import SessionContext

    fake_ctx = SessionContext(summary="", facts={}, recent_messages=[], token_count=0)

    with (
        patch("backend.chat.orchestrator.session_manager.get_or_create", new=AsyncMock()),
        patch("backend.chat.orchestrator.session_manager.add_message", new=AsyncMock()),
        patch(
            "backend.chat.orchestrator.context_manager.build_context",
            new=AsyncMock(return_value=fake_ctx),
        ),
        patch(
            "backend.chat.orchestrator.context_manager.format_context_for_prompt",
            return_value=("", []),
        ),
        patch("backend.chat.orchestrator.context_manager.maybe_update_summary", new=AsyncMock()),
        patch("backend.chat.orchestrator.count_tokens", new=AsyncMock(return_value=500)),
        patch("backend.chat.orchestrator.semantic_cache.check_cache", return_value=None),
        patch("backend.chat.orchestrator.profile_store.get_profile", new=AsyncMock(return_value=None)),
        patch("backend.chat.orchestrator.fact_extractor.extract_profile_facts", new=AsyncMock(return_value=[])),
    ):
        yield


@pytest.fixture(autouse=True)
def _register_real_tools():
    """Register real tool handlers via the registry, but mock their dependencies.

    Retrieval tools depend on the retriever/embedder/compressor which need a
    vector store. We mock those at the retrieval_tools layer so that dispatch
    goes through the real registry → real handler → mocked retriever.
    """
    from backend.chat.tools.registry import TOOL_DISPATCH, register_all_tools

    # Clear any stale registrations from previous tests
    TOOL_DISPATCH.clear()

    with (
        # Mock retrieval dependencies used inside retrieval_tools
        patch("backend.chat.tools.retrieval_tools._enhanced_retrieve", new=AsyncMock(
            return_value=[
                {
                    "content": "Overtime provisions under Part IV apply to workmen earning up to $4,500.",
                    "source": "Employment Act, Part IV, s 38",
                    "url": "",
                },
            ],
        )),
        patch("backend.chat.tools.retrieval_tools.get_section_2", return_value=[
            {
                "content": "'workman' means any person who has entered into a contract of service...",
                "source": "Employment Act, s 2",
                "url": "",
            },
        ]),
    ):
        register_all_tools()
        yield


# ── Test 1: Single tool call → text response ────────────────────────────────


class TestSingleToolCallIntegration:
    """Claude calls search_employment_act once, gets real tool output, then answers."""

    @pytest.mark.asyncio
    async def test_search_tool_dispatches_and_returns_text(self):
        """Verify the full flow: tool_use → real dispatch → text answer with sources."""
        tool_stream = _make_tool_use_stream(
            "search_employment_act", "tool_1", {"query": "overtime pay"},
        )
        text_stream = _make_text_stream(["Under the Employment Act, overtime pay applies..."])

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [tool_stream, text_stream]

        with patch("backend.chat.orchestrator.get_client", return_value=mock_client):
            events = await _collect(orchestrate("s-int-1", "u1", "What is overtime pay?"))

        # Status event for tool execution
        status_events = [e for e in events if "status" in e]
        assert len(status_events) == 1
        assert "Employment Act" in status_events[0]["detail"]

        # Token events from the text response
        token_events = [e for e in events if "token" in e and not e.get("done")]
        assert len(token_events) > 0

        # Final done event
        final = events[-1]
        assert final["done"] is True
        assert "sources" in final

    @pytest.mark.asyncio
    async def test_calculation_tool_dispatches_with_real_logic(self):
        """Verify calculation tools produce deterministic results through real dispatch."""
        tool_stream = _make_tool_use_stream(
            "calculate_leave_entitlement",
            "tool_calc_1",
            {"tenure_years": 3, "employment_type": "full_time", "leave_type": "annual"},
        )
        text_stream = _make_text_stream(["You are entitled to 9 days of annual leave."])

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [tool_stream, text_stream]

        # Capture what Claude sees as the tool result
        original_stream = _FakeAsyncStream
        call_messages: list[Any] = []

        real_stream_fn = mock_client.messages.stream

        def capture_messages(**kwargs):
            call_messages.append(kwargs.get("messages", []))
            return real_stream_fn(**kwargs)

        mock_client.messages.stream.side_effect = [tool_stream, text_stream]

        with patch("backend.chat.orchestrator.get_client", return_value=mock_client):
            events = await _collect(orchestrate("s-int-2", "u1", "How many annual leave days for 3 years?"))

        final = events[-1]
        assert final["done"] is True

        # Verify the client was called twice (tool iteration + final answer)
        assert mock_client.messages.stream.call_count == 2

    @pytest.mark.asyncio
    async def test_check_eligibility_tool_produces_real_output(self):
        """check_eligibility is a pure calculation — verify real dispatch output."""
        tool_stream = _make_tool_use_stream(
            "check_eligibility",
            "tool_elig_1",
            {"salary_monthly": 3000, "role": "non_workman", "employment_type": "full_time"},
        )
        text_stream = _make_text_stream(["Based on your salary, Part IV applies."])

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [tool_stream, text_stream]

        with patch("backend.chat.orchestrator.get_client", return_value=mock_client):
            events = await _collect(orchestrate("s-int-3", "u1", "Am I covered by Part IV?"))

        # Two calls: one for tool_use response, one for text answer
        assert mock_client.messages.stream.call_count == 2
        assert events[-1]["done"] is True


# ── Test 2: Multi-tool iteration ─────────────────────────────────────────────


class TestMultiToolIterationIntegration:
    """Claude calls multiple tools across iterations before answering."""

    @pytest.mark.asyncio
    async def test_eligibility_then_search_then_answer(self):
        """Two sequential tool calls across iterations → final text answer."""
        # Iteration 1: check_eligibility
        tool_stream_1 = _make_tool_use_stream(
            "check_eligibility",
            "tool_1",
            {"salary_monthly": 3000, "role": "non_workman", "employment_type": "full_time"},
        )
        # Iteration 2: search_employment_act
        tool_stream_2 = _make_tool_use_stream(
            "search_employment_act",
            "tool_2",
            {"query": "Part IV overtime provisions"},
        )
        # Iteration 3: text answer
        text_stream = _make_text_stream(["You are covered by Part IV. Overtime rates are..."])

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [tool_stream_1, tool_stream_2, text_stream]

        with patch("backend.chat.orchestrator.get_client", return_value=mock_client):
            events = await _collect(orchestrate("s-int-4", "u1", "Do I get overtime at $3000?"))

        # Two status events for two tool calls
        status_events = [e for e in events if "status" in e]
        assert len(status_events) == 2

        # Final event has done + sources
        final = events[-1]
        assert final["done"] is True
        assert "sources" in final

        # Three API calls total
        assert mock_client.messages.stream.call_count == 3

    @pytest.mark.asyncio
    async def test_parallel_tools_in_single_turn(self):
        """Claude requests two tools in one turn — both dispatched, results fed back."""
        # Single turn with two tool_use blocks
        multi_stream = _make_multi_tool_stream([
            ("search_employment_act", "tool_a", {"query": "annual leave"}),
            ("search_mom_guidelines", "tool_b", {"query": "annual leave application"}),
        ])
        text_stream = _make_text_stream(["Annual leave entitlement is..."])

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [multi_stream, text_stream]

        with patch("backend.chat.orchestrator.get_client", return_value=mock_client):
            events = await _collect(orchestrate("s-int-5", "u1", "Tell me about annual leave"))

        # Two status events (one per tool in the same turn)
        status_events = [e for e in events if "status" in e]
        assert len(status_events) == 2

        assert events[-1]["done"] is True


# ── Test 3: Max iterations reached → fallback ───────────────────────────────


class TestMaxIterationsIntegration:
    """Orchestrator hits the iteration cap and emits the fallback message."""

    @pytest.mark.asyncio
    async def test_five_tool_iterations_triggers_fallback(self):
        """All 5 iterations produce tool_use → fallback message emitted."""
        tool_streams = [
            _make_tool_use_stream(
                "search_employment_act", f"tool_{i}", {"query": f"query {i}"},
            )
            for i in range(5)
        ]

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = tool_streams

        with patch("backend.chat.orchestrator.get_client", return_value=mock_client):
            events = await _collect(orchestrate("s-int-6", "u1", "very complex question"))

        # 5 status events from 5 tool calls
        status_events = [e for e in events if "status" in e]
        assert len(status_events) == 5

        # Final event is the fallback
        final = events[-1]
        assert final["done"] is True
        assert FALLBACK_MAX_ITERATIONS in final["token"]
        assert final["sources"] == []

    @pytest.mark.asyncio
    async def test_fallback_persists_messages(self):
        """After max iterations, both user message and fallback are persisted."""
        tool_streams = [
            _make_tool_use_stream(
                "search_employment_act", f"tool_{i}", {"query": f"q{i}"},
            )
            for i in range(5)
        ]

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = tool_streams
        mock_add = AsyncMock()

        with (
            patch("backend.chat.orchestrator.get_client", return_value=mock_client),
            patch("backend.chat.orchestrator.session_manager.add_message", mock_add),
        ):
            await _collect(orchestrate("s-int-7", "u1", "hard question"))

        assert mock_add.call_count == 2
        roles = [c.args[1] for c in mock_add.call_args_list]
        assert roles == ["user", "assistant"]
        # The assistant message should be the fallback
        assert mock_add.call_args_list[1].args[2] == FALLBACK_MAX_ITERATIONS


# ── Test 4: Tool error handling ──────────────────────────────────────────────


class TestToolErrorHandlingIntegration:
    """Tool raises an exception → error result fed back to Claude → graceful recovery."""

    @pytest.mark.asyncio
    async def test_tool_exception_feeds_error_back_to_claude(self):
        """When a tool handler raises, the error is passed as tool_result with is_error."""
        tool_stream = _make_tool_use_stream(
            "search_employment_act", "tool_err_1", {"query": "overtime"},
        )
        text_stream = _make_text_stream(["I encountered a search error. Let me try another approach."])

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [tool_stream, text_stream]

        # Make the retrieval tool raise an exception
        with (
            patch("backend.chat.orchestrator.get_client", return_value=mock_client),
            patch(
                "backend.chat.tools.retrieval_tools._enhanced_retrieve",
                new=AsyncMock(side_effect=RuntimeError("Vector store unavailable")),
            ),
        ):
            events = await _collect(orchestrate("s-int-8", "u1", "overtime rules"))

        # Should still complete gracefully
        final = events[-1]
        assert final["done"] is True
        assert "error" not in final  # no top-level error — Claude recovered

        # Two API calls: tool_use response + recovery text
        assert mock_client.messages.stream.call_count == 2

    @pytest.mark.asyncio
    async def test_unknown_tool_name_feeds_error_back(self):
        """If Claude hallucinates a tool name, KeyError is caught and fed back."""
        tool_stream = _make_tool_use_stream(
            "nonexistent_tool", "tool_bad_1", {"query": "anything"},
        )
        text_stream = _make_text_stream(["Let me search using the correct tool."])

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [tool_stream, text_stream]

        with patch("backend.chat.orchestrator.get_client", return_value=mock_client):
            events = await _collect(orchestrate("s-int-9", "u1", "some question"))

        # Should recover and produce a done event
        final = events[-1]
        assert final["done"] is True

    @pytest.mark.asyncio
    async def test_tool_error_message_contains_exception_text(self):
        """Verify the error string passed to Claude includes the exception message."""
        tool_stream = _make_tool_use_stream(
            "search_employment_act", "tool_err_2", {"query": "test"},
        )
        text_stream = _make_text_stream(["Sorry, I had trouble searching."])

        mock_client = MagicMock()
        mock_client.messages.stream.side_effect = [tool_stream, text_stream]

        captured_messages: list[Any] = []
        original_side_effect = [tool_stream, text_stream]
        call_count = 0

        def capture_stream(**kwargs):
            nonlocal call_count
            msgs = kwargs.get("messages", [])
            captured_messages.append(msgs)
            result = original_side_effect[call_count]
            call_count += 1
            return result

        mock_client.messages.stream.side_effect = capture_stream

        with (
            patch("backend.chat.orchestrator.get_client", return_value=mock_client),
            patch(
                "backend.chat.tools.retrieval_tools._enhanced_retrieve",
                new=AsyncMock(side_effect=ConnectionError("DB timeout")),
            ),
        ):
            await _collect(orchestrate("s-int-10", "u1", "test question"))

        # Second call's messages should contain the error tool_result
        assert len(captured_messages) == 2
        second_call_messages = captured_messages[1]
        # Find the tool_result message
        tool_result_msg = next(
            (m for m in second_call_messages if m.get("role") == "user"
             and isinstance(m.get("content"), list)
             and any(b.get("type") == "tool_result" for b in m["content"])),
            None,
        )
        assert tool_result_msg is not None
        tool_result = tool_result_msg["content"][0]
        assert tool_result["is_error"] is True
        assert "DB timeout" in tool_result["content"]


# ── Test 5: Semantic cache hit → skips Claude entirely ───────────────────────


class TestSemanticCacheHitIntegration:
    """When semantic cache returns a hit, orchestrator streams it without calling Claude."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_claude_call(self):
        """High-confidence cache hit → no Anthropic API calls, cached answer streamed."""
        cached = CacheResult(
            answer="Annual leave starts at 7 days after 1 year of service.",
            sources=[{"label": "Employment Act, s 43", "url": ""}],
            confidence="high",
            disclaimer=None,
        )

        mock_client = MagicMock()

        with (
            patch("backend.chat.orchestrator.get_client", return_value=mock_client),
            patch("backend.chat.orchestrator.semantic_cache.check_cache", return_value=cached),
        ):
            events = await _collect(orchestrate("s-int-11", "u1", "How many annual leave days?"))

        # Only one event: the cached answer as a done event
        assert len(events) == 1
        final = events[0]
        assert final["done"] is True
        assert "Annual leave starts at 7 days" in final["token"]
        assert final["sources"] == [{"label": "Employment Act, s 43", "url": ""}]

        # Claude was never called
        mock_client.messages.stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_hit_medium_confidence_includes_disclaimer(self):
        """Medium-confidence cache hit → answer includes disclaimer prefix."""
        cached = CacheResult(
            answer="Overtime is 1.5x the hourly basic rate.",
            sources=[{"label": "Employment Act, s 38", "url": ""}],
            confidence="medium",
            disclaimer="This is a verified answer but your situation may differ.",
        )

        mock_client = MagicMock()

        with (
            patch("backend.chat.orchestrator.get_client", return_value=mock_client),
            patch("backend.chat.orchestrator.semantic_cache.check_cache", return_value=cached),
        ):
            events = await _collect(orchestrate("s-int-12", "u1", "What is overtime rate?"))

        final = events[0]
        assert final["done"] is True
        # Disclaimer should be prepended
        assert "This is a verified answer" in final["token"]
        assert "Overtime is 1.5x" in final["token"]

        mock_client.messages.stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_hit_persists_messages(self):
        """Cache hit still persists user and assistant messages to session."""
        cached = CacheResult(
            answer="Cached answer.",
            sources=[],
            confidence="high",
            disclaimer=None,
        )

        mock_client = MagicMock()
        mock_add = AsyncMock()

        with (
            patch("backend.chat.orchestrator.get_client", return_value=mock_client),
            patch("backend.chat.orchestrator.semantic_cache.check_cache", return_value=cached),
            patch("backend.chat.orchestrator.session_manager.add_message", mock_add),
        ):
            await _collect(orchestrate("s-int-13", "u1", "cached question"))

        assert mock_add.call_count == 2
        roles = [c.args[1] for c in mock_add.call_args_list]
        assert roles == ["user", "assistant"]

    @pytest.mark.asyncio
    async def test_cache_exception_falls_through_to_claude(self):
        """If semantic cache raises, orchestrator falls through to normal Claude flow."""
        text_stream = _make_text_stream(["Normal answer from Claude."])
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = text_stream

        with (
            patch("backend.chat.orchestrator.get_client", return_value=mock_client),
            patch(
                "backend.chat.orchestrator.semantic_cache.check_cache",
                side_effect=RuntimeError("Cache corrupted"),
            ),
        ):
            events = await _collect(orchestrate("s-int-14", "u1", "question"))

        # Should still get a normal answer
        final = events[-1]
        assert final["done"] is True
        assert "error" not in final

        # Claude was called (cache was bypassed)
        mock_client.messages.stream.assert_called_once()
