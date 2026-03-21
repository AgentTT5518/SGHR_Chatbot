"""
Agentic orchestration loop: Claude decides which tools to use, streams final answer.

Replaces the static RAG pipeline with a tool-use loop. Claude receives tool
schemas, decides when to call them, and the orchestrator dispatches calls and
feeds results back until Claude produces a text-only response.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

import anthropic

from backend.chat import context_manager, session_manager
from backend.chat.prompts import build_system_prompt
from backend.chat.token_budget import TokenBudget, count_tokens
from backend.chat.tools.registry import dispatch_tool, get_all_schemas, register_all_tools
from backend.config import settings
from backend.lib.logger import get_logger

log = get_logger("chat.orchestrator")

_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


FALLBACK_MAX_ITERATIONS = (
    "I've done extensive research but couldn't fully resolve your question. "
    "Here's what I found so far — please consult MOM at www.mom.gov.sg or "
    "call 6438 5122 for further assistance."
)

_DISPLAY_NAMES: dict[str, str] = {
    "search_employment_act": "Searching Employment Act...",
    "search_mom_guidelines": "Searching MOM guidelines...",
    "search_all_policies": "Searching all policies...",
    "get_legal_definitions": "Looking up legal definitions...",
    "calculate_leave_entitlement": "Calculating leave entitlement...",
    "calculate_notice_period": "Calculating notice period...",
    "check_eligibility": "Checking eligibility...",
    "escalate_to_hr": "Escalating to HR...",
}


def _tool_display_name(name: str) -> str:
    """Map a tool name to a user-friendly status label."""
    return _DISPLAY_NAMES.get(name, f"Using {name}...")


def _extract_sources_from_tool_results(messages: list[dict]) -> list[dict]:
    """Scan tool result messages for source citations.

    Tool results from retrieval tools contain lines like:
        Source: Employment Act, Part IV, s 38
        URL: https://www.mom.gov.sg/...
    Parse these to build a sources list for the frontend.
    """
    sources: list[dict] = []
    seen: set[str] = set()

    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            text = block.get("content", "")
            if not isinstance(text, str):
                continue
            # Parse source lines from tool output
            current_label = ""
            current_url = ""
            for line in text.split("\n"):
                stripped = line.strip()
                if stripped.startswith("Source:"):
                    # Flush previous source if any
                    if current_label and current_label not in seen:
                        seen.add(current_label)
                        sources.append({"label": current_label, "url": current_url})
                    current_label = stripped[len("Source:"):].strip()
                    current_url = ""
                elif stripped.startswith("URL:"):
                    current_url = stripped[len("URL:"):].strip()
            # Flush last source
            if current_label and current_label not in seen:
                seen.add(current_label)
                sources.append({"label": current_label, "url": current_url})

    return sources


async def orchestrate(
    session_id: str,
    user_id: str,
    user_message: str,
    user_role: str = "employee",
) -> AsyncGenerator[str, None]:
    """Agentic loop: Claude decides which tools to use, streams final answer.

    Uses streaming for ALL iterations. Parses the stream to detect tool_use
    blocks. If tool_use is found, collects the full response, dispatches tools,
    and loops. If it's a text-only response, streams tokens through to the client.
    """
    # 1. Load context
    await session_manager.get_or_create(session_id, user_id=user_id)
    system_prompt = build_system_prompt(context=None, user_role=user_role)
    client = get_client()

    # Ensure tools are registered
    register_all_tools()

    tools = get_all_schemas()

    # Allocate token budget for history
    budget = TokenBudget()
    base_tokens = await count_tokens(
        client, [{"role": "user", "content": user_message}], system_prompt, tools
    )
    alloc = budget.allocate(base_tokens)

    # Build context with summary buffer
    session_ctx = await context_manager.build_context(
        session_id, alloc.history_budget, client=client
    )
    summary_block, recent_messages = context_manager.format_context_for_prompt(session_ctx)
    if summary_block:
        system_prompt += summary_block
    messages: list[dict] = recent_messages + [{"role": "user", "content": user_message}]

    # 2. Agentic loop — streaming throughout
    max_iterations = settings.max_tool_iterations

    for iteration in range(max_iterations):
        log.info(
            "Orchestrator iteration",
            extra={"iteration": iteration, "session_id": session_id},
        )

        collected_content: list = []
        has_tool_use = False

        try:
            async with client.messages.stream(
                model=settings.claude_model,
                max_tokens=settings.max_output_tokens,
                system=system_prompt,
                tools=tools,
                messages=messages,
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_start":
                        if event.content_block.type == "tool_use":
                            has_tool_use = True
                    elif event.type == "text" and not has_tool_use:
                        # Stream text tokens directly to client
                        yield _sse({"token": event.text, "done": False})

                # Get the final message with all content blocks
                response = await stream.get_final_message()
                collected_content = list(response.content)

        except anthropic.APIError as e:
            log.error("Claude API error during orchestration", exc_info=True)
            yield _sse({"error": f"API error: {e.message}", "done": True, "sources": []})
            return
        except Exception as e:
            log.error("Unexpected error during orchestration", exc_info=True)
            yield _sse({"error": f"Unexpected error: {str(e)}", "done": True, "sources": []})
            return

        if has_tool_use:
            # Tool use detected — collect tool blocks, dispatch, loop back
            tool_blocks = [b for b in collected_content if b.type == "tool_use"]
            messages.append({"role": "assistant", "content": collected_content})

            tool_results: list[dict] = []
            for block in tool_blocks:
                yield _sse({"status": "thinking", "detail": _tool_display_name(block.name)})
                try:
                    result = await dispatch_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
                except Exception as e:
                    log.error(f"Tool {block.name} failed", exc_info=True)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Error: {str(e)}",
                        "is_error": True,
                    })

            messages.append({"role": "user", "content": tool_results})
            continue  # loop back — Claude reflects on tool results

        else:
            # Text-only response — already streamed to client above
            full_response = "".join(
                b.text for b in collected_content if hasattr(b, "text")
            )

            sources = _extract_sources_from_tool_results(messages)
            yield _sse({"token": "", "done": True, "sources": sources})

            # Persist conversation turn
            await session_manager.add_message(session_id, "user", user_message)
            await session_manager.add_message(session_id, "assistant", full_response)

            # Trigger async summary update (non-blocking)
            asyncio.create_task(context_manager.maybe_update_summary(session_id, client))
            return

    # Max iterations reached — fallback
    log.warning(
        "Max tool iterations reached",
        extra={"session_id": session_id, "max": max_iterations},
    )
    yield _sse({"token": FALLBACK_MAX_ITERATIONS, "done": True, "sources": []})
    await session_manager.add_message(session_id, "user", user_message)
    await session_manager.add_message(session_id, "assistant", FALLBACK_MAX_ITERATIONS)
