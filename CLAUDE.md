# CLAUDE.md — SGHR Chatbot

## Project Identity
| Field | Value |
|-------|-------|
| Name | SGHR Chatbot |
| Description | RAG-powered HR assistant that answers Singapore Employment Act and MOM guideline questions for employees and HR managers |
| Backend | Python 3.11 · FastAPI · Uvicorn |
| Frontend | React 19 · Vite · JavaScript |
| AI Provider | Anthropic Claude (claude-sonnet-4-6) |
| Vector Store | ChromaDB (local) |
| Embeddings | BAAI/bge-base-en-v1.5 (sentence-transformers) |
| Database | SQLite via aiosqlite (sessions) |
| Auth | None (session ID via UUID) |
| Package Manager | pip (backend) · npm (frontend) |
| Test Runner | pytest |
| Deployment | Local / TBD |
| Dev Server Port | Backend: 8000 · Frontend: 5170 |

## Commands
```bash
# Backend
uvicorn backend.main:app --reload --port 8000   # Start dev server
python -m pytest tests/ -v                       # Run tests
ruff check backend/                              # Lint
python -m mypy backend/                          # Type check
python -m backend.ingestion.ingest_pipeline      # Re-ingest knowledge base

# Frontend (from frontend/)
npm run dev           # Start Vite dev server
npm run build         # Production build
npm run lint          # ESLint check
```

## Project Structure
```
backend/
  api/                # FastAPI route handlers
    routes_chat.py    # POST /api/chat (SSE), session management
    routes_admin.py   # Admin/ingestion endpoints
  chat/               # Core RAG logic
    rag_chain.py      # Retrieval + Claude streaming
    session_manager.py # SQLite session CRUD
    prompts.py        # System prompt builders
  ingestion/          # Knowledge base pipeline
    ingest_pipeline.py
    embedder.py       # BGE model wrapper
    chunker.py
    scraper_*.py      # MOM / Employment Act scrapers
  retrieval/          # Vector search
    retriever.py
    vector_store.py   # ChromaDB wrapper
  lib/                # Shared utilities
    logger.py         # Structured logger factory (Rule 3)
  config.py           # Pydantic settings (reads .env)
  main.py             # FastAPI app + lifespan
frontend/
  src/                # React components + pages
docs/
  brand/              # Brand voice, style, tone matrix
  requirements/       # Feature specs
  decisions/          # Architecture Decision Records
tests/                # Mirrors backend/ structure
  test-results/       # Test run logs (gitignored)
```

## Code Conventions
- Type hints on all function signatures
- `async/await` throughout backend (FastAPI + aiosqlite)
- Every `except` block uses `log.error()` — never bare `print()`
- Use project logger (`backend/lib/logger.py`), never `print()` in production
- Pydantic models for all API request/response shapes
- File naming: `snake_case` for Python, `kebab-case` for frontend files
- No secrets in code — all config via `.env` + `backend/config.py`

## Git Workflow
- Branches: `feature/[short-desc]`, `fix/[short-desc]`
- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`
- Never commit to `main` directly
- Run full test suite before every commit

### Parallel Development (2+ developers on same repo)
- Use git worktrees: `git worktree add ../project-[feature] feature/[name]`
- One Claude Code session per worktree — never share
- **Shared contracts first** — agree on types/interfaces, merge to `main` before feature work
- **Lock shared resources** — only one person modifies `backend/api/` routes or migrations at a time
- Rebase on `main` before opening PR
- Full guide: `docs/parallel-development.md`

## Secret Patterns
```
SECRET_SCAN_PATTERNS="sk-ant-\|sk-[a-zA-Z0-9]\{20,\}\|AKIA[A-Z0-9]\{16\}\|ghp_[A-Za-z0-9]\{36\}\|ANTHROPIC_API_KEY\s*=\s*sk\|Bearer \|password\s*="
```

---

## MANDATORY RULES

### Rule 1: Secret Protection
Before every commit, scan for exposed secrets:
```bash
grep -rn "sk-ant-\|sk-[a-zA-Z0-9]\{20,\}\|AKIA[A-Z0-9]\{16\}\|ghp_[A-Za-z0-9]\{36\}\|ANTHROPIC_API_KEY\s*=\s*sk\|Bearer \|password\s*=" \
  --include="*.py" --include="*.js" --include="*.jsx" --include="*.ts" --include="*.json" \
  backend/ frontend/src/ . 2>/dev/null | grep -v node_modules | grep -v ".env.example"
