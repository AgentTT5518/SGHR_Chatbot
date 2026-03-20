"""
Context manager with SummaryBuffer for conversation history.

Replaces raw sliding-window history with a tiered approach:
- Recent messages: last N pairs verbatim
- Summary: older messages compressed via Haiku
- Facts: extracted entities stored per-session

Summary is injected via system prompt appendix, NOT as fake messages.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic

from backend.chat import session_manager
from backend.chat.token_budget import estimate_tokens_local, truncate_to_budget
from backend.config import settings
from backend.lib.logger import get_logger

log = get_logger(__name__)


@dataclass
class SessionContext:
    """Assembled context for a conversation turn."""
    summary: str = ""
    facts: dict = field(default_factory=dict)
    recent_messages: list[dict] = field(default_factory=list)
    token_count: int = 0


async def build_context(
    session_id: str,
    history_budget: int,
    client: anthropic.AsyncAnthropic | None = None,
) -> SessionContext:
    """
    Build conversation context that fits within the token budget.

    - If total history fits in budget: return all messages verbatim.
    - If it exceeds budget: keep last N pairs verbatim, summarize older ones.
    """
    # Get existing context metadata
    ctx_data = await session_manager.get_session_context(session_id)
    existing_summary = ctx_data["summary"]
    existing_facts = ctx_data["facts"]

    # Fetch all messages
    all_messages = await session_manager.get_history(session_id, last_n_pairs=None)

    if not all_messages:
        return SessionContext(
            summary=existing_summary,
            facts=existing_facts,
            recent_messages=[],
            token_count=_estimate_context_tokens(existing_summary, []),
        )

    # Estimate total token cost of all messages
    total_tokens = sum(
        estimate_tokens_local(m.get("content", ""))
        for m in all_messages
    )

    # If everything fits, return all messages verbatim
    if total_tokens <= history_budget:
        return SessionContext(
            summary=existing_summary,
            facts=existing_facts,
            recent_messages=all_messages,
            token_count=_estimate_context_tokens(existing_summary, all_messages),
        )

    # Split: keep last N pairs verbatim, summarize older ones
    recent_count = settings.summary_recent_pairs * 2  # pairs → messages
    if len(all_messages) <= recent_count:
        # Not enough messages to split — just truncate to budget
        truncated = truncate_to_budget(all_messages, history_budget)
        return SessionContext(
            summary=existing_summary,
            facts=existing_facts,
            recent_messages=truncated,
            token_count=_estimate_context_tokens(existing_summary, truncated),
        )

    recent_messages = all_messages[-recent_count:]
    older_messages = all_messages[:-recent_count]

    # Generate summary of older messages (best-effort via Haiku)
    summary = existing_summary
    if client and older_messages:
        new_summary = await generate_summary(older_messages, client, existing_summary)
        if new_summary:
            summary = new_summary
            await session_manager.update_summary(session_id, summary)

        # Extract facts (best-effort)
        new_facts = await extract_facts(older_messages + recent_messages, client)
        if new_facts:
            existing_facts.update({k: v for k, v in new_facts.items() if v is not None and v != ""})
            await session_manager.update_session_facts(session_id, existing_facts)

    # Ensure recent messages fit in remaining budget after summary
    summary_tokens = estimate_tokens_local(summary) if summary else 0
    remaining_budget = max(0, history_budget - summary_tokens)
    recent_messages = truncate_to_budget(recent_messages, remaining_budget)

    return SessionContext(
        summary=summary,
        facts=existing_facts,
        recent_messages=recent_messages,
        token_count=_estimate_context_tokens(summary, recent_messages),
    )


async def generate_summary(
    messages: list[dict],
    client: anthropic.AsyncAnthropic,
    existing_summary: str = "",
) -> str | None:
    """
    Summarize older conversation messages using Haiku.
    Best-effort: returns None on failure.
    """
    # Only summarize if there are enough messages (> 3 pairs = 6 messages)
    if len(messages) < 6:
        return None

    conversation_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )

    prompt_parts = []
    if existing_summary:
        prompt_parts.append(f"Previous summary:\n{existing_summary}\n\nNew messages to incorporate:")
    prompt_parts.append(conversation_text)

    try:
        response = await client.messages.create(
            model=settings.haiku_model,
            max_tokens=300,
            system=(
                "Summarize this HR conversation concisely. Preserve: employee details, "
                "specific questions asked, answers given, any legal provisions or EA sections cited. "
                "Keep to 100-200 words."
            ),
            messages=[{"role": "user", "content": "\n".join(prompt_parts)}],
        )
        block = response.content[0]
        summary = (block.text if hasattr(block, "text") else str(block)).strip()
        log.info("Generated session summary", extra={"length": len(summary)})
        return summary
    except Exception:
        log.error("Failed to generate summary via Haiku", exc_info=True)
        return None


async def extract_facts(
    messages: list[dict],
    client: anthropic.AsyncAnthropic,
) -> dict | None:
    """
    Extract key facts from conversation using Haiku.
    Best-effort: returns None on failure.
    """
    conversation_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages[-10:]  # last 10 messages max
    )

    try:
        response = await client.messages.create(
            model=settings.haiku_model,
            max_tokens=200,
            system=(
                "Extract key facts from this HR conversation as JSON. "
                "Fields: employment_type, salary_range, tenure_years, company, specific_situation. "
                "Return ONLY a JSON object. Only include fields explicitly mentioned in the conversation. "
                "If a field is not mentioned, omit it."
            ),
            messages=[{"role": "user", "content": conversation_text}],
        )
        block = response.content[0]
        text = (block.text if hasattr(block, "text") else str(block)).strip()
        # Try to parse JSON from response
        facts = json.loads(text)
        if isinstance(facts, dict):
            log.info("Extracted session facts", extra={"fields": list(facts.keys())})
            return facts
        return None
    except json.JSONDecodeError:
        log.warning("Haiku returned non-JSON for fact extraction")
        return None
    except Exception:
        log.error("Failed to extract facts via Haiku", exc_info=True)
        return None


def format_context_for_prompt(ctx: SessionContext) -> tuple[str, list[dict]]:
    """
    Format session context for injection into the Claude API call.

    Returns:
        (summary_system_block, recent_messages)
        - summary_system_block: appended to system prompt (empty string if no summary)
        - recent_messages: verbatim messages for the messages parameter
    """
    parts = []
    if ctx.summary:
        parts.append(f"\n\nCONVERSATION CONTEXT:\n{ctx.summary}")
    if ctx.facts:
        facts_str = ", ".join(f"{k}: {v}" for k, v in ctx.facts.items() if v)
        if facts_str:
            parts.append(f"\nKnown facts about this user: {facts_str}")

    summary_block = "".join(parts)
    return summary_block, ctx.recent_messages


async def maybe_update_summary(
    session_id: str,
    client: anthropic.AsyncAnthropic,
) -> None:
    """
    Conditionally update the session summary.
    Called async after response completes — non-blocking.
    Only triggers when message count > 3 pairs (6 messages).
    """
    try:
        ctx_data = await session_manager.get_session_context(session_id)
        if ctx_data["message_count"] <= 6:
            return  # Short conversation, no summary needed

        all_messages = await session_manager.get_history(session_id, last_n_pairs=None)
        recent_count = settings.summary_recent_pairs * 2
        if len(all_messages) <= recent_count:
            return

        older_messages = all_messages[:-recent_count]
        summary = await generate_summary(older_messages, client, ctx_data["summary"])
        if summary:
            await session_manager.update_summary(session_id, summary)

        facts = await extract_facts(all_messages, client)
        if facts:
            await session_manager.update_session_facts(session_id, facts)
    except Exception:
        log.error("Failed to update session summary", exc_info=True)


def _estimate_context_tokens(summary: str, messages: list[dict]) -> int:
    """Estimate total token count for summary + messages."""
    total = estimate_tokens_local(summary) if summary else 0
    total += sum(estimate_tokens_local(m.get("content", "")) for m in messages)
    return total
