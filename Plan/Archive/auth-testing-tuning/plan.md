# Plan: Auth Hardening → Testing → Retrieval Tuning

## Context

The HR Chatbot has zero authentication — admin endpoints are public, session IDs are unsigned client-generated UUIDs, and anyone can delete user profiles. CORS is hardcoded to localhost. Before any deployment, we need auth hardening (Priority 1), then proper test coverage for the new auth layer plus integration/load/eval tests (Priority 2), then systematic retrieval quality tuning using the eval framework (Priority 3).

---

## Priority 1: Auth & Deployment Hardening

### Design Decisions
- **Admin auth**: API key in `.env` (`ADMIN_API_KEY`). Always required — `.env.example` ships `ADMIN_API_KEY=dev-only-key` as the dev default. No env-based bypass.
- **Chat users**: Stay anonymous. Server generates session IDs and signs them with HMAC. Client no longer generates UUIDs.
- **Session signing grace period**: Controlled by `SESSION_SIGNING_ENFORCED=false` (default). Set to `true` in prod to reject unsigned IDs. Sunset: flip to `true` by default after one release cycle.
- **CORS**: Env-based `ALLOWED_ORIGINS` comma-separated list
- **Rate limiting**: Per-signed-session key alongside per-IP. Known limitation: without real user auth, determined attackers can create new sessions to bypass per-session limits. This is noted, not solved here.
- **Environments**: `ENVIRONMENT` env var (`dev`/`staging`/`prod`) with sensible defaults

### Phase 1A: Config & Environment Support
Add environment-aware configuration, CORS from env, HTTPS flag.

**Modify:**
- `backend/config.py` — Add `environment`, `allowed_origins`, `admin_api_key` (default `"dev-only-key"`), `session_secret_key`, `enforce_https`, `session_signing_enforced`
- `backend/main.py` — CORS from settings, conditional `HTTPSRedirectMiddleware`
- `.env.example` — New var placeholders with dev defaults documented

### Phase 1B: Session Signing
Server generates and HMAC-signs session IDs. Client stores the signed ID returned by server.

**Session ID flow (new):**
1. Client sends first message with `session_id: null` (or omits it)
2. Server generates UUID + signs it → `uuid.signature`
3. Returns `signed_session_id` in SSE `done` event
4. Client stores and sends `signed_session_id` on all subsequent requests + as `X-Session-Token` header
5. Server verifies signature on every request
6. **Verification logic must distinguish three cases:**
   - `session_id: null` → new session, always allowed (server creates + signs)
   - `session_id` with valid `.signature` → existing session, proceed
   - `session_id` without `.` separator (legacy unsigned) → if `SESSION_SIGNING_ENFORCED=false`, accept and return signed version; if `true`, reject 403
7. Grace period: `SESSION_SIGNING_ENFORCED=false` (default). Sunset: flip to `true` by default after one release cycle.

**Create:**
- `backend/lib/session_signer.py` — `create_signed_session()` (generate UUID + sign), `verify_session_id()` (validate HMAC)

**Modify:**
- `backend/api/routes_chat.py` — Generate signed ID for new sessions, verify on existing. Return in `done` event. Also protect `GET /api/sessions/{session_id}/history` with signature verification.
- `frontend/src/hooks/useChat.js` — Remove client-side UUID generation. Start with `null`, store server-returned signed ID.
- `frontend/src/api/chatApi.js` — Extract `signed_session_id` from `done` event

### Phase 1C: Admin API Key Auth
Protect all `/admin/*` endpoints and `/metrics`.

**Create:**
- `backend/lib/admin_auth.py` — `require_admin` dependency: always checks `X-Admin-Key` header against `settings.admin_api_key`. Returns 401 if missing, 403 if wrong. No environment bypass.

