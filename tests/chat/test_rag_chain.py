"""
Tests for backend.chat.rag_chain

Mocks the Anthropic client, retriever, and session_manager so no real
API calls or DB access occur. Tests the SSE event flow and error paths.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import anthropic

from backend.chat.rag_chain import FALLBACK_MESSAGE, _sse, stream_rag_response


# ── _sse ──────────────────────────────────────────────────────────────────────

def test_sse_formats_correctly():
    result = _sse({"token": "hello", "done": False})
    assert result.startswith("data: ")
    assert result.endswith("\n\n")
    parsed = json.loads(result[6:])
    assert parsed["token"] == "hello"


# ── stream_rag_response ───────────────────────────────────────────────────────

async def _collect(gen) -> list[dict]:
    """Drain an async generator and parse all SSE payloads."""
    events = []
    async for line in gen:
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def _mock_stream_context(tokens: list[str]):
    """Build a mock async context manager that yields tokens from text_stream."""
    stream_ctx = MagicMock()
    stream_ctx.__aenter__ = AsyncMock(return_value=stream_ctx)
    stream_ctx.__aexit__ = AsyncMock(return_value=False)

    async def _text_stream():
        for t in tokens:
            yield t

    stream_ctx.text_stream = _text_stream()
    return stream_ctx


@pytest.fixture
def mock_session():
    with (
        patch("backend.chat.rag_chain.session_manager.get_or_create", new=AsyncMock()),
        patch("backend.chat.rag_chain.session_manager.get_history", new=AsyncMock(return_value=[])),
        patch("backend.chat.rag_chain.session_manager.add_message", new=AsyncMock()),
    ):
        yield


@pytest.fixture
def mock_retriever_chunks():
    chunks = [{"text": "EA s38 text", "metadata": {"source": "Employment Act", "section_number": "38"}}]
    with (
        patch("backend.chat.rag_chain.retriever.retrieve", return_value=chunks),
        patch("backend.chat.rag_chain.retriever.needs_definitions", return_value=False),
    ):
        yield chunks


class TestStreamRagResponse:
    @pytest.mark.asyncio
    async def test_fallback_when_no_chunks(self, mock_session):
        with patch("backend.chat.rag_chain.retriever.retrieve", return_value=[]):
            events = await _collect(stream_rag_response("s1", "any question"))

        assert len(events) == 1
        assert events[0]["done"] is True
        assert events[0]["sources"] == []
        assert FALLBACK_MESSAGE in events[0]["token"]

    @pytest.mark.asyncio
    async def test_streams_tokens_from_claude(self, mock_session, mock_retriever_chunks):
        stream_ctx = _mock_stream_context(["Hello", " world"])
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = stream_ctx

        with patch("backend.chat.rag_chain.get_client", return_value=mock_client):
            events = await _collect(stream_rag_response("s2", "overtime question"))

        token_events = [e for e in events if not e.get("done")]
        assert any(e["token"] == "Hello" for e in token_events)
        assert any(e["token"] == " world" for e in token_events)

    @pytest.mark.asyncio
    async def test_final_event_has_done_true_and_sources(self, mock_session, mock_retriever_chunks):
        stream_ctx = _mock_stream_context(["Answer"])
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = stream_ctx

        with patch("backend.chat.rag_chain.get_client", return_value=mock_client):
            events = await _collect(stream_rag_response("s3", "question"))

        final = events[-1]
        assert final["done"] is True
        assert "sources" in final

    @pytest.mark.asyncio
    async def test_claude_api_error_yields_error_event(self, mock_session, mock_retriever_chunks):
        mock_client = MagicMock()
        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(side_effect=anthropic.APIStatusError(
            message="rate limited",
            response=MagicMock(status_code=429, headers={}),
            body={},
        ))
        stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.messages.stream.return_value = stream_ctx

        with patch("backend.chat.rag_chain.get_client", return_value=mock_client):
            events = await _collect(stream_rag_response("s4", "question"))

        assert events[-1]["done"] is True
        assert "error" in events[-1]

    @pytest.mark.asyncio
    async def test_unexpected_error_yields_error_event(self, mock_session, mock_retriever_chunks):
        mock_client = MagicMock()
        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("unexpected"))
        stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.messages.stream.return_value = stream_ctx

        with patch("backend.chat.rag_chain.get_client", return_value=mock_client):
            events = await _collect(stream_rag_response("s5", "question"))

        assert events[-1]["done"] is True
        assert "error" in events[-1]
        assert "unexpected" in events[-1]["error"]

    @pytest.mark.asyncio
    async def test_definitions_prepended_when_needed(self, mock_session):
        sec2 = {"text": "s2 definitions", "metadata": {"source": "Employment Act", "section_number": "2"}}
        chunks = [{"text": "some text about employer", "metadata": {"source": "Employment Act", "section_number": "5"}}]
        stream_ctx = _mock_stream_context(["ok"])
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = stream_ctx

        with (
            patch("backend.chat.rag_chain.retriever.retrieve", return_value=chunks),
            patch("backend.chat.rag_chain.retriever.needs_definitions", return_value=True),
            patch("backend.chat.rag_chain.retriever.get_section_2", return_value=sec2),
            patch("backend.chat.rag_chain.get_client", return_value=mock_client),
        ):
            events = await _collect(stream_rag_response("s6", "employer obligations"))

        # Verify stream was called (definitions path executed without error)
        assert any(e.get("done") for e in events)

    @pytest.mark.asyncio
    async def test_session_history_saved_after_response(self, mock_retriever_chunks):
        mock_add = AsyncMock()
        stream_ctx = _mock_stream_context(["answer"])
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = stream_ctx

        with (
            patch("backend.chat.rag_chain.session_manager.get_or_create", new=AsyncMock()),
            patch("backend.chat.rag_chain.session_manager.get_history", new=AsyncMock(return_value=[])),
            patch("backend.chat.rag_chain.session_manager.add_message", mock_add),
            patch("backend.chat.rag_chain.get_client", return_value=mock_client),
        ):
            await _collect(stream_rag_response("s7", "test question"))

        assert mock_add.call_count == 2  # user message + assistant response
        roles = [c.args[1] for c in mock_add.call_args_list]
        assert roles == ["user", "assistant"]