```
- All secrets in `.env` only (never committed)
- `.env` MUST be in `.gitignore` — `.env.example` must list all required vars with placeholders
- Secrets only in `backend/config.py` via `pydantic-settings` — never hardcoded
- New env vars → add placeholder to `.env.example` immediately
- **If a secret is detected, STOP. Do not commit. Alert the user.**

### Rule 2: Test & Review Every Feature
- Write tests in `tests/` mirroring the module structure
- Run before every commit and save results:
  ```bash
  python -m pytest tests/ -v 2>&1 | tee tests/test-results/$(date +%Y%m%d-%H%M%S).log
  ```
- Test result logs saved to `tests/test-results/` (gitignored)
- Self-review checklist:
  - Matches requirements in `docs/requirements/`?
  - All new code paths tested? Error cases handled?
  - No hardcoded config values? No bare `print()` in production?
  - Secret scan passed (Rule 1)?
- **If tests fail, fix before moving on. Never skip.**

### Rule 3: Error Logging
- Logger factory lives at `backend/lib/logger.py`
- **Every module MUST import the scoped logger:**
  ```python
  # backend/chat/rag_chain.py
  from backend.lib.logger import get_logger
  log = get_logger("chat.rag_chain")
  ```
- Every `except` block → `log.error("description", exc_info=True)`
- Every API route → log entry + errors
- Every external service call (Claude API, ChromaDB) → log failures with context
- NEVER log the Anthropic API key or user PII
- No bare `print()` in production code (startup messages are exempt during lifespan)

### Rule 4: Update ARCHITECTURE.md After Every Feature
- Lives at project root
- After each feature: update Component Map, API Endpoints, Feature Log
- Always update "Last updated" date

### Rule 5: Feature Boundary — HARD BLOCK
**NEVER edit files outside the current module without user approval.**
- ONLY modify files within the current backend module or frontend component freely
- ASK before touching: other modules, `backend/config.py`, `backend/main.py`, `requirements.txt`, `frontend/package.json`, DB schemas
- Use this format:
  ```
  BOUNDARY ALERT
  File:   [path]
  Reason: [why]
  Change: [what]
  Risk:   [Low/Med/High]
  Proceed? (yes/no)
  ```

---

## Feature Workflow
```
1. BOUNDARY  -> Identify which module/component this feature lives in
2. PLAN      -> Create Plan/Planning/[feature]/ folder
              -> Copy docs/templates/plan-template.md to Plan/Planning/[feature]/plan.md
              -> Iterate on plan with Claude — save progress to plan.md
3. REVIEW    -> User reviews plan.md, adds comments/feedback
              -> Resolve open questions, finalize approach
4. APPROVE   -> User gives go-ahead to start development
5. DESIGN    -> Update ARCHITECTURE.md with planned changes
6. BUILD     -> Implement + tests + logger (ask before cross-boundary edits)
7. TEST      -> Secret scan + tests + self-review checklist
8. COMPLETE  -> Finalize docs/requirements/[feature].md (from plan)
              -> Finalize docs/decisions/[feature].md (from plan decisions)
              -> Update ARCHITECTURE.md Feature Log
              -> Move Plan/Planning/[feature]/ to Plan/Archive/[feature]/
9. COMMIT    -> Conventional commit -> push feature branch -> PR
```

## Command Policy Overrides
| Command | Default Tier | Project Tier | Reason |
|---------|-------------|-------------|--------|
| `git status / log / diff` | 1 | 1 | Read-only |
| `pytest` / `ruff check` / `mypy` | 1 | 1 | Safe analysis |
| `npm run dev / build / lint` | 1 | 1 | Safe local ops |
| `git add / commit` | 2 | 2 | Requires confirmation |
| `git push` | 2 | 2 | Requires confirmation |
| `pip install` | 2 | 2 | Supply chain risk |
| `rm -rf` / `git push --force` / `git reset --hard` | 3 | 3 | Prohibited |

## Reference Docs
- `ARCHITECTURE.md` — Living system design
- `docs/github-workflow-guide.md` — Step-by-step feature development workflow
- `docs/parallel-development.md` — Multi-developer worktree workflow
- `docs/project-setup-guide.md` — Decision guide for artifact selection (skills, evals, brand docs)
- `docs/skills-guide.md` — How to create custom Claude Code skills
- `docs/evals-guide.md` — How to set up AI output quality testing
- `docs/brand-voice-guide.md` — How to define writing style and brand voice
- `docs/command-policy.md` — Command permission tiers for Claude Code operations
- `docs/brand/BRAND-PROFILE.md` — Product identity and voice
- `docs/brand/STYLE-GUIDE.md` — Writing rules for AI responses
- `docs/brand/TONE-MATRIX.md` — Tone adjustments by context
- `Plan/Planning/` — Active feature plans (working drafts)
- `Plan/Archive/` — Completed feature plans
- `docs/templates/plan-template.md` — Plan file template
- `docs/requirements/` — Finalized feature specs (written on completion)
- `docs/decisions/` — Finalized Architecture Decision Records (written on completion)
- `docs/templates/FEATURE-CLAUDE.md` — Feature boundary template
- `docs/templates/skill-template.md` — Custom skill starter file
- `docs/templates/eval-template/` — Eval test structure starter (rubric + test cases)
- `docs/templates/brand/` — Brand identity, style guide, and tone matrix templates
- `backend/lib/logger.py` — Structured logger
- `docs/templates/logger-template.py` — Python logger template
- `.claude/settings.json` — Command permission policy
- `.claude/commands/project-setup.md` — Interactive project setup skill (`/project-setup`)
