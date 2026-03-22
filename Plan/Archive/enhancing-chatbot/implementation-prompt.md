# Implementation Prompt — Enhancing Chatbot

> Copy the relevant phase section below into a new Claude Code session to begin implementation.

---

## Phase 1: Foundation (Session Memory + Token Budget + Persistent User ID)

```
I'm implementing Phase 1 of the "Enhancing Chatbot" feature plan. Read the full plan first:

Plan/Planning/enhancing-chatbot/plan.md

Focus on the "Implementation Plan — Step-by-Step" section, Phase 1 (Steps 1.1, 1.2, 1.3).

Context:
- Branch: feature/Enchancing_Chatbot (already created, already checked out)
- This is a FastAPI + Anthropic Claude + ChromaDB + SQLite HR chatbot
- Read CLAUDE.md for project rules (especially Rules 1-5)
- Read ARCHITECTURE.md for current system design

Phase 1 has 3 steps that can partially parallelise:
- Step 1.1: Persistent User ID (frontend localStorage + backend user_id column) — no dependencies
- Step 1.2: Token Budget Manager (Anthropic count_tokens API + tiktoken fallback) — no dependencies
- Step 1.3: Context Manager with SummaryBuffer (depends on 1.2)

Key decisions already made:
- Token counting: Use client.beta.messages.count_tokens() (Anthropic API), fallback to tiktoken cl100k_base with 15% safety margin
- Summary model: claude-haiku-4-5 (not Sonnet)
- Summary injection: Via system prompt appendix, NOT fake user/assistant message pairs
- Summary trigger: Only when message count > 3 pairs (short conversations are a no-op)
- Haiku calls are best-effort: On failure, log error and proceed with raw/un-enhanced data
- User identity: Anonymous persistent ID via localStorage, no auth

Implementation order:
1. Start with Step 1.1 (persistent user ID) and Step 1.2 (token budget) in parallel
2. Then Step 1.3 (context manager) which depends on 1.2

For each step:
- Follow the file paths and acceptance criteria in the plan exactly
- Write tests mirroring backend/ structure in tests/
- Use the project logger (backend/lib/logger.py), never bare print()
- Run tests after each step: python -m pytest tests/ -v
- Run secret scan before any commit (CLAUDE.md Rule 1)

Do NOT start Phase 2. Do NOT modify files outside Phase 1 scope without asking (CLAUDE.md Rule 5).
```

---

## Phase 2 (PR 2): Tool Registry + All Tool Implementations + Metadata Filtering

```
I'm implementing Phase 2 (Steps 2.1-2.4 + 4C) of the "Enhancing Chatbot" feature plan. Read the full plan first:

Plan/Planning/enhancing-chatbot/plan.md

Focus on the "Implementation Plan — Step-by-Step" section, Steps 2.1 through 2.4, plus Step 4C (Metadata Filtering).

Context:
- Branch: feature/Enchancing_Chatbot
- Phase 1 is already merged (token budget, context manager, persistent user ID are available)
- Read CLAUDE.md for project rules, ARCHITECTURE.md for current design
- Read the existing retrieval code before modifying:
  - backend/retrieval/retriever.py
  - backend/retrieval/vector_store.py
  - backend/retrieval/keyword_search.py
  - backend/chat/prompts.py

Phase 2 (PR 2) has 5 steps — 2.2/2.3/2.4 can parallelise after 2.1:
- Step 2.1: Tool Registry & Schema Definitions (backend/chat/tools/registry.py)
- Step 2.2: Retrieval Tools — refactor retriever.py, expose per-collection functions, wrap as tools
- Step 2.3: Calculation Tools — hardcoded EA rules (annual leave, sick leave, notice period)
- Step 2.4: Routing Tools — check_eligibility, escalate_to_hr (MVP: log entry + admin endpoint)
- Step 4C: Metadata Filtering — add where-clause support to vector_store.py + retriever.py

Key decisions already made:
- Tool descriptions: 3-4 sentences following Anthropic best practices (when to use / when NOT to use)
- Calculation rules: Hardcoded from Employment Act. EA_RULES_VERSION = "2025-01". Every result cites the EA section.
- Escalation: MVP is a SQLite log entry visible in admin dashboard. Stub a notification hook for future email/Slack.
- Metadata filtering: ChromaDB where-clause passthrough, used by search_employment_act's section_filter param.

Implementation order:
1. Step 2.1 first (registry is needed by all tools)
2. Steps 2.2, 2.3, 2.4, 4C in parallel
3. Register all tools in registry.py at the end

For each step:
- Follow the file paths and acceptance criteria in the plan exactly
- Write tests in tests/ mirroring the module structure
- Use the project logger, never bare print()
- Run tests after each step: python -m pytest tests/ -v

Do NOT build the orchestrator (Step 2.5) — that's PR 3. Do NOT modify rag_chain.py or routes_chat.py. This PR only creates and tests the tools.
```

