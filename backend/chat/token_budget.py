"""
Token counting and budget enforcement for Claude context window management.

Uses Anthropic's count_tokens API for accuracy, with tiktoken fallback.
"""
from __future__ import annotations

from dataclasses import dataclass

import anthropic

from backend.config import settings
from backend.lib.logger import get_logger

log = get_logger(__name__)

# Lazy-loaded tiktoken encoding (fallback only)
_tiktoken_enc = None


def _get_tiktoken_enc():
    """Lazy-load tiktoken encoding for fallback token counting."""
    global _tiktoken_enc
    if _tiktoken_enc is None:
        import tiktoken
        _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
    return _tiktoken_enc


@dataclass
class BudgetAllocation:
    """How many tokens are available for history and retrieval context."""
    history_budget: int
    context_budget: int


class TokenBudget:
    """Manages token budget allocation for Claude API calls."""

    def __init__(
        self,
        context_window: int | None = None,
        max_output: int | None = None,
        history_ratio: float | None = None,
    ):
        self.context_window = context_window or settings.context_window
        self.max_output = max_output or settings.max_output_tokens
        self.max_input = self.context_window - self.max_output
        self.history_ratio = history_ratio or settings.history_budget_ratio

    def allocate(self, used_tokens: int) -> BudgetAllocation:
        """
        Given tokens already used (system prompt, tools, user message),
        return how many tokens are available for history and retrieval context.
        """
        remaining = max(0, self.max_input - used_tokens)
        history_budget = int(remaining * self.history_ratio)
        context_budget = remaining - history_budget
        return BudgetAllocation(
            history_budget=history_budget,
            context_budget=context_budget,
        )


def estimate_tokens_local(text: str) -> int:
    """Estimate token count using tiktoken cl100k_base (local, fast, approximate)."""
    enc = _get_tiktoken_enc()
    return len(enc.encode(text))


async def count_tokens(
    client: anthropic.AsyncAnthropic,
    messages: list[dict],
    system: str,
    tools: list[dict] | None = None,
) -> int:
    """
    Count tokens using Anthropic's API (accurate).
    Falls back to tiktoken with 15% safety margin on API failure.
    """
    try:
        kwargs: dict = {
            "model": settings.claude_model,
            "messages": messages,
            "system": system,
        }
        if tools:
            kwargs["tools"] = tools
        result = await client.beta.messages.count_tokens(**kwargs)
        return result.input_tokens
    except Exception:
        log.error("Anthropic count_tokens API failed, falling back to tiktoken", exc_info=True)
        return _fallback_count(messages, system, tools)


def _fallback_count(
    messages: list[dict],
    system: str,
    tools: list[dict] | None = None,
) -> int:
    """Tiktoken fallback with 15% safety margin (overestimates to be safe)."""
    import json

    parts = [system]
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            # Handle content blocks
            for block in content:
                if isinstance(block, dict):
                    parts.append(block.get("text", str(block)))
                else:
                    parts.append(str(block))
        else:
            parts.append(str(content))
    if tools:
        parts.append(json.dumps(tools))

    raw_estimate = estimate_tokens_local(" ".join(parts))
    # Add 15% safety margin (overestimate to avoid exceeding limit)
    return int(raw_estimate * 1.15)


def truncate_to_budget(messages: list[dict], budget: int) -> list[dict]:
    """
    Trim oldest messages first to fit within token budget.
    Always preserves at least the last message.
    """
    if not messages:
        return messages

    total = sum(estimate_tokens_local(m.get("content", "") if isinstance(m.get("content"), str) else str(m.get("content", ""))) for m in messages)
    if total <= budget:
        return messages

    # Remove from the front (oldest) until we fit
    result = list(messages)
    while len(result) > 1:
        removed = result.pop(0)
        removed_tokens = estimate_tokens_local(
            removed.get("content", "") if isinstance(removed.get("content"), str) else str(removed.get("content", ""))
        )
        total -= removed_tokens
        if total <= budget:
            break

    return result
