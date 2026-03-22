# Next Session Prompt — Post Enhancing Chatbot

Copy everything below the line into a new Claude Code session.

---

The "Enhancing Chatbot" feature is **fully complete** including Phase 4A/4B. All 6 PRs have been merged:

| PR | Phase | Status |
|----|-------|--------|
| PR 1 | Phase 1: Token budget + SummaryBuffer + persistent user ID | Merged |
| PR 2 | Phase 2A-2D + 4C: Tool registry + all tools + metadata filtering | Merged |
| PR 3 | Phase 2E: Orchestrator + frontend thinking UX | Merged |
| PR 4 | Phase 3A-3B: Profile memory + verified Q&A cache | Merged |
| PR 5 | Phase 3C: FAQ pattern detection | Merged |
| PR 6 | Phase 4A/4B: Query expansion + contextual compression | Merged |

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

## Finalization done

- `docs/requirements/enhancing-chatbot.md` — Feature requirements doc (complete)
- `docs/decisions/enhancing-chatbot.md` — 12 Architecture Decision Records
- `Plan/Archive/enhancing-chatbot/` — Full plan archived
- `ARCHITECTURE.md` — Up to date with all 6 PRs

## What to work on next

Pick based on priorities:

1. **Auth & deployment hardening** — Needed before any public deployment
   - User authentication (JWT or session-based)
   - CORS configuration for production
   - HTTPS enforcement
   - Rate limiting per user (not just per IP)
   - Environment-specific configs (dev/staging/prod)

2. **Testing improvements**
   - E2E tests (frontend → backend → ChromaDB)
   - Load testing (concurrent users, API latency benchmarks)
   - Integration tests for the orchestrator tool-use loop
   - Retrieval quality evaluation (precision/recall against labeled query set)

3. **Retrieval quality tuning** — Now that 4A/4B are deployed
   - Tune `COMPRESSION_THRESHOLD` (currently 0.45) with real queries
   - Tune `QUERY_EXPANSION_COUNT` (currently 3)
   - Evaluate whether expansion actually improves recall for HR synonyms
   - Consider Phase 4A/4B latency impact in production

4. **New features** — Check with user for priorities
   - Document upload (user provides their employment contract for context)
   - Multi-language support (common Singapore languages)
   - Email/export conversation history
   - Notification system for escalations