**Modify:**
- `backend/api/routes_admin.py` — Add `dependencies=[Depends(require_admin)]` to router
- `backend/api/routes_feedback.py` — Add `Depends(require_admin)` to `GET /admin/feedback` and `GET /admin/feedback/stats` individually (keep `POST /api/feedback` open)
- `backend/main.py` — Protect `/metrics` endpoint with admin auth
- `frontend/src/pages/AdminDashboard.jsx` — Add API key input field at top, store in `sessionStorage`, send as `X-Admin-Key` header on all admin API calls
- `frontend/src/api/adminApi.js` (or equivalent) — Read key from `sessionStorage`, attach header

**Audit logging:** Add `log.info(f"Admin action: {request.method} {request.url.path}", extra={"admin_ip": request.client.host})` in `require_admin` on success. Simple log trail for who did what.

### Phase 1D: Route Protection
Prevent unauthorized access to profiles, sessions, and feedback submission.

**Modify:**
- `backend/api/routes_profile.py` — GET/DELETE require matching user_id from signed session (via `X-Session-Token` header) or admin key
- `backend/api/routes_chat.py` — `DELETE /api/sessions/{session_id}` requires valid signed session ID. `GET /api/sessions/{session_id}/history` requires valid signed session ID.
- `backend/api/routes_feedback.py` — `POST /api/feedback` requires a valid signed session ID (prevents feedback for non-existent sessions). Validate that the session exists before accepting feedback.

### Phase 1E: Enhanced Rate Limiting
Per-session rate limiting via `X-Session-Token` header + cover unrated endpoints.

**Modify:**
- `backend/lib/limiter.py` — Composite key function: read `X-Session-Token` header (same header used in 1B/1D for route protection) → fallback to IP. Avoids parsing JSON body in key function (which conflicts with FastAPI body consumption). Known limitation documented in code comment: without real user auth, session rotation bypasses per-session limits.
- `backend/api/routes_chat.py` — Use enhanced key function
- `backend/api/routes_feedback.py` — Add rate limit to `POST /api/feedback` (e.g., `5/minute`)
- `backend/api/routes_profile.py` — Add rate limit to GET/DELETE profile (e.g., `10/minute`)

### Phase 1F: ARCHITECTURE.md Update
**Modify:**
- `ARCHITECTURE.md` — Update Component Map (new auth modules), API Endpoints (auth requirements), Feature Log entry for auth hardening

---

## Priority 2: Testing Improvements

### Phase 2A: Auth Tests (after Priority 1)
**Create:**
- `tests/lib/test_session_signer.py` — Sign/verify: valid round-trip, tampered signature, legacy unsigned (grace on/off), empty secret
- `tests/lib/test_admin_auth.py` — Missing key → 401, wrong key → 403, correct key → pass, audit log emitted

**Modify:**
- `tests/api/test_routes_admin.py` — Add `X-Admin-Key: dev-only-key` to all existing tests + new tests for 401/403
- `tests/api/test_routes_chat.py` — Signed session flow: null → server-assigned, tampered → 403, history endpoint protected
- `tests/api/test_routes_profile.py` — Ownership verification, admin override for DELETE
- `tests/api/test_routes_feedback.py` (if exists, or add to test_feedback.py) — Feedback with invalid session → rejected

### Phase 2B: Orchestrator Integration Tests (independent)
**Create:**
- `tests/chat/test_orchestrator_integration.py` — Mock Anthropic client with pre-canned tool_use responses, real tool dispatch through registry. Tests: single tool → text, multi-tool iteration, max iterations fallback, tool error handling, cache hit skip, profile injection into system prompt.

**Modify:**
- `tests/conftest.py` — Shared mock Anthropic streaming client fixture

### Phase 2C: Load Testing Setup (independent)

**BOUNDARY ALERT:** Load testing deps go in `tests/requirements-load.txt` (new file), NOT `requirements.txt`, to avoid polluting production deps.

**Create:**
- `tests/requirements-load.txt` — `locust>=2.20.0`
- `tests/load/locustfile.py` — Chat SSE flow (with stream consumption), admin read storm (with API key), feedback burst. Mock Anthropic client to test infra only.
- `tests/load/README.md` — Install instructions (`pip install -r tests/requirements-load.txt`), run commands, baseline numbers

