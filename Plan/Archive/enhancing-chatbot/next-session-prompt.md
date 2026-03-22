# Next Session Prompt — Enhancing Chatbot Feature Complete

Copy everything below the line into a new Claude Code session.

---

The "Enhancing Chatbot" feature plan is **fully delivered**. All 5 PRs have been merged:

| PR | Phase | Status |
|----|-------|--------|
| PR 1 | Phase 1: Token budget + SummaryBuffer + persistent user ID | Merged |
| PR 2 | Phase 2A-2D + 4C: Tool registry + all tools + metadata filtering | Merged |
| PR 3 | Phase 2E: Orchestrator + frontend thinking UX | Merged |
| PR 4 | Phase 3A-3B: Profile memory + verified Q&A cache | Merged |
| PR 5 | Phase 3C: FAQ pattern detection | Merged |

## What's deferred

- **Phase 4A (Query Expansion)** — deferred until retrieval quality metrics justify it
- **Phase 4B (Contextual Compression)** — deferred until retrieval quality metrics justify it
- Both are documented in `Plan/Planning/enhancing-chatbot/plan.md` (lines ~894–895)

## Cleanup tasks for this session

1. Read `Plan/Planning/enhancing-chatbot/plan.md` to confirm all acceptance criteria are met
2. Finalize feature documentation:
   - Create `docs/requirements/enhancing-chatbot.md` from the plan (Feature Workflow step 8)
   - Create `docs/decisions/enhancing-chatbot.md` with key Architecture Decision Records
3. Move `Plan/Planning/enhancing-chatbot/` to `Plan/Archive/enhancing-chatbot/`
4. Review `ARCHITECTURE.md` for completeness — all 5 PRs should be reflected
5. Consider what to work on next:
   - Phase 4A/4B (retrieval improvements) — only if usage data shows retrieval gaps
   - Auth/deployment hardening — needed before any public deployment
   - Testing improvements — E2E tests, load testing
   - New feature planning — check with user for priorities
