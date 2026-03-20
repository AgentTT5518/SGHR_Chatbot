# PR 2 Session Prompt — Tool Registry + All Tools + Metadata Filtering

Copy everything below the line into a new Claude Code session.

---

I'm implementing Phase 2 (Steps 2.1–2.4 + 4C) of the "Enhancing Chatbot" feature plan.

## Setup

1. Read the full plan: `Plan/Planning/enhancing-chatbot/plan.md`
   - Focus on "Implementation Plan — Step-by-Step", Steps 2.1 through 2.4 plus Step 4C
2. Read `CLAUDE.md` for project rules (especially Rules 1–5)
3. Read `ARCHITECTURE.md` for current design (just updated with Phase 1)
4. Read the existing retrieval code before modifying:
   - `backend/retrieval/retriever.py`
   - `backend/retrieval/vector_store.py`
   - `backend/retrieval/keyword_search.py`
   - `backend/chat/prompts.py`
5. Create a new branch: `git checkout -b feature/enhancing-chatbot-tools`

## What to build

Phase 2 PR 2 has 5 steps. Build 2.1 first, then 2.2/2.3/2.4/4C can be done in parallel:

### Step 2.1: Tool Registry & Schema Definitions
- Create `backend/chat/tools/__init__.py` (empty)
- Create `backend/chat/tools/registry.py`:
  - `TOOL_SCHEMAS: list[dict]` — Anthropic tool format definitions
  - `TOOL_DISPATCH: dict[str, Callable]` — maps tool name → async handler
  - `async def dispatch_tool(name: str, input: dict) -> str`
  - `def get_all_schemas() -> list[dict]`
- Each tool description: 3-4 sentences, clear when-to-use / when-NOT-to-use

### Step 2.2: Retrieval Tools
- Create `backend/chat/tools/retrieval_tools.py`
- Refactor `backend/retrieval/retriever.py` — expose `retrieve_from_collection(query, collection, n, section_filter)` for per-collection search
- Implement 4 tool handlers: `search_employment_act`, `search_mom_guidelines`, `search_all_policies`, `get_legal_definitions`
- Each returns formatted text with source citations

### Step 2.3: Calculation Tools
- Create `backend/chat/tools/calculation_tools.py`
- `calculate_leave_entitlement(tenure_years, employment_type, leave_type)` — annual, sick, maternity, paternity, childcare
- `calculate_notice_period(tenure_years, contract_notice)` — EA s10 brackets
- `EA_RULES_VERSION = "2025-01"` constant
- All calculations deterministic Python, every result cites EA section

### Step 2.4: Routing Tools
- Create `backend/chat/tools/routing_tools.py`
- `check_eligibility(salary_monthly, role, employment_type)` — EA Part IV salary thresholds
- `escalate_to_hr(reason, session_id)` — log to new `escalations` SQLite table, return reference ID
- Add `escalations` table to `session_manager.py` schema (with migration)
- Add `GET /admin/escalations` endpoint to `routes_admin.py`

### Step 4C: Metadata Filtering
- Modify `backend/retrieval/vector_store.py` — pass where-clauses to ChromaDB
- Modify `backend/retrieval/retriever.py` — accept optional `section_filter` param
- Used by `search_employment_act` tool's `section_filter` parameter

## Key decisions (already made — do not revisit)
- Tool descriptions: 3-4 sentences following Anthropic best practices
- Calculation rules: Hardcoded from Employment Act. `EA_RULES_VERSION = "2025-01"`. Every result cites the EA section
- Escalation: MVP is a SQLite log entry visible in admin dashboard. Stub a notification hook for future email/Slack
- Metadata filtering: ChromaDB where-clause passthrough, used by `search_employment_act`'s `section_filter` param

## Implementation order
1. Step 2.1 first (registry is needed by all tools)
2. Steps 2.2, 2.3, 2.4, 4C in parallel
3. Register all tools in `registry.py` at the end

## Testing rules
- Write tests in `tests/` mirroring the module structure (e.g. `tests/chat/tools/test_registry.py`)
- Use the project logger (`backend/lib/logger.py`), never bare `print()`
- Run tests after each step: `python -m pytest tests/ -v`
- There's a `tests/conftest.py` that mocks `SentenceTransformer` at session scope — don't remove it
- Mock `vector_store.query` in retrieval tool tests (don't need real ChromaDB)

## Scope boundaries — HARD STOP
- Do NOT build the orchestrator (Step 2.5) — that's PR 3
- Do NOT modify `rag_chain.py` or `routes_chat.py` — this PR only creates and tests the tools
- Do NOT modify files outside scope without asking (CLAUDE.md Rule 5)
- The only existing files that should be modified are:
  - `backend/retrieval/retriever.py` (expose per-collection functions)
  - `backend/retrieval/vector_store.py` (where-clause support)
  - `backend/chat/session_manager.py` (escalations table)
  - `backend/api/routes_admin.py` (escalations endpoint)

## Before committing
- Run full test suite: `python -m pytest tests/ -v`
- Run secret scan (CLAUDE.md Rule 1)
- Run linting: `ruff check backend/`
- Run type check: `python -m mypy backend/`
- Update `ARCHITECTURE.md` Feature Log + Component Map
