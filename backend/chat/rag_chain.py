"""
RAG chain: retrieves context, builds prompt, streams Claude's response.
"""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import anthropic

from backend.config import settings
from backend.chat import session_manager
from backend.chat.prompts import build_system_prompt, format_context, extract_sources
from backend.retrieval import retriever

_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


FALLBACK_MESSAGE = (
    "I couldn't find relevant information in the Employment Act or MOM guidelines "
    "for your question. For accurate guidance, please:\n"
    "- Visit **www.mom.gov.sg** directly\n"
    "- Call MOM at **6438 5122** (Mon–Fri, 8:30am–5:30pm)\n"
    "- Consult a Singapore employment lawyer for specific legal advice"
)


async def stream_rag_response(
    session_id: str,
    user_message: str,
    user_role: str = "employee",
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE-formatted strings.
    Each yield is a data: {...} line.
    Final yield includes {"done": true, "sources": [...]}.
    """
    # Ensure session exists
    await session_manager.get_or_create(session_id)

    # 1. Retrieve relevant chunks
    chunks = retriever.retrieve(user_message)

    # 2. Conditionally prepend Section 2 (Definitions)
    if retriever.needs_definitions(user_message, chunks):
        sec2 = retriever.get_section_2()
        if sec2:
            chunks = [sec2] + chunks

    # 3. Zero-results guard
    if not chunks:
        yield _sse({"token": FALLBACK_MESSAGE, "done": True, "sources": []})
        # Still save the exchange so history is coherent
        await session_manager.add_message(session_id, "user", user_message)
        await session_manager.add_message(session_id, "assistant", FALLBACK_MESSAGE)
        return

    # 4. Build prompt + history
    context = format_context(chunks)
    system_prompt = build_system_prompt(context, user_role)
    history = await session_manager.get_history(session_id)
    messages = history + [{"role": "user", "content": user_message}]

    # 5. Stream Claude response
    full_response = ""
    client = get_client()
    try:
        async with client.messages.stream(
            model=settings.claude_model,
            max_tokens=settings.max_tokens,
            system=system_prompt,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                full_response += text
                yield _sse({"token": text, "done": False})
    except anthropic.APIError as e:
        error_msg = f"I encountered an error while generating a response: {e.message}"
        yield _sse({"error": error_msg, "done": True, "sources": []})
        return
    except Exception as e:
        yield _sse({"error": f"Unexpected error: {str(e)}", "done": True, "sources": []})
        return

    # 6. Send final event with sources
    sources = extract_sources(chunks)
    yield _sse({"token": "", "done": True, "sources": sources})

    # 7. Persist conversation turn
    await session_manager.add_message(session_id, "user", user_message)
    await session_manager.add_message(session_id, "assistant", full_response)
