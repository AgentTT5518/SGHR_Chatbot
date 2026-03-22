# PR 4 Session Prompt — Profile Memory + Verified Q&A Cache

Copy everything below the line into a new Claude Code session.

---

I'm implementing Phase 3, Steps 3.1 and 3.2 of the "Enhancing Chatbot" feature plan — Profile Memory Store and Verified Q&A Cache.

## Setup

1. Read the full plan: `Plan/Planning/enhancing-chatbot/plan.md`
   - Focus on "Implementation Plan — Step-by-Step", Steps 3.1 and 3.2 (lines ~766–848)
2. Read `CLAUDE.md` for project rules (especially Rules 1–5)
3. Read `ARCHITECTURE.md` for current design (just updated with Phase 2 orchestrator)
4. Read existing code before modifying:
   - `backend/chat/orchestrator.py` — agentic loop (needs profile injection + cache check)
   - `backend/chat/context_manager.py` — SummaryBuffer (fact extraction pattern to reference)
   - `backend/chat/session_manager.py` — SQLite patterns (init_db, CRUD, cleanup_loop)
   - `backend/config.py` — settings (needs cache thresholds + profile config)
   - `backend/retrieval/vector_store.py` — ChromaDB wrapper (reference for verified_answers collection)
   - `backend/ingestion/embedder.py` — embedding model (reuse for cache embeddings)
   - `backend/api/routes_admin.py` — admin endpoints (needs verified answers CRUD)
   - `frontend/src/api/adminApi.js` — admin API calls (needs verified answers)
   - `frontend/src/pages/AdminDashboard.jsx` — admin dashboard (needs Verified Answers tab)
5. Create a new branch: `git checkout -b feature/enhancing-chatbot-memory`

## What to build

### Part A: Profile Memory Store (Step 3.1)

#### 1. Create `backend/memory/` module

