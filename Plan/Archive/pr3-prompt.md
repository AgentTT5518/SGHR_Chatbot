# PR 3 Session Prompt — Orchestration Loop + Frontend Status Events

Copy everything below the line into a new Claude Code session.

---

I'm implementing Phase 2, Step 2.5 of the "Enhancing Chatbot" feature plan — the Orchestration Loop that replaces the static RAG pipeline with an agentic tool-use loop.

## Setup

1. Read the full plan: `Plan/Planning/enhancing-chatbot/plan.md`
   - Focus on "Implementation Plan — Step-by-Step", Step 2.5 (lines ~598–763)
2. Read `CLAUDE.md` for project rules (especially Rules 1–5)
3. Read `ARCHITECTURE.md` for current design (just updated with Phase 2 tools)
4. Read existing code before modifying:
   - `backend/chat/rag_chain.py` — current streaming pipeline (to be replaced)
   - `backend/api/routes_chat.py` — current route (wires to rag_chain)
   - `backend/chat/prompts.py` — system prompt builder (needs simplification)
   - `backend/chat/tools/registry.py` — tool schemas + dispatch (built in PR 2)
   - `backend/chat/context_manager.py` — SummaryBuffer (built in Phase 1)
   - `backend/chat/token_budget.py` — token counting/allocation (built in Phase 1)
   - `frontend/src/api/chatApi.js` — SSE parsing
   - `frontend/src/hooks/useChat.js` — state management + reducer
   - `frontend/src/components/MessageBubble.jsx` — message rendering
5. Create a new branch: `git checkout -b feature/enhancing-chatbot-orchestrator`

## What to build

### 1. Create `backend/chat/orchestrator.py` — the agentic loop

Core function: `async def orchestrate(session_id, user_id, user_message, user_role) -> AsyncGenerator[str, None]`

The loop:
1. Load context: `get_or_create` session, build system prompt (simplified — no context block), allocate token budget, build session context via SummaryBuffer
2. Register all tools via `registry.register_all_tools()`
3. Agentic loop (max 5 iterations):
   - **Always stream** — parse stream events to detect `tool_use` blocks vs text
   - If `tool_use` detected: collect full response, dispatch tool(s), emit `{"status": "thinking", "detail": "Searching Employment Act..."}` SSE events, append tool results to messages, loop back
   - If text-only response: stream tokens directly to client via `{"token": "...", "done": false}`, then emit `{"done": true, "sources": [...]}`
   - On max iterations: emit graceful fallback message
4. After loop: persist messages, trigger async summary update
5. Helper functions:
   - `_tool_display_name(name)` — maps tool names to friendly labels (e.g. `"search_employment_act"` → `"Searching Employment Act..."`)
   - `_extract_sources_from_tool_results(messages)` — scan tool result messages for source citations to send to frontend
   - `_sse(data)` — SSE formatter (same pattern as current `rag_chain.py`)

**Key design decisions (already made — do not revisit):**
- Stream throughout ALL iterations — parse events to detect tool_use. No double API call (non-streaming check + streaming re-call).
- `status` events (`{"status": "thinking", "detail": "..."}`) emitted before each tool dispatch
- Sources extracted from tool results at the end, not from direct retrieval
- Keep `rag_chain.py` as fallback — add `use_orchestrator: bool = True` flag to `config.py`

### 2. Update `backend/chat/prompts.py`

- Simplify `build_system_prompt`: remove the `context` parameter (tools handle retrieval now)
- Keep role instructions (employee vs HR) — the `_get_role_instructions()` function stays
- Add tool-use guidance to system prompt: "You have access to tools for searching policies, calculating entitlements, and checking eligibility. Use them when needed."
- Keep `format_context()` and `extract_sources()` — still used by retrieval tools

### 3. Update `backend/api/routes_chat.py`

- Import orchestrator
- Route to `orchestrator.orchestrate()` when `settings.use_orchestrator` is True
- Fall back to `rag_chain.stream_rag_response()` when False
- Pass `user_id` from request

### 4. Add config flag to `backend/config.py`

- `use_orchestrator: bool = True`
- `max_tool_iterations: int = 5`

### 5. Frontend: handle `status` SSE events

