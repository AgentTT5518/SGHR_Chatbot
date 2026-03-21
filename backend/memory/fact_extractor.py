"""
Profile fact extractor — uses Haiku to extract employment facts from conversation.

Best-effort: returns empty dict on failure (never blocks the main flow).
"""
from __future__ import annotations

import json

import anthropic

from backend.config import settings
from backend.lib.logger import get_logger

log = get_logger("memory.fact_extractor")


async def extract_profile_facts(
    messages: list[dict],
    client: anthropic.AsyncAnthropic,
) -> dict:
    """
    Call Haiku to extract employment profile facts from conversation messages.

    Returns a dict with any of: employment_type, salary_bracket, tenure_years,
    company, topics. Returns empty dict on failure.
    """
    # Take last 10 messages to keep prompt short
    recent = messages[-10:] if len(messages) > 10 else messages
    conversation_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in recent
        if isinstance(m.get("content"), str)
    )

    if not conversation_text.strip():
        return {}

    try:
        response = await client.messages.create(
            model=settings.haiku_model,
            max_tokens=200,
            system=(
                "Extract employment profile facts from this HR conversation as JSON. "
                "Fields: employment_type (e.g. 'full-time', 'part-time', 'contract'), "
                "salary_bracket (e.g. '$3000-$4000'), tenure_years (numeric), "
                "company (employer name), topics (list of HR topics discussed). "
                "Return ONLY a JSON object. Only include fields explicitly mentioned. "
                "If a field is not mentioned, omit it entirely."
            ),
            messages=[{"role": "user", "content": conversation_text}],
        )
        block = response.content[0]
        text = (block.text if hasattr(block, "text") else str(block)).strip()
        facts = json.loads(text)
        if isinstance(facts, dict):
            log.info("Extracted profile facts", extra={"fields": list(facts.keys())})
            return facts
        return {}
    except json.JSONDecodeError:
        log.warning("Haiku returned non-JSON for profile fact extraction")
        return {}
    except Exception:
        log.error("Failed to extract profile facts via Haiku", exc_info=True)
        return {}
