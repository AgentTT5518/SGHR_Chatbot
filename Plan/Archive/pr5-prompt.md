# PR 5 Session Prompt — FAQ Pattern Detection

Copy everything below the line into a new Claude Code session.

---

I'm implementing Phase 3, Step 3.3 of the "Enhancing Chatbot" feature plan — FAQ Pattern Detection.

## Setup

1. Read the full plan: `Plan/Planning/enhancing-chatbot/plan.md`
   - Focus on "Implementation Plan — Step-by-Step", Step 3.3 (search for "Step 3.3" heading)
2. Read `CLAUDE.md` for project rules (especially Rules 1–5)
3. Read `ARCHITECTURE.md` for current design (just updated with Phase 3 memory/cache)
4. Read existing code before modifying:
   - `backend/memory/semantic_cache.py` — verified answers cache (reference for ChromaDB embedding queries)
   - `backend/chat/session_manager.py` — SQLite queries (messages + feedback tables for pattern analysis)
   - `backend/ingestion/embedder.py` — embedding model (reuse for query clustering)
   - `backend/retrieval/vector_store.py` — ChromaDB wrapper (reference patterns)
   - `backend/api/routes_admin.py` — admin endpoints (add FAQ patterns endpoint)
   - `backend/config.py` — settings (if any new config needed)
   - `frontend/src/api/adminApi.js` — admin API calls (add FAQ patterns)
   - `frontend/src/pages/AdminDashboard.jsx` — admin dashboard (add FAQ Patterns tab)
5. Create a new branch: `git checkout -b feature/enhancing-chatbot-faq`

## What to build

### 1. Create `backend/memory/faq_analyzer.py`

- `async def analyze_query_patterns(days: int = 30) -> list[dict]`:
  - Fetch user messages from the last N days from SQLite
  - Embed all queries using `backend/ingestion/embedder.py`
  - Cluster by embedding similarity using DBSCAN from scikit-learn (preferred over agglomerative because it auto-detects cluster count; use `eps=0.3` on cosine distance, `min_samples=2`, `metric="cosine"`)
  - Cap at most recent 500 user messages to prevent embedding timeouts
  - Return top 10 clusters sorted by frequency: `[{"cluster_id": int, "count": int, "representative_query": str, "sample_queries": list[str]}]`

- `async def identify_gaps(days: int = 30) -> list[dict]`:
  - Find queries that got thumbs-down feedback OR that triggered an escalation (join `feedback` table with `rating='down'` and `escalations` table)
  - For thumbs-down: join `feedback` → `messages` to get the user query preceding the rated assistant message
  - For escalations: join `escalations` → `messages` to get user queries from escalated sessions
  - Cluster those "gap" queries by embedding similarity (same DBSCAN params)
  - Return clusters: `[{"cluster_id": int, "count": int, "representative_query": str, "sample_queries": list[str], "gap_type": "thumbs_down" | "escalation"}]`

- Use `backend/lib/logger.py` for all logging

### 2. Add admin endpoint in `backend/api/routes_admin.py`

- `GET /admin/faq-patterns?days=30` — returns `{"top_patterns": [...], "knowledge_gaps": [...]}`
- Use rate limiting (existing `admin_rate_limit`)

### 3. Add frontend FAQ Patterns tab

- `frontend/src/api/adminApi.js` — add `fetchFaqPatterns(days)`
- `frontend/src/pages/AdminDashboard.jsx` — add "FAQ Patterns" tab showing:
  - **Top Question Clusters**: table with representative query, count, sample queries (expandable)
  - **Knowledge Gaps**: table with gap type, representative query, count, samples
  - A "days" selector (7, 14, 30, 60) to adjust the analysis window
  - A "Refresh" button to re-run analysis

### 4. Dependencies check

- scikit-learn is already in requirements.txt (used by keyword_search.py for TF-IDF)
- numpy is already available
- No new dependencies should be needed

### 5. Frontend testing

- No frontend component tests required for this PR
- Manual verification: confirm the FAQ Patterns tab renders, days selector works, refresh button triggers reload

## Key constraints from the plan

- Clustering must work with small datasets (< 10 queries) — handle gracefully
- Performance: embedding many queries can be slow — consider caching or limiting to last N queries
- The endpoint may be slow (embedding + clustering) — consider running in background or adding a loading state
- NEVER log PII (Rule 3) — log cluster stats, not actual query text
- This is an analytics/admin-only feature — no impact on the chat flow

## Existing code to reference (not modify unless integrating)

- `backend/memory/semantic_cache.py` — ChromaDB embedding query patterns
- `backend/chat/session_manager.py` — SQLite message queries
- `backend/ingestion/embedder.py` — `embed_query()`, `embed_documents()`
- `backend/retrieval/keyword_search.py` — scikit-learn usage patterns in the project

## Testing rules

- Write tests in `tests/` mirroring the module structure:
  - `tests/memory/test_faq_analyzer.py` — mock SQLite data, mock embedder, verify clustering
  - Update `tests/api/test_routes_admin.py` — FAQ patterns endpoint
- Mock the embedder and SQLite queries in tests
- Test scenarios:
  1. Empty messages — returns empty patterns
  2. Few messages (< 3) — returns patterns without clustering errors
  3. Normal case — returns top clusters sorted by count
  4. Knowledge gaps — queries with thumbs-down feedback clustered
  5. Days parameter — filters by date range
  6. Admin endpoint returns expected structure

## Scope boundaries — HARD STOP

- Do NOT modify tool implementations
- Do NOT modify the orchestrator or chat flow
- Do NOT modify `session_manager.py` schema (read-only queries against existing tables)
- Do NOT modify files outside scope without asking (CLAUDE.md Rule 5)
- Files to create/modify:
  - **Create:** `backend/memory/faq_analyzer.py`
  - **Modify:** `backend/api/routes_admin.py` (add FAQ patterns endpoint)
  - **Modify:** `frontend/src/api/adminApi.js` (add FAQ patterns API call)
  - **Modify:** `frontend/src/pages/AdminDashboard.jsx` (add FAQ Patterns tab)

## Before committing

- Run full test suite: `python -m pytest tests/ -v`
- Run secret scan (CLAUDE.md Rule 1)
- Run linting: `ruff check backend/`
- Run type check: `python -m mypy backend/`
- Run frontend lint: `cd frontend && npm run lint`
- Update `ARCHITECTURE.md` Feature Log + Component Map
