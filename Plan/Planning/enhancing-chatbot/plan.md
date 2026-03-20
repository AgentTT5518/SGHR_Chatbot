# Plan: Enhancing Chatbot — Tools, Memory & Orchestration

**Status:** Planning
**Created:** 2026-03-20
**Feature Branch:** `feature/Enchancing_Chatbot`

---

## Goal / Problem Statement

The SGHR Chatbot is currently a static RAG pipeline: every query always retrieves → always sends to Claude → streams response. It has no tool use, no long-term memory, no context management beyond a raw sliding window, and no ability to calculate, route, or escalate.

This plan upgrades the chatbot across three pillars:

1. **Tool-Augmented Orchestration** — Let Claude decide when to retrieve, calculate, or escalate (replacing the static retrieve-then-generate flow)
2. **Memory System** — Session memory with compression, cross-session profile memory, and a verified Q&A cache
3. **Document Management** — Per-source retrieval tools with metadata filtering and contextual compression

### Why Not Sub-Agents?

Research (Anthropic, Microsoft, Google, LangChain benchmarks) unanimously recommends a **single agent with tools** for bounded-domain chatbots. Multi-agent adds ~15x token cost vs ~4x for single-agent, fragments context, and complicates debugging. Revisit only if tool count exceeds ~15 or fundamentally different security/domain boundaries emerge.

### Why No Framework (LangChain/LangGraph)?

Anthropic recommends building the agentic loop directly with their SDK. The loop is ~30 lines of Python. Benefits: no abstraction tax, full control over message format, native SSE streaming, no dependency churn. LangChain patterns are used as *architectural reference*, not as a runtime dependency.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│  FastAPI Route (/api/chat)                                       │
│  validate → rate-limit → session lookup                          │
└──────────────────┬───────────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  Memory Layer                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ Session Mem   │  │ Profile Mem   │  │ Semantic Mem           │ │
│  │ (summary +   │  │ (user prefs,  │  │ (verified Q&A cache,   │ │
│  │  recent msgs) │  │  emp details) │  │  FAQ patterns)         │ │
│  └──────────────┘  └──────────────┘  └────────────────────────┘ │
└──────────────────┬───────────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  Orchestration Loop (replaces rag_chain.py)                      │
│                                                                  │
│  while True:                                                     │
│    response = claude.messages.create(                            │
│      system = system_prompt + session_summary + profile_context, │
│      tools  = tool_registry,                                     │
│      messages = recent_messages + [user_message]                 │
│    )                                                             │
│    if response.stop_reason == "tool_use":                        │
│      → dispatch tool(s) → append results → loop                 │
│    else:                                                         │
│      → stream final answer → break                              │
│  Post-loop:                                                      │
│    → save messages → update session summary → extract profile    │
└──────────────────────────────────────────────────────────────────┘
                   │
        ┌──────────┼──────────┬────────────────┐
        ▼          ▼          ▼                ▼
  ┌──────────┐ ┌────────┐ ┌──────────┐ ┌───────────┐
  │Retrieval │ │Calc    │ │Lookup    │ │Routing    │
  │Tools     │ │Tools   │ │Tools     │ │Tools      │
  │          │ │        │ │          │ │           │
  │search_ea │ │calc_   │ │get_legal_│ │escalate_  │
  │search_mom│ │leave   │ │definitions│ │to_hr     │
  │search_all│ │calc_   │ │          │ │check_     │
  │          │ │notice  │ │          │ │eligibility│
  └──────────┘ └────────┘ └──────────┘ └───────────┘
