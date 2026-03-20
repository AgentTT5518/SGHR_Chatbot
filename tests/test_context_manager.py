"""
Tests for backend.chat.context_manager — SummaryBuffer, context assembly, fact extraction.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from backend.chat import session_manager
from backend.chat.context_manager import (
    SessionContext,
    build_context,
    extract_facts,
    format_context_for_prompt,
    generate_summary,
    maybe_update_summary,
)


@pytest_asyncio.fixture(autouse=True)
async def fresh_db(tmp_path):
    """Point session_manager at a temp DB for each test."""
    db_path = str(tmp_path / "test_sessions.db")
    with patch.object(session_manager, "DB_PATH", db_path):
        await session_manager.init_db()
        yield


def _make_haiku_response(text: str) -> MagicMock:
    """Create a mock Anthropic response object."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


# ── build_context ─────────────────────────────────────────────────────────────


class TestBuildContext:
    @pytest.mark.asyncio
    async def test_empty_session_returns_empty_context(self):
        await session_manager.get_or_create("empty-sess")
        ctx = await build_context("empty-sess", history_budget=10_000)
        assert ctx.recent_messages == []
        assert ctx.summary == ""

    @pytest.mark.asyncio
    async def test_short_conversation_no_summary(self):
        """Conversations within budget should return all messages verbatim."""
        await session_manager.get_or_create("short-sess")
        await session_manager.add_message("short-sess", "user", "What is annual leave?")
        await session_manager.add_message("short-sess", "assistant", "Annual leave is 7-14 days.")

        ctx = await build_context("short-sess", history_budget=10_000)
        assert len(ctx.recent_messages) == 2
        assert ctx.recent_messages[0]["role"] == "user"
        assert ctx.recent_messages[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_long_conversation_triggers_summary(self):
        """When history exceeds budget, older messages should be summarized."""
        await session_manager.get_or_create("long-sess")
        # Add 10 pairs (20 messages) with substantial content
        for i in range(10):
            await session_manager.add_message("long-sess", "user", f"Question {i}: " + "x" * 200)
            await session_manager.add_message("long-sess", "assistant", f"Answer {i}: " + "y" * 200)

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_make_haiku_response("Summary: User asked 10 questions about employment.")
        )

        # Use a tight budget that forces summarization
        ctx = await build_context("long-sess", history_budget=300, client=mock_client)

        # Should have fewer messages than the full 20
        assert len(ctx.recent_messages) <= 6  # at most 3 pairs
        # Haiku should have been called (for summary and/or facts)
        assert mock_client.messages.create.await_count >= 1

    @pytest.mark.asyncio
    async def test_build_context_without_client_uses_existing_summary(self):
        """Without a client, should use existing summary from DB."""
        await session_manager.get_or_create("existing-sum")
        await session_manager.update_summary("existing-sum", "Previous summary content.")
        for i in range(10):
            await session_manager.add_message("existing-sum", "user", f"Q{i}: " + "z" * 200)
            await session_manager.add_message("existing-sum", "assistant", f"A{i}: " + "w" * 200)

        ctx = await build_context("existing-sum", history_budget=300, client=None)
        assert ctx.summary == "Previous summary content."


# ── generate_summary ──────────────────────────────────────────────────────────


class TestGenerateSummary:
    @pytest.mark.asyncio
    async def test_generates_summary_for_long_conversation(self):
        messages = [
            {"role": "user", "content": f"Question {i}"} for i in range(8)
        ]
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_make_haiku_response("User asked 8 questions about HR topics.")
        )

        result = await generate_summary(messages, mock_client)
        assert result == "User asked 8 questions about HR topics."

    @pytest.mark.asyncio
    async def test_skips_short_conversation(self):
        """Conversations with < 6 messages should not be summarized."""
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        mock_client = AsyncMock()
        result = await generate_summary(messages, mock_client)
        assert result is None
        mock_client.messages.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_none_on_api_failure(self):
        messages = [{"role": "user", "content": f"Q{i}"} for i in range(8)]
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("Haiku down"))

        result = await generate_summary(messages, mock_client)
        assert result is None

    @pytest.mark.asyncio
    async def test_incorporates_existing_summary(self):
        messages = [{"role": "user", "content": f"Q{i}"} for i in range(8)]
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_make_haiku_response("Updated summary.")
        )

        result = await generate_summary(messages, mock_client, existing_summary="Old summary.")
        assert result == "Updated summary."
        # Verify existing summary was included in the prompt
        call_args = mock_client.messages.create.call_args
        prompt_content = call_args[1]["messages"][0]["content"]
        assert "Old summary." in prompt_content


