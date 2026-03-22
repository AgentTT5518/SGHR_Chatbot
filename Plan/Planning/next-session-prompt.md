# Next Session Prompt — Post Auth, Testing & Tuning

Copy everything below the line into a new Claude Code session.

---

The "Auth Hardening, Testing Improvements & Retrieval Tuning" feature is **fully complete**. PR #13 merged.

| PR | Feature | Status |
|----|---------|--------|
| PR 1–6 | Enhancing Chatbot (Phases 1–4B) | Merged |
| PR 13 | Auth Hardening + Testing + Retrieval Tuning | Merged |

## Current system capabilities

- **Agentic tool-use orchestrator** with 8 tools (retrieval, calculation, routing)
- **Session memory** with SummaryBuffer (Haiku compression) + token budget manager
- **Profile memory** — cross-session user profile extraction + injection
- **Verified Q&A cache** — semantic cache with two-tier confidence matching
- **FAQ pattern detection** — DBSCAN clustering for admin dashboard
- **Query expansion** — Haiku rephrasings for HR synonym coverage (toggleable)
- **Contextual compression** — embedding similarity filtering (toggleable)
- **Hybrid retrieval** — semantic + TF-IDF + RRF with metadata filtering
- **Admin dashboard** — feedback, escalations, verified answers, FAQ patterns tabs
- **HMAC session signing** — server-generated, tamper-proof session IDs
- **Admin API key auth** — all /admin/* and /metrics protected with audit logging
- **Route protection** — profile ownership, session validation, feedback checks
- **Per-session rate limiting** — composite key (session token → IP fallback)
- **Env-based deployment config** — CORS origins, HTTPS redirect, environment toggle
- **468 passing tests** — unit, integration, auth, orchestrator
- **Retrieval eval framework** — 55 labelled queries, keyword recall metrics
- **Load testing** — Locust setup with SSE consumption
- **Parameter sweep** — two-stage (45 fast + 15 expansion) retrieval tuning

## Finalization done

- `docs/requirements/auth-testing-tuning.md` — Feature requirements doc
- `docs/decisions/auth-testing-tuning.md` — 9 Architecture Decision Records
- `Plan/Archive/auth-testing-tuning/` — Full plan archived
- `ARCHITECTURE.md` — Up to date with all features

## Operational tasks (require running server + ingested data)

1. **Run retrieval baseline** — `python -m tests.eval.eval_retrieval`
2. **Run parameter sweep** — `python -m tests.eval.sweep`
3. **Apply optimal settings** — Update config.py defaults from sweep results
4. **Flip session signing enforcement** — Set `SESSION_SIGNING_ENFORCED=true` after one release cycle

## What to work on next

Pick based on priorities:

1. **Real user authentication** — Move beyond anonymous sessions
   - JWT or OAuth2 with actual user accounts
   - Per-user rate limiting tied to authenticated identity
   - Role-based access (employee vs HR vs admin)
   - Password hashing, registration, login flow

2. **Production deployment**
   - Docker containerization
   - Production database (PostgreSQL replacing SQLite)
   - CI/CD pipeline for staging → prod
   - Monitoring & alerting (Prometheus + Grafana)
   - Log aggregation

3. **New features** — Check with user for priorities
   - Document upload (user provides employment contract for context)
   - Multi-language support (common Singapore languages)
   - Email/export conversation history
   - Notification system for escalations
   - Conversation analytics dashboard
