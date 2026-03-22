"""
Query expander — uses Haiku to generate alternative phrasings of a user query.

Best-effort: returns [original_query] on failure (never blocks retrieval).
"""
from __future__ import annotations

import anthropic

from backend.config import settings
from backend.lib.logger import get_logger

log = get_logger("retrieval.query_expander")

_EXPANSION_PROMPT = (
    "Generate {count} alternative phrasings of this HR query. "
    "Cover Singapore employment terminology synonyms "
    "(e.g. 'annual leave' ↔ 'vacation' ↔ 'PTO', 'termination' ↔ 'dismissal'). "
    "Return ONLY the rephrasings, one per line. No numbering, no explanations."
)


async def expand(query: str) -> list[str]:
    """
    Generate query rephrasings via Haiku for multi-query retrieval.

    Returns [original_query, rephrasing1, rephrasing2, ...].
    On any error, returns [original_query] (best-effort).
    """
    if not settings.use_query_expansion:
        return [query]

    count = settings.query_expansion_count
    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=settings.haiku_model,
            max_tokens=200,
            system=_EXPANSION_PROMPT.format(count=count),
            messages=[{"role": "user", "content": query}],
        )
        block = response.content[0]
        text = block.text if hasattr(block, "text") else str(block)

        rephrasings = [
            line.strip() for line in text.strip().splitlines()
            if line.strip()
        ]

        if not rephrasings:
            log.warning("Haiku returned no rephrasings, using original query only")
            return [query]

        # Cap to requested count
        rephrasings = rephrasings[:count]
        result = [query] + rephrasings
        log.info(
            "Query expanded",
            extra={"original": query, "expansion_count": len(rephrasings)},
        )
        return result

    except Exception:
        log.error("Query expansion failed, using original query only", exc_info=True)
        return [query]