# ── extract_facts ─────────────────────────────────────────────────────────────


class TestExtractFacts:
    @pytest.mark.asyncio
    async def test_extracts_valid_facts(self):
        messages = [
            {"role": "user", "content": "I'm a full-time employee with 3 years tenure."},
            {"role": "assistant", "content": "Based on your tenure..."},
        ]
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_make_haiku_response('{"employment_type": "full-time", "tenure_years": 3}')
        )

        result = await extract_facts(messages, mock_client)
        assert result == {"employment_type": "full-time", "tenure_years": 3}

    @pytest.mark.asyncio
    async def test_returns_none_on_invalid_json(self):
        messages = [{"role": "user", "content": "Hello"}]
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_make_haiku_response("Not valid JSON at all")
        )

        result = await extract_facts(messages, mock_client)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_api_failure(self):
        messages = [{"role": "user", "content": "Hello"}]
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("API error"))

        result = await extract_facts(messages, mock_client)
        assert result is None


# ── format_context_for_prompt ─────────────────────────────────────────────────


class TestFormatContextForPrompt:
    def test_no_summary_no_facts(self):
        ctx = SessionContext(
            summary="",
            facts={},
            recent_messages=[{"role": "user", "content": "Hi"}],
        )
        block, messages = format_context_for_prompt(ctx)
        assert block == ""
        assert len(messages) == 1

    def test_with_summary(self):
        ctx = SessionContext(
            summary="User asked about annual leave.",
            facts={},
            recent_messages=[{"role": "user", "content": "Follow-up question"}],
        )
        block, messages = format_context_for_prompt(ctx)
        assert "CONVERSATION CONTEXT" in block
        assert "User asked about annual leave." in block
        assert len(messages) == 1

    def test_with_summary_and_facts(self):
        ctx = SessionContext(
            summary="Discussed leave policies.",
            facts={"employment_type": "full-time", "tenure_years": 5},
            recent_messages=[],
        )
        block, messages = format_context_for_prompt(ctx)
        assert "CONVERSATION CONTEXT" in block
        assert "Known facts" in block
        assert "full-time" in block
        assert "5" in block

    def test_facts_only_no_summary(self):
        ctx = SessionContext(
            summary="",
            facts={"employment_type": "part-time"},
            recent_messages=[],
        )
        block, messages = format_context_for_prompt(ctx)
        assert "Known facts" in block
        assert "part-time" in block


# ── maybe_update_summary ─────────────────────────────────────────────────────


class TestMaybeUpdateSummary:
    @pytest.mark.asyncio
    async def test_skips_short_conversation(self):
        """Should not attempt summary for conversations with <= 6 messages."""
        await session_manager.get_or_create("short-maybe")
        await session_manager.add_message("short-maybe", "user", "Hi")
        await session_manager.add_message("short-maybe", "assistant", "Hello!")

        mock_client = AsyncMock()
        await maybe_update_summary("short-maybe", mock_client)
        mock_client.messages.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_triggers_for_long_conversation(self):
        """Should attempt summary for conversations with > 6 messages."""
        await session_manager.get_or_create("long-maybe")
        for i in range(5):
            await session_manager.add_message("long-maybe", "user", f"Question {i} " + "x" * 50)
            await session_manager.add_message("long-maybe", "assistant", f"Answer {i} " + "y" * 50)

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_make_haiku_response("Summary of conversation.")
        )

        await maybe_update_summary("long-maybe", mock_client)
        # Should have called Haiku at least once
        assert mock_client.messages.create.await_count >= 1

    @pytest.mark.asyncio
    async def test_handles_api_failure_gracefully(self):
        """Should not raise even if Haiku fails."""
        await session_manager.get_or_create("fail-maybe")
        for i in range(5):
            await session_manager.add_message("fail-maybe", "user", f"Q{i}")
            await session_manager.add_message("fail-maybe", "assistant", f"A{i}")

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("Haiku down"))

        # Should not raise
        await maybe_update_summary("fail-maybe", mock_client)
