# ADR: Testing Improvements (Track 2)

**Status:** Accepted
**Date:** 2026-03-25
**Branch:** `feature/testing-improvements`

---

## ADR-01: httpx AsyncClient Over TestClient for E2E Tests

**Decision:** Use `httpx.AsyncClient` with `ASGITransport(app=app)` for E2E tests instead of FastAPI's synchronous `TestClient`.

**Alternatives considered:**
- `FastAPI.TestClient` (synchronous, wraps httpx internally)
- `pytest-httpx` with separate server process
- Playwright/Selenium for browser-level E2E

**Rationale:** The app uses `async/await` throughout — SSE streaming, aiosqlite, async tool dispatch. `httpx.AsyncClient` runs fully async in-process without spawning a server, making tests fast (~0.5s for 27 tests) and deterministic. `TestClient` works but obscures async behavior. Browser-level tests are out of scope (no JS rendering needed for API tests).

**Consequence:** E2E tests require `pytest-asyncio` with `mode=strict`. All E2E test functions must be `async def` with `pytestmark = pytest.mark.asyncio`.

---

## ADR-02: Mock Only Anthropic API in E2E Tests

**Decision:** E2E tests mock only the Anthropic Claude API. ChromaDB and SQLite use real local instances.

**Alternatives considered:**
- Mock everything (fast but tests prove nothing about integration)
- Mock nothing (requires API key, incurs costs, flaky)
- Record/replay with VCR cassettes

**Rationale:** The goal of E2E tests is to verify the full request/response cycle through real infrastructure. Mocking ChromaDB would hide integration bugs (the exact category of bug E2E tests should catch). Mocking Claude is necessary because: (a) API calls cost money, (b) responses are non-deterministic, (c) rate limits would cause flaky tests.

**Consequence:** E2E tests require ingested ChromaDB data for retrieval tests. The `conftest.py` session-scoped fixture prevents SentenceTransformer downloads.

---

## ADR-03: Mock LLM Mode via Config Flag

**Decision:** Add `MOCK_LLM=true` environment variable that short-circuits the orchestrator with a canned response, bypassing all Claude API calls.

**Alternatives considered:**
- Monkey-patching the Anthropic client at startup
- Separate mock server process
- Locust-side response stubbing

**Rationale:** A config-level flag is the simplest approach — one line in `.env` enables/disables it. The mock lives at the orchestrator level (not the client level) so it still exercises session creation, message persistence, and SSE formatting. This makes load tests realistic for everything except the LLM call itself.

**Consequence:** `mock_llm` field added to `Settings` in `config.py`. Must never be `true` in production — enforced by convention (default is `false`).

---

## ADR-04: Vitest Over Jest for Frontend Tests

**Decision:** Use Vitest with jsdom for frontend component testing.

**Alternatives considered:**
- Jest with Babel transforms
- Cypress Component Testing
- Storybook interaction testing

**Rationale:** Vitest shares the same config as Vite (the project's existing bundler), requires zero additional Babel/webpack configuration, and runs ~10x faster than Jest for small test suites. React Testing Library + jsdom provides sufficient DOM simulation for component smoke tests. Cypress is overkill for component-level tests (better suited for full browser E2E).

**Consequence:** Test config lives in `vite.config.js` under the `test` key. Setup file at `frontend/src/__tests__/setup.js` imports `@testing-library/jest-dom/vitest` for DOM matchers.

---

## ADR-05: Smoke Tests Over Full Coverage for Initial Frontend Setup

**Decision:** Write smoke tests (render + basic interaction) for 3 key components rather than pursuing comprehensive coverage.

**Alternatives considered:**
- Full unit tests for all 10+ components and hooks
- Integration tests with mocked API calls
- Snapshot testing

**Rationale:** The frontend is stable and relatively simple (5 components, 1 page, 2 hooks). Smoke tests establish the testing infrastructure and catch regressions in core user interactions (typing, submitting, feedback, navigation). Full coverage can be added incrementally as the frontend grows. Snapshot tests are brittle and provide low signal for component behavior.

**Consequence:** Coverage is intentionally incomplete. Priority components tested: InputBar (user input), MessageBubble (message display + feedback), AdminDashboard (navigation + admin key).