- `backend/memory/__init__.py` — empty
- `backend/memory/profile_store.py`:
  - `user_profiles` table: `user_id TEXT PRIMARY KEY, employment_type TEXT, salary_bracket TEXT, tenure_years REAL, company TEXT, topics_json TEXT DEFAULT '[]', preferences_json TEXT DEFAULT '{}', created_at DATETIME, updated_at DATETIME`
  - `async def init_profile_db() -> None` — create table if not exists (call from app lifespan)
  - `async def get_profile(user_id: str) -> dict | None`
  - `async def upsert_profile(user_id: str, facts: dict) -> None` — merge new facts with existing (don't overwrite with nulls/empty)
  - `async def delete_profile(user_id: str) -> None`
  - `async def cleanup_stale_profiles(retention_years: int = 2) -> int` — delete profiles not updated in N years
  - Uses the same SQLite database as session_manager (`backend/data/sessions.db`)

- `backend/memory/fact_extractor.py`:
  - `async def extract_profile_facts(messages: list[dict], client: anthropic.AsyncAnthropic) -> dict` — call Haiku to extract employment_type, salary_bracket, tenure, company from conversation
  - Best-effort: returns empty dict on failure (same pattern as `context_manager.extract_facts`)
  - Called async after each conversation turn (non-blocking)

#### 2. Integrate into orchestrator

- On session start: load profile via `get_profile(user_id)`, inject as system prompt context: "Known user context: [employment_type], [salary_bracket], [tenure_years], [company]"
- After response completes: `asyncio.create_task(update_profile_from_conversation(user_id, messages, client))`
- Add helper `async def update_profile_from_conversation(user_id, messages, client)` — extracts facts, upserts profile

#### 3. Create `backend/api/routes_profile.py`

- `GET /api/profile/{user_id}` — return profile dict (for future settings page)
- `DELETE /api/profile/{user_id}` — delete profile (privacy compliance)
- Register in `backend/main.py`

#### 4. Add profile cleanup to lifespan

- Call `cleanup_stale_profiles()` in the existing cleanup loop or as a separate periodic task

### Part B: Verified Q&A Cache (Step 3.2)

#### 1. Create `backend/memory/semantic_cache.py`

- New ChromaDB collection: `verified_answers`
- Config thresholds in `backend/config.py`:
  - `cache_high_threshold: float = 0.95`
  - `cache_medium_threshold: float = 0.88`
- Dataclass `CacheResult(answer: str, sources: list, confidence: str, disclaimer: str | None)`
- `async def check_cache(query: str) -> CacheResult | None`:
  - Embed query using `backend/ingestion/embedder.py`
  - Search `verified_answers` collection
  - If similarity ≥ `cache_high_threshold`: return CacheResult with confidence="high", no disclaimer
  - If `cache_medium_threshold` ≤ similarity < `cache_high_threshold`: return CacheResult with confidence="medium", disclaimer="Based on a similar previously answered question..."
  - If < `cache_medium_threshold`: return None
- `async def add_verified_answer(question: str, answer: str, sources: list) -> str` — embed and store, return ID
- `async def remove_verified_answer(answer_id: str) -> None`
- `async def list_verified_answers() -> list[dict]` — return all cached answers

#### 2. Integrate into orchestrator

- Before starting the agentic loop, check semantic cache
- If cache hit: stream cached answer directly (skip Claude API call entirely), emit done with sources
- Log cache hits for observability

#### 3. Admin endpoints in `backend/api/routes_admin.py`

- `GET /admin/feedback/candidates` — returns thumbs-up answers not yet in cache (join feedback + messages)
- `POST /admin/verified-answers` — admin approves answer into cache (body: question, answer, sources)
- `DELETE /admin/verified-answers/{id}` — admin removes from cache
- `GET /admin/verified-answers` — list all cached answers

#### 4. Frontend: Verified Answers admin tab

- `frontend/src/api/adminApi.js` — add `fetchVerifiedAnswers()`, `addVerifiedAnswer()`, `deleteVerifiedAnswer()`, `fetchCacheCandidates()`
- `frontend/src/pages/AdminDashboard.jsx` — add "Verified Answers" tab
- The tab should show:
  - List of cached answers (question, answer preview, confidence, delete button)
  - "Candidates" section: thumbs-up answers that could be added to cache (with "Approve" button)

## Key constraints from the plan

- Profile facts merge with existing — never overwrite good data with nulls
- All Haiku calls are best-effort — on failure, log and continue
- Cache thresholds must be configurable via `.env` / `config.py`
- Profile auto-deletes after 2 years inactive
- High-confidence cache hit skips Claude API call entirely
- Medium-confidence hit returns answer with disclaimer text
- NEVER log PII (Rule 3)

## Existing code to reference (not modify unless integrating)

- `backend/chat/orchestrator.py` — integration point for profile + cache
- `backend/chat/context_manager.py` — `extract_facts()` pattern to follow for `fact_extractor.py`
- `backend/chat/session_manager.py` — SQLite CRUD patterns, `init_db()`, `cleanup_loop()`
- `backend/retrieval/vector_store.py` — ChromaDB wrapper patterns for `verified_answers` collection
- `backend/ingestion/embedder.py` — `get_model()`, `encode()` for cache embeddings

## Testing rules

- Write tests in `tests/` mirroring the module structure:
  - `tests/memory/__init__.py`
  - `tests/memory/test_profile_store.py` — CRUD, merge logic, stale cleanup
  - `tests/memory/test_fact_extractor.py` — mock Haiku, verify extraction
  - `tests/memory/test_semantic_cache.py` — mock ChromaDB, test two-tier thresholds, add/remove
  - `tests/api/test_routes_profile.py` — profile API endpoints
  - Update `tests/api/test_routes_admin.py` — verified answers CRUD endpoints
- Use the project logger (`backend/lib/logger.py`), never bare `print()`
- Run tests after each step: `python -m pytest tests/ -v`
- Mock Anthropic client and ChromaDB in tests
- Test scenarios:
  1. Profile CRUD: create, read, update (merge), delete
  2. Fact extraction: Haiku returns valid JSON, Haiku fails gracefully
  3. Profile merge: new facts merge without overwriting existing non-null values
  4. Stale cleanup: profiles older than retention period deleted
  5. Cache hit (high confidence): returns answer, skips Claude
  6. Cache hit (medium confidence): returns answer with disclaimer
  7. Cache miss: returns None, falls through to orchestrator
  8. Cache add/remove: verified answers stored and retrievable
  9. Admin endpoints: candidates, approve, list, delete

## Scope boundaries — HARD STOP

- Do NOT modify tool implementations (`retrieval_tools.py`, `calculation_tools.py`, `routing_tools.py`)
- Do NOT modify `session_manager.py` schema (only add profile table via `profile_store.py`)
- Do NOT build Phase 3C (FAQ pattern detection) — that's PR 5
- Do NOT modify files outside scope without asking (CLAUDE.md Rule 5)
- Files to create/modify:
  - **Create:** `backend/memory/__init__.py`
  - **Create:** `backend/memory/profile_store.py`
  - **Create:** `backend/memory/fact_extractor.py`
  - **Create:** `backend/memory/semantic_cache.py`
  - **Create:** `backend/api/routes_profile.py`
  - **Modify:** `backend/chat/orchestrator.py` (profile injection + cache check)
  - **Modify:** `backend/config.py` (cache thresholds, profile settings)
  - **Modify:** `backend/main.py` (register profile routes, init profile db)
  - **Modify:** `backend/api/routes_admin.py` (verified answers CRUD)
  - **Modify:** `frontend/src/api/adminApi.js` (verified answers API calls)
  - **Modify:** `frontend/src/pages/AdminDashboard.jsx` (Verified Answers tab)

## Before committing

- Run full test suite: `python -m pytest tests/ -v`
- Run secret scan (CLAUDE.md Rule 1)
- Run linting: `ruff check backend/`
- Run type check: `python -m mypy backend/`
- Run frontend lint: `cd frontend && npm run lint`
- Update `ARCHITECTURE.md` Feature Log + Component Map + Data Model