### Phase 2D: Retrieval Eval Framework (independent, feeds Priority 3)
**Create:**
- `tests/eval/dataset.json` — 50+ labeled HR queries across categories: annual leave, notice period, salary definitions, Part IV eligibility, maternity leave, sick leave, retrenchment, overtime, public holidays, probation. Include 5-10 adversarial/out-of-scope queries (e.g., "What's the weather?", "US tax filing") to verify retrieval returns low-confidence results for off-topic questions. Per query: `{"query": "...", "category": "...", "expected_chunk_ids": [...], "expected_keywords": [...]}`
- `tests/eval/eval_retrieval.py` — Precision@k, recall@k, MRR. Flags: `--expansion on/off`, `--compression on/off`, `--threshold X`. Per-category breakdown in output.
- `tests/eval/README.md` — Usage, metric definitions, how to add labeled queries

### Phase 2E: ARCHITECTURE.md Update
**Modify:**
- `ARCHITECTURE.md` — Feature Log entry for testing improvements, document eval framework location

---

## Priority 3: Retrieval Quality Tuning

### Phase 3A: Make Constants Configurable
**Modify:**
- `backend/config.py` — Add `threshold_floor: float = 0.25`, `threshold_multiplier: float = 1.5`, `rrf_k: int = 60`, `max_retrieval_results: int = 8`
- `backend/retrieval/retriever.py` — Replace hardcoded `THRESHOLD_FLOOR`, `THRESHOLD_MULTIPLIER`, `_RRF_K`, `_MAX_RESULTS` with `settings.*` reads
- `.env.example` — Document new vars with current defaults

### Phase 3B: Baseline Measurement (operational)
Run eval framework with 4 configs: all on, expansion off, compression off, both off. Record precision@8, recall@8, MRR, avg latency per query. Save to `tests/eval/results/baseline.json`.

### Phase 3C: Parameter Sweep
**Create:**
- `tests/eval/sweep.py` — Two-stage sweep to manage cost (full sweep = 135 configs x 50+ queries):
  1. **Stage 1 (fast, no API calls):** Sweep with expansion OFF: `COMPRESSION_THRESHOLD` [0.35, 0.40, 0.45, 0.50, 0.55], `THRESHOLD_FLOOR` [0.20, 0.25, 0.30], `RRF_K` [40, 60, 80] = 45 configs. Pure retrieval, no Haiku calls.
  2. **Stage 2 (top N only):** Take top 5 configs from Stage 1, test each with expansion ON at `QUERY_EXPANSION_COUNT` [2, 3, 4] = 15 configs. Measures Haiku latency/cost impact.
  - Record quality + latency per config. Output ranked table.

### Phase 3D: Apply & Document
**Modify:**
- `backend/config.py` — Update defaults to sweep winners
- `.env.example` — Update documented defaults
- `ARCHITECTURE.md` — Document tuning results: baseline vs. tuned metrics, parameter choices and rationale

---

## Execution Order

```
1A → 1B + 1C + 1E (parallel) → 1D → 1F → PR
2B + 2C + 2D (parallel, start during P1) → 2A (after P1 merges) → 2E → PR
3A (can start during P2) → 3B (after 2D) → 3C → 3D → PR
```

## Verification
- **Priority 1**: `pytest tests/ -v` all green, manual test: admin 401/403, signed session round-trip in browser, `/metrics` requires key, feedback rejects invalid session
- **Priority 2**: New tests pass, load test runs clean, eval framework produces per-category metrics for 50+ queries
- **Priority 3**: Eval metrics improve over baseline, `pytest` passes, no retrieval regressions

## Totals
| Priority | New Files | Modified Files |
|----------|:---------:|:--------------:|
| 1: Auth | 2 | ~12 |
| 2: Testing | 8 | 6 |
| 3: Retrieval | 1 | 6 |