```

---

## Phases

### Phase 1: Foundation (Session Memory + Token Budget)
> Unblock everything else. Prevent silent failures.

#### 1A. Token Budget Manager
- Count tokens for: system prompt + session context + retrieved chunks + user message
- Enforce a budget (e.g., leave 4096 tokens for output, cap input at context_window - 4096)
- Use `anthropic.count_tokens()` or tiktoken approximation

#### 1B. Session Memory with SummaryBuffer
- Replace raw `get_history(last_n_pairs=10)` with a tiered approach:
  - **Recent messages:** last 3-5 pairs verbatim
  - **Summary:** older messages compressed into a running summary via a lightweight Claude call
  - **Key facts:** extracted entities (employment type, salary, tenure) stored per-session
- Add `session_summary` column to `sessions` table
- Add `session_facts_json` column to `sessions` table
- Summary update triggered conditionally (async, non-blocking) — only when message count exceeds the verbatim window (> 3 pairs). Short conversations are a no-op.

#### 1C. Persistent User ID
- Frontend: switch from `sessionStorage` to `localStorage` for user ID
- Separate concept of `user_id` (persistent) from `session_id` (per conversation)
- Add `user_id` column to `sessions` table

**Files to create/modify:**

| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `backend/chat/token_budget.py` | Token counting and budget enforcement |
| Create | `backend/chat/context_manager.py` | SummaryBuffer logic, context assembly |
| Modify | `backend/chat/session_manager.py` | Add summary/facts columns, summary update methods |
| Modify | `backend/chat/rag_chain.py` | Use context_manager instead of raw get_history |
| Modify | `backend/config.py` | Add token budget settings |
| Modify | `frontend/src/hooks/useChat.js` | Persistent user_id in localStorage |
| Modify | `frontend/src/api/chatApi.js` | Send user_id alongside session_id |
| Modify | `backend/api/routes_chat.py` | Accept user_id parameter |

---

### Phase 2: Tool-Augmented Orchestration
> Replace static RAG pipeline with agentic tool-use loop.

#### 2A. Tool Registry & Definitions
- Define tool schemas following Anthropic's best practices (3-4 sentence descriptions, clear when-to-use / when-not-to-use)
- Tool registry maps tool names → async callables

#### 2B. Retrieval Tools (refactor existing)
- `search_employment_act` — semantic + keyword over EA collection only
- `search_mom_guidelines` — semantic + keyword over MOM collection only
- `search_all_policies` — search both (for cross-source queries)
- `get_legal_definitions` — fetch Section 2 definitions
- Each tool returns formatted context with source citations

#### 2C. Calculation Tools (new)
- `calculate_leave_entitlement` — annual leave, sick leave, maternity/paternity based on tenure, employment type, salary
- `calculate_notice_period` — based on service length and contract terms
- All calculations are deterministic Python (never ask the LLM to do arithmetic)

#### 2D. Routing Tools (new)
- `check_eligibility` — rule-based: is this person covered by EA Part IV? Salary thresholds?
- `escalate_to_hr` — flags conversation for human review, returns acknowledgement

#### 2E. Orchestration Loop
- Replace `stream_rag_response()` with agentic loop:
  - Send user message + tools to Claude
  - If `stop_reason == "tool_use"`: dispatch tool(s), append results, loop
  - If `stop_reason == "end_turn"`: stream final response
  - Max iterations guard (prevent infinite loops)
- Stream throughout all iterations — parse stream events to detect tool_use blocks vs text. No double API call.

**Files to create/modify:**

| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `backend/chat/orchestrator.py` | Agentic loop with tool dispatch |
| Create | `backend/chat/tools/__init__.py` | Tool registry |
| Create | `backend/chat/tools/registry.py` | Tool definitions, schemas, dispatch map |
| Create | `backend/chat/tools/retrieval_tools.py` | Retriever wrappers as Claude tools |
| Create | `backend/chat/tools/calculation_tools.py` | Leave, notice period calculations |
| Create | `backend/chat/tools/routing_tools.py` | Eligibility checks, escalation |
| Modify | `backend/chat/rag_chain.py` | Deprecate or refactor to call orchestrator |
| Modify | `backend/retrieval/retriever.py` | Expose per-collection search functions |
| Modify | `backend/chat/prompts.py` | Simplify — tool descriptions handle routing |
| Modify | `backend/api/routes_chat.py` | Wire up orchestrator instead of rag_chain |

---

### Phase 3: Profile & Semantic Memory
> Cross-session intelligence. System learns over time.

#### 3A. Profile Memory
- New `user_profiles` SQLite table:
  - `user_id`, `employment_type`, `salary_bracket`, `tenure_years`, `company`, `topics_json`, `preferences_json`, `updated_at`
- Profile extraction: after each conversation, async Claude call extracts/updates profile facts
- Profile injection: on session start, load profile into system prompt context
- Privacy: user can view and delete their profile (new API endpoint)

#### 3B. Verified Q&A Cache (Semantic Memory)
- New ChromaDB collection: `verified_answers`
- Flow: thumbs-up answers → admin reviews → approved → embedded and stored
- On query: check `verified_answers` first (similarity search). If high-confidence match → return cached answer (with "previously verified" label)
- Significantly reduces latency and Claude API cost for repeat questions

#### 3C. FAQ Pattern Detection
- Background job: analyze feedback + query logs to identify common question clusters
- Surface to admin dashboard: "Top 10 unanswered/poorly-answered topics"
- Feed back into knowledge base gaps → trigger targeted re-ingestion

**Files to create/modify:**

| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `backend/memory/__init__.py` | Memory module |
| Create | `backend/memory/profile_store.py` | User profile CRUD + extraction |
| Create | `backend/memory/semantic_cache.py` | Verified Q&A cache (ChromaDB) |
| Create | `backend/memory/fact_extractor.py` | Extract profile facts from conversations |
| Create | `backend/api/routes_profile.py` | GET/DELETE user profile endpoints |
| Modify | `backend/chat/orchestrator.py` | Inject profile context, check semantic cache |
| Modify | `backend/chat/session_manager.py` | Link sessions to user_id |
| Modify | `backend/api/routes_admin.py` | FAQ patterns, verified answers management |
| Modify | `frontend/src/pages/AdminDashboard.jsx` | FAQ patterns tab, verified answers tab |

---

### Phase 4: Document Management Improvements (DEFERRED)
> **Deferred until metrics show retrieval quality is a bottleneck.** The tool-based architecture in Phase 2 already provides intelligent query routing. Adding query expansion and compression adds Haiku calls and re-embedding overhead per retrieval — not justified without evidence of a recall problem.

#### 4A. Query Expansion (MultiQuery pattern) — DEFERRED
- Before retrieval tool execution, optionally generate 2-3 query rephrasings
- Merge results with RRF (extend existing RRF logic)
- Especially valuable for HR synonym coverage ("annual leave" / "vacation" / "PTO")

#### 4B. Contextual Compression — DEFERRED
- After retrieval, filter chunks for relevance before returning to the orchestrator
- Lightweight: use embedding similarity between query and each chunk as a relevance score
- Drop chunks below a threshold → fewer but higher-quality chunks in context

#### 4C. Metadata Filtering — SHIP WITH PHASE 2 (low cost)
- Allow retrieval tools to accept optional filters (Part, Division, section range)
- Claude can pass `section_filter: "Part IV"` when the query is clearly about a specific part
- Reduces noise, improves precision
- Already designed into retrieval tool schemas (Step 2.2)

**Files to create/modify (4C only — 4A/4B deferred):**

| Action | File Path | Description |
|--------|-----------|-------------|
| Modify | `backend/retrieval/retriever.py` | Add metadata filter support |
| Modify | `backend/retrieval/vector_store.py` | Pass where-clauses to ChromaDB |

---

## Implementation Order & Dependencies

```
Phase 1 (Foundation)          Phase 2 (Tools + 4C)         Phase 3 (Memory)
┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│ 1A Token Budget │──┐       │ 2A Tool Registry│──┐       │ 3A Profile Mem  │
│ 1B SummaryBuffer│──┼──────▶│ 2B Retrieval    │  │       │ 3B Verified Q&A │
│ 1C Persistent ID│──┘       │     Tools       │  ├──────▶│ 3C FAQ Patterns │
│                 │          │ 2C Calc Tools   │  │       │                 │
│                 │          │ 2D Routing Tools│  │       └─────────────────┘
│                 │          │ 2E Orchestrator │──┘
│                 │          │ 4C Metadata Filt│          Phase 4A/4B: DEFERRED
│                 │          └─────────────────┘          (until retrieval metrics
└─────────────────┘                                       justify the overhead)

                             Phase 2 depends on Phase 1    Phase 3 depends
                             (token budget needed for       on Phase 1C
                              orchestrator context          (persistent user_id)
                              management)                   + Phase 2E
                                                            (orchestrator)
