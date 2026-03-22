# Feature Requirements: Enhancing Chatbot — Tools, Memory & Orchestration

**Status:** Complete
**Completed:** 2026-03-21
**Branch:** `feature/Enchancing_Chatbot`

---

## Phase 1: Foundation (Session Memory + Token Budget)

### 1A. Token Budget Manager

| # | Requirement | Status |
|---|-------------|--------|
| 1A-1 | Token counting via Anthropic `count_tokens()` API (accurate) | ✅ |
| 1A-2 | Fallback to tiktoken `cl100k_base` with 15% safety margin if API unreachable | ✅ |
| 1A-3 | Budget enforcement: reserve 4096 tokens for output, cap input at `context_window - 4096` | ✅ |
| 1A-4 | 40/60 split between history and retrieval context | ✅ |

### 1B. Session Memory with SummaryBuffer

| # | Requirement | Status |
|---|-------------|--------|
| 1B-1 | Recent messages (last 3-5 pairs) kept verbatim | ✅ |
| 1B-2 | Older messages compressed into running summary via Haiku | ✅ |
| 1B-3 | Key facts extracted per session (employment type, salary, tenure) | ✅ |
| 1B-4 | `session_summary` and `session_facts_json` columns in sessions table | ✅ |
| 1B-5 | Summary update triggered only when message count exceeds verbatim window (> 3 pairs) | ✅ |
| 1B-6 | Summary injected as system prompt appendix (not fake messages) | ✅ |
| 1B-7 | Haiku failures are best-effort — log error, proceed without enhancement | ✅ |

### 1C. Persistent User ID

| # | Requirement | Status |
|---|-------------|--------|
| 1C-1 | Frontend: `user_id` stored in `localStorage` (persists across sessions) | ✅ |
| 1C-2 | `session_id` remains in `sessionStorage` (per conversation) | ✅ |
| 1C-3 | `user_id` column added to sessions table | ✅ |
| 1C-4 | `user_id` sent in POST `/api/chat` body | ✅ |

---

## Phase 2: Tool-Augmented Orchestration

### 2A. Tool Registry

| # | Requirement | Status |
|---|-------------|--------|
| 2A-1 | Tool schemas follow Anthropic format (3-4 sentence descriptions, when-to-use / when-not-to-use) | ✅ |
| 2A-2 | Registry maps tool names to async callables | ✅ |
| 2A-3 | 8 tools registered total | ✅ |

### 2B. Retrieval Tools

| # | Requirement | Status |
|---|-------------|--------|
| 2B-1 | `search_employment_act` — semantic + keyword over EA collection | ✅ |
| 2B-2 | `search_mom_guidelines` — semantic + keyword over MOM collection | ✅ |
| 2B-3 | `search_all_policies` — search both collections | ✅ |
| 2B-4 | `get_legal_definitions` — fetch Section 2 definitions | ✅ |
| 2B-5 | Each tool returns formatted context with source citations | ✅ |

### 2C. Calculation Tools

| # | Requirement | Status |
|---|-------------|--------|
| 2C-1 | `calculate_leave_entitlement` — annual, sick, maternity, paternity, childcare based on tenure/type/salary | ✅ |
| 2C-2 | `calculate_notice_period` — based on service length and contract terms | ✅ |
| 2C-3 | All calculations are deterministic Python (no LLM arithmetic) | ✅ |
| 2C-4 | Rules derived from EA sections s43/s89/Part IX, documented in code | ✅ |

### 2D. Routing Tools

| # | Requirement | Status |
|---|-------------|--------|
| 2D-1 | `check_eligibility` — EA Part IV salary thresholds | ✅ |
| 2D-2 | `escalate_to_hr` — logs to SQLite escalations table, returns acknowledgement | ✅ |
| 2D-3 | Escalations viewable via `GET /admin/escalations` | ✅ |

### 2E. Orchestration Loop

| # | Requirement | Status |
|---|-------------|--------|
| 2E-1 | Agentic loop: send message + tools → detect `tool_use` → dispatch → loop | ✅ |
| 2E-2 | Streaming throughout all iterations (no double API call) | ✅ |
| 2E-3 | Status SSE events emitted before each tool dispatch | ✅ |
| 2E-4 | Max 5 iterations with graceful fallback message | ✅ |
| 2E-5 | Feature flag (`use_orchestrator`) for legacy RAG fallback | ✅ |
| 2E-6 | Source extraction from tool results | ✅ |
| 2E-7 | Frontend renders thinking steps as status messages | ✅ |