---

## Phase 2 (PR 3): Orchestrator + Frontend Thinking UX + Prompts Refactor

```
I'm implementing the orchestrator (Step 2.5) of the "Enhancing Chatbot" feature plan. Read the full plan first:

Plan/Planning/enhancing-chatbot/plan.md

Focus on Step 2.5 in the "Implementation Plan — Step-by-Step" section.

Context:
- Branch: feature/Enchancing_Chatbot
- Phase 1 (token budget, context manager, persistent user ID) is merged
- Phase 2 tools (PR 2: registry, retrieval tools, calculation tools, routing tools, metadata filtering) are merged
- Read CLAUDE.md for project rules, ARCHITECTURE.md for current design
- Read the existing code being replaced:
  - backend/chat/rag_chain.py (current flow — will become fallback)
  - backend/api/routes_chat.py (will switch to orchestrator)
  - backend/chat/prompts.py (will simplify)
  - frontend/src/hooks/useChat.js (will handle thinking events)
  - frontend/src/components/MessageBubble.jsx (will render thinking steps)

This is the biggest single change — it replaces the core RAG pipeline with an agentic tool-use loop.

Key decisions already made:
- Stream throughout ALL iterations (no double API call). Parse stream events to detect tool_use blocks.
- Thinking UX: Emit {"status": "thinking", "detail": "Searching Employment Act..."} SSE events before each tool call
- Summary context: Inject via system prompt appendix, not fake messages
- Max 5 tool iterations, graceful fallback message on limit
- Feature flag: use_orchestrator: bool = True in config.py — allows switching back to legacy rag_chain
- Keep rag_chain.py as fallback, don't delete it

Implementation:
1. Create backend/chat/orchestrator.py with the streaming agentic loop (see plan for full code pattern)
2. Update backend/chat/prompts.py — remove context parameter, add tool-use guidance
3. Update backend/api/routes_chat.py — route to orchestrator (or rag_chain via feature flag)
4. Update backend/config.py — add use_orchestrator flag
5. Update frontend/src/hooks/useChat.js — handle STREAM_STATUS action for thinking events
6. Update frontend/src/components/MessageBubble.jsx — render thinkingSteps
7. Write tests: tests/test_orchestrator.py (mock Claude API, test all scenarios)

Test scenarios to cover:
- Direct answer (no tools) — Claude responds without tool calls
- Single tool call — retrieval → answer
- Multi-tool chain — check_eligibility → search_ea → calculate_leave
- Max iterations reached — graceful fallback
- Tool error — is_error: true in tool result, Claude handles gracefully
- SSE event order: thinking → thinking → streaming tokens → done

After implementation:
- Run full test suite: python -m pytest tests/ -v
- Secret scan (CLAUDE.md Rule 1)
- Update ARCHITECTURE.md: replace rag_chain with orchestrator in Component Map, update Architecture Diagram
```

---

## Phase 3 (PR 4): Profile Memory + Verified Q&A Cache