**`frontend/src/api/chatApi.js`:**
- Currently parses: `token`, `done`, `error`
- Add parsing for `status` field — call an `onStatus` callback when received
- The `streamChat` function needs an `onStatus` parameter

**`frontend/src/hooks/useChat.js`:**
- Add `STREAM_STATUS` action to the reducer
- Store thinking steps in the message object (e.g. `message.thinkingSteps: string[]`)
- Wire `onStatus` callback from `chatApi.streamChat` into the reducer dispatch

**`frontend/src/components/MessageBubble.jsx`:**
- If `message.thinkingSteps` exists and has entries, render them as subtle status lines above the message content
- Style: muted text, smaller font, italic — they represent intermediate "thinking" steps
- While streaming, show the latest thinking step; after done, collapse or keep visible

## Key constraints from the plan

- The orchestrator uses `client.messages.stream()` for ALL iterations (never `client.messages.create()`)
- Tool results use Anthropic's expected format: `{"type": "tool_result", "tool_use_id": block.id, "content": result_string}`
- The assistant message with tool_use blocks must be appended to messages as `{"role": "assistant", "content": collected_content}` (the raw content blocks list)
- Max 5 iterations guard — emit fallback message if exceeded
- `FALLBACK_MAX_ITERATIONS` message: "I've done extensive research but couldn't fully resolve your question. Here's what I found so far..."

## Existing code to reference (not modify)

- `backend/chat/tools/registry.py` — `register_all_tools()`, `get_all_schemas()`, `dispatch_tool(name, input)`
- `backend/chat/tools/retrieval_tools.py` — returns formatted text with citations
- `backend/chat/tools/calculation_tools.py` — returns structured text with EA section refs
- `backend/chat/tools/routing_tools.py` — `escalate_to_hr` writes to SQLite
- `backend/chat/context_manager.py` — `build_context(session_id, budget, client)`, `format_context_for_prompt(ctx)`, `maybe_update_summary(session_id, client)`
- `backend/chat/token_budget.py` — `TokenBudget()`, `count_tokens(client, messages, system)`

## Testing rules

- Write tests in `tests/` mirroring the module structure (e.g. `tests/chat/test_orchestrator.py`)
- Use the project logger (`backend/lib/logger.py`), never bare `print()`
- Run tests after each step: `python -m pytest tests/ -v`
- There's a `tests/conftest.py` that mocks `SentenceTransformer` at session scope — don't remove it
- Mock the Anthropic client in orchestrator tests — simulate tool_use responses and text responses
- Test scenarios:
  1. Direct answer (no tools) — Claude responds with text only
  2. Single tool call — Claude calls one tool, then answers
  3. Multi-tool chain — Claude calls 2+ tools across iterations
  4. Max iterations reached — fallback message emitted
  5. Tool error — error handled gracefully, Claude gets error result
  6. SSE event order — status events before tool dispatch, token events during streaming, done event at end

## Scope boundaries — HARD STOP

- Do NOT modify tool implementations (`retrieval_tools.py`, `calculation_tools.py`, `routing_tools.py`) — those are done
- Do NOT modify `session_manager.py` or `vector_store.py` — those are done
- Do NOT build Phase 3 features (profile memory, semantic cache)
- Do NOT modify files outside scope without asking (CLAUDE.md Rule 5)
- The only files that should be created/modified:
  - **Create:** `backend/chat/orchestrator.py`
  - **Modify:** `backend/chat/prompts.py` (simplify for tool-use)
  - **Modify:** `backend/api/routes_chat.py` (route to orchestrator)
  - **Modify:** `backend/config.py` (add flags)
  - **Modify:** `frontend/src/api/chatApi.js` (parse status events)
  - **Modify:** `frontend/src/hooks/useChat.js` (STREAM_STATUS action)
  - **Modify:** `frontend/src/components/MessageBubble.jsx` (render thinking steps)

## Before committing

- Run full test suite: `python -m pytest tests/ -v`
- Run secret scan (CLAUDE.md Rule 1)
- Run linting: `ruff check backend/`
- Run type check: `python -m mypy backend/`
- Run frontend lint: `cd frontend && npm run lint`
- Update `ARCHITECTURE.md` Feature Log + Component Map
