"""
Tests for backend.chat.token_budget — token counting and budget allocation.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.chat.token_budget import (
    BudgetAllocation,
    TokenBudget,
    count_tokens,
    estimate_tokens_local,
    truncate_to_budget,
)


# ── TokenBudget.allocate ─────────────────────────────────────────────────────


class TestTokenBudgetAllocate:
    def test_allocate_basic(self):
        budget = TokenBudget(context_window=200_000, max_output=4_096, history_ratio=0.4)
        alloc = budget.allocate(used_tokens=10_000)
        remaining = 200_000 - 4_096 - 10_000
        assert alloc.history_budget == int(remaining * 0.4)
        assert alloc.context_budget == remaining - int(remaining * 0.4)

    def test_allocate_never_negative(self):
        budget = TokenBudget(context_window=200_000, max_output=4_096)
        alloc = budget.allocate(used_tokens=300_000)  # exceeds max_input
        assert alloc.history_budget >= 0
        assert alloc.context_budget >= 0

    def test_allocate_zero_used(self):
        budget = TokenBudget(context_window=100_000, max_output=2_000, history_ratio=0.5)
        alloc = budget.allocate(used_tokens=0)
        assert alloc.history_budget == 49_000
        assert alloc.context_budget == 49_000


# ── estimate_tokens_local ────────────────────────────────────────────────────


class TestEstimateTokensLocal:
    def test_empty_string(self):
        assert estimate_tokens_local("") == 0

    def test_nonempty_returns_positive(self):
        count = estimate_tokens_local("Hello, how can I help you today?")
        assert count > 0

    def test_longer_text_more_tokens(self):
        short = estimate_tokens_local("Hi")
        long = estimate_tokens_local("Hello, this is a much longer piece of text that should produce more tokens.")
        assert long > short


# ── count_tokens (API + fallback) ────────────────────────────────────────────


class TestCountTokens:
    @pytest.mark.asyncio
    async def test_uses_anthropic_api_when_available(self):
        mock_result = MagicMock()
        mock_result.input_tokens = 1234

        mock_client = AsyncMock()
        mock_client.beta.messages.count_tokens = AsyncMock(return_value=mock_result)

        result = await count_tokens(
            client=mock_client,
            messages=[{"role": "user", "content": "Hello"}],
            system="You are helpful.",
        )
        assert result == 1234
        mock_client.beta.messages.count_tokens.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_tiktoken_on_api_error(self):
        mock_client = AsyncMock()
        mock_client.beta.messages.count_tokens = AsyncMock(side_effect=Exception("API down"))

        result = await count_tokens(
            client=mock_client,
            messages=[{"role": "user", "content": "Hello world"}],
            system="You are helpful.",
        )
        # Should return a positive number from tiktoken fallback
        assert result > 0

    @pytest.mark.asyncio
    async def test_fallback_includes_safety_margin(self):
        """Fallback should overestimate by ~15%."""
        mock_client = AsyncMock()
        mock_client.beta.messages.count_tokens = AsyncMock(side_effect=Exception("API down"))

        text = "Hello world this is a test message."
        result = await count_tokens(
            client=mock_client,
            messages=[{"role": "user", "content": text}],
            system="System prompt.",
        )
        raw = estimate_tokens_local(f"System prompt. {text}")
        # Result should be higher than raw (due to 15% margin)
        assert result >= raw

    @pytest.mark.asyncio
    async def test_count_tokens_with_tools(self):
        mock_result = MagicMock()
        mock_result.input_tokens = 5678

        mock_client = AsyncMock()
        mock_client.beta.messages.count_tokens = AsyncMock(return_value=mock_result)

        tools = [{"name": "search", "description": "Search docs", "input_schema": {"type": "object", "properties": {}}}]
        result = await count_tokens(
            client=mock_client,
            messages=[{"role": "user", "content": "Find leave info"}],
            system="You are helpful.",
            tools=tools,
        )
        assert result == 5678
        # Verify tools were passed
        call_kwargs = mock_client.beta.messages.count_tokens.call_args[1]
        assert "tools" in call_kwargs


# ── truncate_to_budget ───────────────────────────────────────────────────────


class TestTruncateToBudget:
    def test_within_budget_no_truncation(self):
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        result = truncate_to_budget(messages, budget=10_000)
        assert len(result) == 2

    def test_over_budget_removes_oldest(self):
        messages = [
            {"role": "user", "content": "A" * 1000},
            {"role": "assistant", "content": "B" * 1000},
            {"role": "user", "content": "C" * 10},
            {"role": "assistant", "content": "D" * 10},
        ]
        result = truncate_to_budget(messages, budget=50)
        # Should have removed older messages, keeping at least 1
        assert len(result) < 4
        assert len(result) >= 1
        # Last message should be preserved
        assert result[-1]["content"] == "D" * 10

    def test_empty_messages(self):
        assert truncate_to_budget([], budget=100) == []

    def test_preserves_at_least_one_message(self):
        messages = [{"role": "user", "content": "A" * 10000}]
        result = truncate_to_budget(messages, budget=1)
        assert len(result) == 1