### 4C. Metadata Filtering (shipped with Phase 2)

| # | Requirement | Status |
|---|-------------|--------|
| 4C-1 | `section_filter` parameter on retrieval tools passes through as ChromaDB `where` clause | ✅ |
| 4C-2 | No filter returns all matching chunks (existing behaviour preserved) | ✅ |
| 4C-3 | Invalid filter falls back to unfiltered search | ✅ |

---

## Phase 3: Profile & Semantic Memory

### 3A. Profile Memory

| # | Requirement | Status |
|---|-------------|--------|
| 3A-1 | `user_profiles` SQLite table with employment facts | ✅ |
| 3A-2 | Haiku-based fact extraction from conversations (async, best-effort) | ✅ |
| 3A-3 | Merge-without-overwrite upsert (new nulls don't erase existing data) | ✅ |
| 3A-4 | Auto-delete profiles inactive for 2 years | ✅ |
| 3A-5 | User can view profile via `GET /api/profile/{user_id}` | ✅ |
| 3A-6 | User can delete profile via `DELETE /api/profile/{user_id}` | ✅ |
| 3A-7 | Profile context injected into orchestrator system prompt | ✅ |

### 3B. Verified Q&A Cache

| # | Requirement | Status |
|---|-------------|--------|
| 3B-1 | ChromaDB `verified_answers` collection for semantic cache | ✅ |
| 3B-2 | High-confidence match (≥ 0.95) returns answer without Claude API call | ✅ |
| 3B-3 | Medium-confidence match (0.88–0.94) returns answer with disclaimer | ✅ |
| 3B-4 | Low similarity (< 0.88) falls through to normal orchestration | ✅ |
| 3B-5 | Thresholds configurable via `.env` / `config.py` | ✅ |
| 3B-6 | Admin CRUD: `GET/POST/DELETE /admin/verified-answers` | ✅ |
| 3B-7 | `GET /admin/feedback/candidates` — thumbs-up answers not yet in cache | ✅ |
| 3B-8 | Frontend Verified Answers admin tab | ✅ |

### 3C. FAQ Pattern Detection

| # | Requirement | Status |
|---|-------------|--------|
| 3C-1 | DBSCAN clustering on BGE embeddings to identify question patterns | ✅ |
| 3C-2 | Top query patterns (frequent clusters) surfaced to admin | ✅ |
| 3C-3 | Knowledge gaps (thumbs-down + escalation clusters) identified | ✅ |
| 3C-4 | `GET /admin/faq-patterns` endpoint with `days` parameter | ✅ |
| 3C-5 | Frontend FAQ Patterns admin tab with days selector | ✅ |

---

## Deferred

| Phase | Description | Reason |
|-------|-------------|--------|
| 4A | Query Expansion (MultiQuery pattern) | Deferred until retrieval quality metrics justify the overhead |
| 4B | Contextual Compression | Deferred until retrieval quality metrics justify the overhead |

---

## API Endpoints Added

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/escalations` | Paginated escalation records (filterable by status) |
| GET | `/api/profile/{user_id}` | User profile data |
| DELETE | `/api/profile/{user_id}` | Delete user profile (privacy) |
| GET | `/admin/verified-answers` | List cached verified answers |
| POST | `/admin/verified-answers` | Add verified answer to cache |
| DELETE | `/admin/verified-answers/{id}` | Remove verified answer |
| GET | `/admin/feedback/candidates` | Thumbs-up answers not yet cached |
| GET | `/admin/faq-patterns` | Top query clusters + knowledge gaps |

---

## Key Files Created

| File | Purpose |
|------|---------|
| `backend/chat/token_budget.py` | Token counting and budget enforcement |
| `backend/chat/context_manager.py` | SummaryBuffer logic, context assembly |
| `backend/chat/orchestrator.py` | Agentic tool-use loop with streaming |
| `backend/chat/tools/registry.py` | Tool schemas and dispatch map |
| `backend/chat/tools/retrieval_tools.py` | 4 retrieval tools |
| `backend/chat/tools/calculation_tools.py` | 2 calculation tools |
| `backend/chat/tools/routing_tools.py` | 2 routing tools |
| `backend/memory/profile_store.py` | User profile CRUD |
| `backend/memory/fact_extractor.py` | Haiku-based fact extraction |
| `backend/memory/semantic_cache.py` | Verified Q&A cache |
| `backend/memory/faq_analyzer.py` | DBSCAN query clustering |
| `backend/api/routes_profile.py` | Profile endpoints |