```

---

## Open Questions

- [x] **Token counting method:** ~~Use `anthropic.count_tokens()` (API call, accurate) or local tiktoken approximation (free, ~95% accurate)?~~ **Decided: Use Anthropic's `client.beta.messages.count_tokens()` API for budget enforcement (single fast API call, accurate). Fallback to tiktoken `cl100k_base` with 15% safety margin if API is unreachable. tiktoken alone is insufficient — Claude's tokenizer differs from OpenAI's and can be off by 10-20%.**
- [x] **Streaming with tool use:** ~~Claude's tool_use responses are non-streaming. Should we send intermediate "thinking..." SSE events while tools execute?~~ **Decided: Option C — emit `{"status": "thinking", "detail": "Searching Employment Act..."}` SSE events before each tool call. Frontend renders as step-by-step status messages that disappear when streaming begins.**
- [x] **Profile data privacy:** ~~What's the retention policy for user profiles? PDPA (Singapore data protection) considerations?~~ **Decided: 2-year retention. Auto-delete profiles inactive for 2 years. User can manually delete at any time via API.**
- [x] **Verified Q&A threshold:** ~~What similarity threshold for the semantic cache to return a cached answer vs doing a fresh retrieval?~~ **Decided: Two-tier approach. ≥0.95 → serve cached answer directly. 0.88–0.94 → serve cached answer with disclaimer ("Based on a similar previously answered question. Ask again if this doesn't match your situation."). <0.88 → normal retrieval + Claude.**
- [x] **Max tool iterations:** ~~What's the cap on the orchestration loop?~~ **Decided: 5 iterations max. If the loop hasn't resolved after 5 tool calls, return a graceful fallback message.**

## Decisions Made

- **Single agent over multi-agent:** Bounded domain (2 sources, ~8 tools), sequential state-dependent tasks, cost/latency/debugging advantages. Unanimous industry recommendation.
- **No LangChain dependency:** Use Anthropic SDK directly. LangChain patterns as architectural reference only. Avoids abstraction tax and dependency churn.
- **SQLite for profile storage:** Already using SQLite for sessions. Adding profile tables avoids a new dependency. Migrate to PostgreSQL only if needed later.
- **ChromaDB for semantic cache:** Already using ChromaDB for document retrieval. Adding a `verified_answers` collection is natural extension.
- **SummaryBuffer over full summarization:** Preserves recent exchange fidelity while compressing older context. Best tradeoff for HR consultations where recent details matter most.
- **Anonymous persistent ID:** Use `localStorage` for a persistent anonymous user ID. No auth for now — add later before public deployment.
- **Haiku for summarization:** Use `claude-haiku-4-5` for session summary generation to reduce cost and latency. Sonnet reserved for main orchestration.
- **Hardcoded EA calculation rules:** Calculation tools use deterministic Python with hardcoded Employment Act rules. Version the rules and document the EA sections they derive from. Accept the risk that rules may change — mitigate with admin alerts when EA is re-ingested.
- **Haiku calls are best-effort:** All Haiku calls (summarization, fact extraction, profile extraction, query expansion) are non-critical. On failure: log the error, skip the enhancement, proceed with raw/un-enhanced data. Never fail a user request because a Haiku call failed.
- **Configurable similarity thresholds:** Verified Q&A cache thresholds (0.95 high / 0.88 medium) stored in `config.py`, not hardcoded. These are model-dependent and need tuning with real data.
- **Phase 4 deferred:** Query expansion (4A) and contextual compression (4B) add Haiku calls and re-embedding per retrieval. Given the tool-based architecture already lets Claude route queries intelligently, Phase 4 is deferred until metrics show retrieval quality is a bottleneck. Metadata filtering (4C) is low-cost and can ship with Phase 2.
- **Summary via system prompt, not fake messages:** Session summaries are injected as a system prompt appendix, not as synthetic user/assistant message pairs (which can confuse the model's conversation tracking).

## Implementation Plan — Step-by-Step

### Phase 1: Foundation (Session Memory + Token Budget)

#### Step 1.1: Persistent User ID (frontend + backend)
> Prerequisite: None. Start here — it's small and unblocks Phase 3.

**Backend:**
1. Add `user_id TEXT` column to `sessions` table in `session_manager.py` `CREATE_SCHEMA`
2. Update `get_or_create(session_id, user_id)` to accept and store `user_id`
3. Add DB migration: `ALTER TABLE sessions ADD COLUMN user_id TEXT` with fallback for existing DBs
4. Update `ChatRequest` Pydantic model in `routes_chat.py` to accept optional `user_id`
5. Pass `user_id` through `routes_chat.py` → `rag_chain.py` → `session_manager.get_or_create()`

**Frontend:**
6. In `useChat.js`: add `USER_KEY = "hr_chat_user_id"` stored in `localStorage` (persists across sessions)
7. Keep `SESSION_KEY` in `sessionStorage` (per-conversation, as today)
8. In `chatApi.js`: send `user_id` field in POST `/api/chat` body

**Tests:**
- `tests/test_session_manager.py`: test `get_or_create` with `user_id`, verify column persists
- `tests/test_routes_chat.py`: test `user_id` accepted in request body

**Acceptance criteria:**
- [ ] Same `user_id` survives browser tab close + reopen
- [ ] Different conversations get different `session_id` but same `user_id`
- [ ] Existing sessions without `user_id` still work (backward compatible)

---

#### Step 1.2: Token Budget Manager
> Prerequisite: None. Can build in parallel with 1.1.

1. Create `backend/chat/token_budget.py`:
   - `async def count_tokens(client: AsyncAnthropic, messages: list, system: str, tools: list | None = None) -> int`:
     - Primary: use `client.beta.messages.count_tokens()` (accurate, single fast API call)
     - Fallback: if API call fails, use tiktoken `cl100k_base` with 15% safety margin (`int(estimate * 0.85)`)
   - `estimate_tokens_local(text: str) -> int` — tiktoken fallback for quick local estimates
   - `TokenBudget` class:
     ```python
     class TokenBudget:
         context_window: int = 200_000  # claude-sonnet-4-6
         max_output: int = 4_096
         max_input: int = context_window - max_output

         def allocate(self, used_tokens: int) -> BudgetAllocation:
             """Returns how many tokens are available for history + retrieved context."""
             remaining = self.max_input - used_tokens
             # Split remaining: 40% history, 60% retrieval context
             return BudgetAllocation(
                 history_budget=int(remaining * 0.4),
                 context_budget=int(remaining * 0.6),
             )
     ```
   - `BudgetAllocation` dataclass with `history_budget`, `context_budget` fields
   - `truncate_to_budget(messages: list[dict], budget: int) -> list[dict]` — trim oldest messages first

2. Add to `backend/config.py`:
   - `context_window: int = 200_000`
   - `max_output_tokens: int = 4_096`
   - `history_budget_ratio: float = 0.4`

3. Install `tiktoken` — add to `requirements.txt` (fallback only)

**Tests:**
- `tests/test_token_budget.py`: test `count_tokens` with mocked API, test fallback to tiktoken, test `allocate` math, test `truncate_to_budget` trims correctly

**Acceptance criteria:**
- [ ] `count_tokens` uses Anthropic API when available
- [ ] Falls back to tiktoken with 15% safety margin on API failure
- [ ] `allocate()` never returns negative budgets
- [ ] `truncate_to_budget()` preserves newest messages, drops oldest
- [ ] Long conversations don't exceed context window

---

#### Step 1.3: Context Manager with SummaryBuffer
> Prerequisite: Step 1.2 (needs token budget). Can start after 1.2.

**DB schema changes (`session_manager.py`):**
1. Add columns to `sessions` table:
   - `summary TEXT DEFAULT ''` — running summary of older exchanges
   - `session_facts_json TEXT DEFAULT '{}'` — extracted key facts (employment type, salary, tenure)
2. Add methods:
   - `update_summary(session_id: str, summary: str) -> None`
   - `update_session_facts(session_id: str, facts: dict) -> None`
   - `get_session_context(session_id: str) -> SessionContext` — returns summary + facts + recent messages

**Context manager (`backend/chat/context_manager.py`):**
3. Create `SessionContext` dataclass:
   ```python
   @dataclass
   class SessionContext:
       summary: str           # compressed older history
       facts: dict            # extracted entities
       recent_messages: list  # last N pairs verbatim
       token_count: int       # total tokens used by this context
   ```

4. `async def build_context(session_id: str, token_budget: int) -> SessionContext`:
   - Fetch all messages for session
   - If total tokens ≤ budget: return all messages verbatim (no summary needed)
   - If total tokens > budget:
     - Keep last 3 pairs verbatim
     - Summarize older messages via Haiku call
     - Extract key facts (employment type, salary, tenure) from summary
     - Store updated summary + facts back to DB
     - Return `SessionContext` with summary prefix + recent messages

5. `async def generate_summary(messages: list[dict]) -> str`:
   - Call `claude-haiku-4-5` with a summarization prompt
   - Prompt: "Summarize this HR conversation. Preserve: employee details, specific questions asked, answers given, any legal provisions cited. Be concise."
   - Return summary string (~100-200 tokens)

6. `async def extract_facts(messages: list[dict]) -> dict`:
   - Call `claude-haiku-4-5` with extraction prompt
   - Prompt: "Extract key facts from this HR conversation as JSON: {employment_type, salary_range, tenure_years, company, specific_situation}. Return only fields that are explicitly mentioned."
   - Return parsed dict

7. `def format_context_for_prompt(ctx: SessionContext) -> tuple[str, list[dict]]`:
   - Returns `(summary_system_block, recent_messages)`
   - If summary exists: return summary as a system prompt appendix block (e.g., `"\n\nCONVERSATION CONTEXT:\n{summary}\n\nKnown facts: {facts}"`) — injected into the system prompt, NOT as fake user/assistant messages (fake pairs can confuse the model)
   - Return recent messages verbatim as the messages list

**Integration (`rag_chain.py`):**
8. Replace:
   ```python
   history = await session_manager.get_history(session_id)
   messages = history + [{"role": "user", "content": user_message}]
   ```
   With:
   ```python
   budget = token_budget.allocate(system_prompt, user_message)
   ctx = await context_manager.build_context(session_id, budget.history_budget)
   messages = context_manager.format_context_for_prompt(ctx) + [{"role": "user", "content": user_message}]
   ```

9. After response completes, trigger async summary update:
   ```python
   asyncio.create_task(context_manager.maybe_update_summary(session_id))
   ```

**Tests:**
- `tests/test_context_manager.py`:
  - Test `build_context` with short history (no summary needed)
  - Test `build_context` with long history (triggers summarization) — mock Haiku call
  - Test `format_context_for_prompt` output structure
  - Test `extract_facts` returns valid JSON — mock Haiku call
  - Test token budget is respected
- `tests/test_session_manager.py`:
  - Test `update_summary`, `update_session_facts`, `get_session_context`

**Acceptance criteria:**
- [ ] Short conversations (< 3 pairs) — no summary generated, raw history used
- [ ] Long conversations (> 5 pairs) — older messages summarized, last 3 pairs verbatim
- [ ] Summary + recent messages fit within token budget
- [ ] Facts extracted and stored in `session_facts_json`
- [ ] Summary update is async — doesn't block response streaming
- [ ] Haiku model used for summarization (not Sonnet)

---

### Phase 2: Tool-Augmented Orchestration

#### Step 2.1: Tool Registry & Schema Definitions
> Prerequisite: None. Can start in parallel with Phase 1.

1. Create `backend/chat/tools/__init__.py` (empty)

2. Create `backend/chat/tools/registry.py`:
   - `TOOL_SCHEMAS: list[dict]` — Anthropic tool format definitions for all tools
   - `TOOL_DISPATCH: dict[str, Callable]` — maps tool name → async handler function
   - `async def dispatch_tool(name: str, input: dict) -> str` — looks up handler, executes, returns result string
   - `def get_all_schemas() -> list[dict]` — returns `TOOL_SCHEMAS`
   - Each schema follows Anthropic best practices: 3-4 sentence description, clear when-to-use/when-not-to-use, `input_schema` with Pydantic-style JSON Schema

3. Tool schema template:
   ```python
   {
       "name": "search_employment_act",
       "description": (
           "Search the Singapore Employment Act for legal provisions, statutory rights, "
           "penalties, and obligations. Use this when the user asks about legal entitlements, "
           "specific Act sections, or employer obligations under the law. "
           "Do NOT use this for practical how-to procedures — use search_mom_guidelines instead."
       ),
       "input_schema": {
           "type": "object",
           "properties": {
               "query": {"type": "string", "description": "The search query describing what to find"},
               "section_filter": {"type": "string", "description": "Optional: filter to a specific Part (e.g. 'Part IV', 'Part X')"}
           },
           "required": ["query"]
       }
   }
   ```

**Tests:**
- `tests/test_tool_registry.py`: validate all schemas are well-formed, dispatch map matches schemas, unknown tool raises error

**Acceptance criteria:**
- [ ] All tool schemas pass Anthropic's tool format validation
- [ ] Every schema has a name, 3+ sentence description, and input_schema
- [ ] `dispatch_tool` routes to correct handler
- [ ] Unknown tool name raises clear error

---

#### Step 2.2: Retrieval Tools
> Prerequisite: Step 2.1 (registry). Uses existing `retriever.py`.

1. Create `backend/chat/tools/retrieval_tools.py`:

2. Refactor `backend/retrieval/retriever.py` — expose per-collection functions:
   - `retrieve_from_collection(query: str, collection: str, n: int = 10) -> list[dict]` — single-collection semantic + keyword
   - Keep existing `retrieve()` as a wrapper that calls both collections
   - Add optional `section_filter: str | None` parameter for metadata filtering

3. Implement tool handlers:
   - `async def search_employment_act(query: str, section_filter: str | None = None) -> str`
     - Calls `retrieve_from_collection(query, "employment_act")`
     - If `section_filter`: post-filter results by metadata `part` field
     - Formats results as numbered text with source labels (reuse `format_context`)
     - Returns formatted string for Claude to read
   - `async def search_mom_guidelines(query: str) -> str`
     - Calls `retrieve_from_collection(query, "mom_guidelines")`
     - Returns formatted string
   - `async def search_all_policies(query: str) -> str`
     - Calls existing `retrieve(query)`
     - Returns formatted string
   - `async def get_legal_definitions(term: str) -> str`
     - Wraps existing `get_section_2()` logic
     - Returns Section 2 text or "Definition not found"

4. Register all 4 tools in `registry.py`

**Tests:**
- `tests/test_retrieval_tools.py`: mock `vector_store.query`, verify each tool returns formatted strings, verify section_filter works

**Acceptance criteria:**
- [ ] Each tool returns human-readable formatted text with source citations
- [ ] `search_employment_act` with `section_filter="Part IV"` only returns Part IV results
- [ ] `get_legal_definitions` returns Section 2 content or graceful "not found"
- [ ] Tools handle empty results gracefully

---

#### Step 2.3: Calculation Tools
> Prerequisite: Step 2.1 (registry). Independent of 2.2.

1. Create `backend/chat/tools/calculation_tools.py`:

2. `calculate_leave_entitlement(tenure_years: float, employment_type: str, leave_type: str) -> str`:
   - **Annual leave** (EA s43): 7 days (year 1) → +1/year → cap 14 days (year 8+)
   - **Sick leave** (EA s89): 14 days outpatient + 60 days hospitalisation (after 6 months service)
   - **Maternity** (EA Part IX): 16 weeks (conditions apply)
   - **Paternity** (GPEA): 2 weeks
   - **Childcare** (CCDA): 6 days/year (child < 7), 2 days/year (child 7-12)
   - Handle part-time pro-rating
   - Return structured text: entitlement + conditions + EA section reference

3. `calculate_notice_period(tenure_years: float, contract_notice: str | None = None) -> str`:
   - EA s10: < 26 weeks → 1 day; 26 weeks–2 years → 1 week; 2–5 years → 2 weeks; 5+ years → 4 weeks
   - Contract terms override if more favourable
   - Return structured text with EA section reference

4. Add `EA_RULES_VERSION = "2025-01"` constant — document which version of the Act rules are based on

5. Register both tools in `registry.py`

**Tests:**
- `tests/test_calculation_tools.py`:
  - Annual leave: 1 year → 7 days, 3 years → 9 days, 8+ years → 14 days
  - Sick leave: < 6 months → not eligible, 6+ months → 14+60
  - Notice period: all tenure brackets
  - Part-time pro-rating
  - Edge cases: 0 tenure, negative tenure (error)

**Acceptance criteria:**
- [ ] All calculations match Employment Act provisions exactly
- [ ] Every result includes the EA section reference it derives from
- [ ] Part-time pro-rating is correct
- [ ] Edge cases return clear error messages, not crashes
- [ ] `EA_RULES_VERSION` is set and documented

---

#### Step 2.4: Routing Tools
> Prerequisite: Step 2.1 (registry). Independent of 2.2/2.3.

1. Create `backend/chat/tools/routing_tools.py`:

2. `check_eligibility(salary_monthly: float, role: str, employment_type: str) -> str`:
   - EA Part IV (rest days, hours, overtime): applies to workmen ≤$4,500 and non-workmen ≤$2,600
   - EA general coverage: all employees under contract of service (excludes domestic workers, seafarers, statutory board employees)
   - Return: which Parts apply, which don't, and why

3. `escalate_to_hr(reason: str, session_id: str) -> str`:
   - Log escalation request to a new `escalations` SQLite table (session_id, reason, created_at, status)
   - Return acknowledgement: "Your question has been flagged for HR review. Reference: [escalation_id]"
   - **MVP scope:** Escalation is a log entry visible in the admin dashboard only. No push notification. Future: trigger email/Slack notification — stub the notification hook now so it's easy to add later
   - Add `GET /admin/escalations` endpoint to surface pending escalations in admin dashboard

4. Add `escalations` table to `session_manager.py` schema

5. Register both tools in `registry.py`

**Tests:**
- `tests/test_routing_tools.py`:
  - Eligibility: workman $4000 → covered by Part IV; exec $5000 → not covered; non-workman $2000 → covered
  - Escalation: creates DB record, returns reference ID

**Acceptance criteria:**
- [ ] Eligibility check correctly applies salary thresholds for workmen vs non-workmen
- [ ] Escalation creates a persistent record
- [ ] Escalation returns a reference ID the user can quote

---

#### Step 2.5: Orchestration Loop
> Prerequisite: Steps 1.2, 1.3, 2.1-2.4 (needs token budget, context manager, all tools)
> This is the core integration step.

1. Create `backend/chat/orchestrator.py`:

2. Core loop — **stream throughout** (avoids double API call):
   ```python
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
       This avoids the double-call anti-pattern (non-streaming check + streaming re-call).
       """

       # 1. Load context
       await session_manager.get_or_create(session_id, user_id)
       system_prompt = build_system_prompt(user_role)  # simplified — no context block
       budget_tokens = await token_budget.count_tokens(client, messages, system_prompt)
       budget = token_budget.allocate(budget_tokens)
       ctx = await context_manager.build_context(session_id, budget.history_budget)

       messages = context_manager.format_context_for_prompt(ctx)
       messages.append({"role": "user", "content": user_message})

       # 2. Agentic loop — streaming throughout
       tools = registry.get_all_schemas()
       max_iterations = 5

       for iteration in range(max_iterations):
           # Always stream — parse events to detect tool_use vs text
           collected_content = []  # accumulates content blocks
           full_text = ""          # accumulates streamed text
           has_tool_use = False

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
                       # Stream text tokens directly to client (only if no tool_use detected)
                       full_text += event.text
                       yield _sse({"token": event.text, "done": False})

               # Get the final message with all content blocks
               response = await stream.get_final_message()
               collected_content = response.content

           if has_tool_use:
               # Tool use detected — collect tool blocks, dispatch, loop back
               tool_blocks = [b for b in collected_content if b.type == "tool_use"]
               messages.append({"role": "assistant", "content": collected_content})

               tool_results = []
               for block in tool_blocks:
                   yield _sse({"status": "thinking", "detail": _tool_display_name(block.name)})
                   try:
                       result = await registry.dispatch_tool(block.name, block.input)
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
               # Extract full text from collected content
               full_response = "".join(
                   b.text for b in collected_content if b.type == "text"
               )

               sources = _extract_sources_from_tool_results(messages)
               yield _sse({"token": "", "done": True, "sources": sources})

               # Persist
               await session_manager.add_message(session_id, "user", user_message)
               await session_manager.add_message(session_id, "assistant", full_response)
               asyncio.create_task(context_manager.maybe_update_summary(session_id))
               return

       # Max iterations reached
       yield _sse({"token": FALLBACK_MAX_ITERATIONS, "done": True, "sources": []})
   ```

3. Helper functions:
   - `_tool_display_name(name: str) -> str` — maps tool names to user-friendly labels:
     ```python
     _DISPLAY_NAMES = {
         "search_employment_act": "Searching Employment Act...",
         "search_mom_guidelines": "Searching MOM guidelines...",
         "search_all_policies": "Searching all policies...",
         "get_legal_definitions": "Looking up legal definitions...",
         "calculate_leave_entitlement": "Calculating leave entitlement...",
         "calculate_notice_period": "Calculating notice period...",
         "check_eligibility": "Checking eligibility...",
         "escalate_to_hr": "Escalating to HR...",
     }
     ```
   - `_extract_sources_from_tool_results(messages) -> list[dict]` — scan tool results for source metadata

4. Update `backend/api/routes_chat.py`:
   - Import `orchestrator.orchestrate` instead of `rag_chain.stream_rag_response`
   - Pass `user_id` from request

5. Update `backend/chat/prompts.py`:
   - Simplify `build_system_prompt` — remove the `context` parameter (tools now handle retrieval)
   - Keep role instructions (employee vs HR)
   - Add tool-use guidance: "You have access to tools for searching policies, calculating entitlements, and checking eligibility. Use them when needed."

6. Keep `rag_chain.py` as a fallback — add a feature flag in `config.py`:
   - `use_orchestrator: bool = True`
   - Route to orchestrator or legacy rag_chain based on flag

**Frontend changes:**
7. Update `frontend/src/hooks/useChat.js` — handle `status` SSE events:
   - Add `STREAM_STATUS` action to reducer
   - Render status as a temporary message or indicator in the assistant bubble
8. Update `frontend/src/components/MessageBubble.jsx`:
   - If message has `thinkingSteps`, render them as subtle status lines above the content

**Tests:**
- `tests/test_orchestrator.py`:
  - Mock Claude API responses to simulate: direct answer (no tools), single tool call, multi-tool chain, max iterations reached
  - Verify SSE events are emitted in correct order: thinking → thinking → streaming → done
  - Verify tool results are appended correctly to messages
  - Verify fallback on max iterations
  - Verify sources extracted from tool results
- `tests/test_routes_chat.py`: integration test with orchestrator
- `tests/test_prompts.py`: updated system prompt structure

**Acceptance criteria:**
- [ ] Simple questions (greetings, clarifications) → Claude answers directly, no tool calls
- [ ] Policy questions → Claude calls retrieval tool(s), then answers with citations
- [ ] Calculation questions → Claude calls calculation tool, then presents results
- [ ] Eligibility questions → Claude calls check_eligibility, then explains
- [ ] Complex questions → Claude chains multiple tools (e.g., check eligibility → search EA → calculate)
- [ ] "Thinking..." events stream to frontend during tool execution
- [ ] Max 5 iterations enforced, graceful fallback
- [ ] Feature flag allows switching back to legacy rag_chain
- [ ] All existing tests still pass (backward compatibility)

---

### Phase 3: Profile & Semantic Memory

#### Step 3.1: Profile Memory Store
> Prerequisite: Step 1.1 (persistent user_id) + Step 2.5 (orchestrator)

1. Create `backend/memory/__init__.py`

2. Create `backend/memory/profile_store.py`:
   - `user_profiles` table: `user_id TEXT PRIMARY KEY, employment_type TEXT, salary_bracket TEXT, tenure_years REAL, company TEXT, topics_json TEXT DEFAULT '[]', preferences_json TEXT DEFAULT '{}', created_at DATETIME, updated_at DATETIME`
   - `async def get_profile(user_id: str) -> dict | None`
   - `async def upsert_profile(user_id: str, facts: dict) -> None` — merge new facts with existing (don't overwrite with nulls)
   - `async def delete_profile(user_id: str) -> None`
   - `async def cleanup_stale_profiles(retention_years: int = 2) -> int`

3. Create `backend/memory/fact_extractor.py`:
   - `async def extract_profile_facts(messages: list[dict]) -> dict` — call Haiku to extract employment_type, salary_bracket, tenure, company from conversation
   - Called async after each conversation turn (non-blocking)

4. Integrate into orchestrator:
   - On session start: load profile, inject as context: "Known user context: [employment_type], [salary], [tenure]"
   - After response: `asyncio.create_task(update_profile_from_conversation(user_id, session_id))`

5. Create `backend/api/routes_profile.py`:
   - `GET /api/profile/{user_id}` — return profile (for future settings page)
   - `DELETE /api/profile/{user_id}` — delete profile (privacy)

6. Add profile cleanup to existing `cleanup_loop` in session_manager

**Tests:**
- `tests/test_profile_store.py`: CRUD operations, merge logic, stale cleanup
- `tests/test_fact_extractor.py`: mock Haiku, verify extraction

**Acceptance criteria:**
- [ ] Profile persists across sessions for same user_id
- [ ] New facts merge with existing (don't overwrite good data with nulls)
- [ ] Profile auto-deletes after 2 years inactive
- [ ] User can delete their profile via API
- [ ] Profile context injected into orchestrator system prompt

---

#### Step 3.2: Verified Q&A Cache
> Prerequisite: Step 2.5 (orchestrator) + existing feedback system

1. Create `backend/memory/semantic_cache.py`:
   - New ChromaDB collection: `verified_answers`
   - Thresholds read from `config.py` (`cache_high_threshold: float = 0.95`, `cache_medium_threshold: float = 0.88`) — configurable, not hardcoded
   - `async def check_cache(query: str) -> CacheResult | None`:
     - Embed query, search `verified_answers`
     - If similarity ≥ `cache_high_threshold`: return `CacheResult(answer=..., confidence="high", disclaimer=None)`
     - If `cache_medium_threshold` ≤ similarity < `cache_high_threshold`: return `CacheResult(answer=..., confidence="medium", disclaimer="Based on a similar previously answered question...")`
     - If < `cache_medium_threshold`: return `None`
   - `async def add_verified_answer(question: str, answer: str, sources: list) -> str` — embed and store
   - `async def remove_verified_answer(answer_id: str) -> None`

2. Admin workflow:
   - Add `GET /admin/feedback/candidates` — returns thumbs-up answers not yet in cache
   - Add `POST /admin/verified-answers` — admin approves answer into cache
   - Add `DELETE /admin/verified-answers/{id}` — admin removes from cache
   - Add `GET /admin/verified-answers` — list all cached answers

3. Integrate into orchestrator:
   - Before starting agentic loop, check semantic cache
   - If cache hit: stream cached answer directly (skip Claude API call)
   - Log cache hits for metrics

4. Update admin dashboard frontend:
   - `frontend/src/components/VerifiedAnswersTab.jsx` — list, approve, delete cached answers
   - `frontend/src/api/adminApi.js` — add verified answers API calls
   - `frontend/src/pages/AdminDashboard.jsx` — add "Verified Answers" tab

**Tests:**
- `tests/test_semantic_cache.py`: mock ChromaDB, test two-tier thresholds, test add/remove
- `tests/test_routes_admin.py`: test admin CRUD endpoints

**Acceptance criteria:**
- [ ] High-confidence cache hit (≥ high threshold) returns answer without Claude API call
- [ ] Medium-confidence hit returns answer with disclaimer
- [ ] Low similarity falls through to normal orchestration
- [ ] Admin can approve/reject/remove cached answers
- [ ] Cache hit rate tracked in metrics
- [ ] Thresholds configurable via `.env` / `config.py`

---

#### Step 3.3: FAQ Pattern Detection
> Prerequisite: Step 3.2 (semantic cache) + existing feedback system

1. Create `backend/memory/faq_analyzer.py`:
   - `async def analyze_query_patterns(days: int = 30) -> list[dict]` — cluster recent queries by embedding similarity, return top clusters with counts
   - `async def identify_gaps() -> list[dict]` — find queries with no results or thumbs-down, cluster them

2. Add `GET /admin/faq-patterns` endpoint
3. Add FAQ patterns tab to admin dashboard

**Tests:**
- `tests/test_faq_analyzer.py`: mock query data, verify clustering

**Acceptance criteria:**
- [ ] Top 10 question clusters surfaced to admin
- [ ] Knowledge gaps (unanswered/poorly-answered) identified
- [ ] Admin can view patterns and take action

---

### Phase 4: Document Management Improvements

#### Step 4C: Metadata Filtering (ships with Phase 2)
> Prerequisite: Step 2.2 (retrieval tools)

1. Update `backend/retrieval/vector_store.py`:
   - `query()` accepts optional `where: dict` parameter → passes to ChromaDB `where` clause
   - Example: `where={"part": "Part IV"}`

2. Update `backend/retrieval/retriever.py`:
   - `retrieve_from_collection()` accepts `metadata_filter: dict | None`

3. Update retrieval tools to pass through `section_filter` → `metadata_filter`

**Tests:**
- `tests/test_vector_store.py`: test with and without where clause
- `tests/test_retrieval_tools.py`: test section_filter passthrough

**Acceptance criteria:**
- [ ] `section_filter="Part IV"` returns only Part IV chunks
- [ ] No filter → returns all matching chunks (existing behaviour)
- [ ] Invalid filter → graceful fallback to unfiltered search

#### Steps 4A & 4B: DEFERRED
Query expansion and contextual compression are deferred until retrieval quality metrics indicate they are needed. Revisit after Phase 3 is shipped and we have real usage data.

---

### Cross-Cutting: ARCHITECTURE.md Update (CLAUDE.md Rule 4)

After each PR is merged, update `ARCHITECTURE.md`:
- **PR 1:** Add token budget manager, context manager, and user_id to Component Map. Update Data Model with new columns.
- **PR 2:** Add tool registry, all tool modules to Component Map. Add new API endpoints (escalations). Update Architecture Diagram with tool dispatch flow.
- **PR 3:** Replace RAG chain with orchestrator in Component Map. Update Architecture Diagram with agentic loop. Add feature flag to notes.
- **PR 4:** Add memory module (profile_store, semantic_cache) to Component Map. Add profile and verified answers API endpoints. Update Data Model with user_profiles table and verified_answers collection.
- Add Feature Log row for each PR.

---

## PR Strategy

| PR | Contains | Depends On | ARCHITECTURE.md Update |
|----|----------|------------|------------------------|
| **PR 1** | Phase 1: Token budget + SummaryBuffer + persistent user ID | — | Token budget, context manager, user_id column |
| **PR 2** | Phase 2A-2D + 4C: Tool registry + all tools + metadata filtering | PR 1 merged | Tool modules, escalations table, new endpoints |
| **PR 3** | Phase 2E: Orchestrator + frontend thinking UX + prompts refactor | PR 2 merged | Replace rag_chain with orchestrator, feature flag |
| **PR 4** | Phase 3A-3B: Profile memory + verified Q&A cache | PR 3 merged | Memory module, profile table, verified_answers collection |
| **PR 5** | Phase 3C: FAQ pattern detection | PR 4 merged | FAQ analyzer, admin endpoint |

Each PR should be independently testable and deployable. Feature flag on orchestrator allows safe rollout. Phase 4A/4B deferred — no PR planned until retrieval metrics justify it.

---

## Comments / Review Notes

- Phase 1 and Phase 2 are the core deliverables. Phase 3 is enhancement. Phase 4A/4B deferred.
- Each phase should be a separate PR to keep reviews manageable.
- The orchestrator (Phase 2E) is the biggest single change — it replaces the core `rag_chain.py` flow.
- Calculation tools (Phase 2C) need careful validation against the Employment Act — hardcoded rules must be verified and versioned.
- Feature flag on orchestrator allows A/B testing against the existing static RAG pipeline.
- ARCHITECTURE.md must be updated after each PR (CLAUDE.md Rule 4).
- Branch name typo: `feature/Enchancing_Chatbot` — "Enchancing" should be "Enhancing." Already on this branch; not renaming.

### Review Feedback Applied (2026-03-20)
1. **Fixed: Double API call** — Orchestrator now uses streaming throughout. Parses stream to detect tool_use blocks. No re-call for final response.
2. **Fixed: tiktoken accuracy** — Switched to `client.beta.messages.count_tokens()` (Anthropic API, accurate) with tiktoken + 15% safety margin as fallback.
3. **Fixed: Summary trigger** — `maybe_update_summary` short-circuits when message count ≤ 3 pairs. No unnecessary Haiku calls.
4. **Fixed: Haiku error handling** — All Haiku calls are best-effort. On failure: log error, proceed without enhancement. Never fail a user request.
5. **Fixed: Escalation scope** — Clarified as MVP log entry only. Admin dashboard visibility. Notification hook stubbed for future.
6. **Fixed: Configurable thresholds** — Q&A cache thresholds in `config.py`, not hardcoded.
7. **Noted: Branch typo** — Acknowledged, not renaming.
8. **Fixed: Phase 4 deferred** — 4A/4B deferred until metrics justify. 4C (metadata filtering) ships with Phase 2.
9. **Fixed: Summary injection** — Uses system prompt appendix, not fake user/assistant messages.
10. **Fixed: Frontend file paths** — Added specific component paths for Phase 3 admin dashboard updates.
11. **Fixed: ARCHITECTURE.md** — Added cross-cutting step with per-PR update requirements.