```
I'm implementing Phase 3 (Steps 3.1 and 3.2) of the "Enhancing Chatbot" feature plan. Read the full plan first:

Plan/Planning/enhancing-chatbot/plan.md

Focus on Steps 3.1 and 3.2 in the "Implementation Plan — Step-by-Step" section.

Context:
- Branch: feature/Enchancing_Chatbot
- Phases 1-2 are merged (token budget, context manager, persistent user ID, tools, orchestrator all available)
- Read CLAUDE.md for project rules, ARCHITECTURE.md for current design
- Read the orchestrator code: backend/chat/orchestrator.py (will inject profile context + check cache)
- Read the session manager: backend/chat/session_manager.py (will add profile cleanup)
- Read the existing feedback system: backend/api/routes_feedback.py, session_manager feedback methods

Step 3.1: Profile Memory Store
- New module: backend/memory/
- user_profiles SQLite table (user_id, employment_type, salary_bracket, tenure_years, company, topics, preferences)
- Fact extraction via Haiku (best-effort, async, non-blocking)
- Profile injected into orchestrator system prompt
- GET/DELETE /api/profile/{user_id} endpoints
- 2-year retention, auto-cleanup

Step 3.2: Verified Q&A Cache
- New ChromaDB collection: verified_answers
- Two-tier thresholds from config.py (cache_high_threshold=0.95, cache_medium_threshold=0.88)
- Admin workflow: thumbs-up candidates → admin approval → cache
- Orchestrator checks cache before agentic loop — cache hit skips Claude API call
- Frontend: VerifiedAnswersTab.jsx in admin dashboard
- Admin API endpoints: GET/POST/DELETE /admin/verified-answers

Key decisions:
- Haiku calls are best-effort — on failure, log and proceed
- Thresholds are configurable via .env / config.py
- Profile facts merge with existing (don't overwrite good data with nulls)
- Cache similarity uses cosine distance from BGE embeddings (same model as document retrieval)

Implementation order:
1. Step 3.1 first (profile store + extraction + API endpoints + orchestrator integration)
2. Step 3.2 (semantic cache + admin workflow + orchestrator integration + frontend tab)

After implementation:
- Run full test suite: python -m pytest tests/ -v
- Secret scan (CLAUDE.md Rule 1)
- Update ARCHITECTURE.md: add memory module, profile table, verified_answers collection, new endpoints
```

---

## Phase 3 (PR 5): FAQ Pattern Detection

```
I'm implementing Step 3.3 (FAQ Pattern Detection) of the "Enhancing Chatbot" feature plan. Read the full plan first:

Plan/Planning/enhancing-chatbot/plan.md

Focus on Step 3.3 in the "Implementation Plan — Step-by-Step" section.

Context:
- Branch: feature/Enchancing_Chatbot
- Phases 1-3 (PR 1-4) are merged (full orchestrator, profile memory, verified Q&A cache all available)
- Read CLAUDE.md for project rules, ARCHITECTURE.md for current design
- Read backend/memory/semantic_cache.py (the verified answers system this builds on)
- Read backend/chat/session_manager.py (feedback and message data this analyzes)

Step 3.3: FAQ Pattern Detection
- Create backend/memory/faq_analyzer.py
  - analyze_query_patterns(days=30) — cluster recent queries by embedding similarity, return top clusters with counts
  - identify_gaps() — find queries with no results or thumbs-down, cluster them
- Add GET /admin/faq-patterns endpoint in backend/api/routes_admin.py
- Add FAQ patterns tab in frontend admin dashboard

This is the lightest PR. After implementation:
- Run full test suite: python -m pytest tests/ -v
- Secret scan (CLAUDE.md Rule 1)
- Update ARCHITECTURE.md: add FAQ analyzer to Component Map, new endpoint to API table
- Move Plan/Planning/enhancing-chatbot/ to Plan/Archive/enhancing-chatbot/ (feature complete)
```
