# Requirements — Auth Hardening, Testing Improvements, Retrieval Tuning

## Priority 1: Auth & Deployment Hardening

### Session Signing
- Server generates session IDs (UUIDs) and signs with HMAC-SHA256
- Clients store signed token (`uuid.signature`) and send via `X-Session-Token` header
- Three verification cases: null (new session), signed (valid), unsigned legacy (grace period)
- `SESSION_SIGNING_ENFORCED` toggle — `false` accepts unsigned IDs, `true` rejects them
- `SESSION_SECRET_KEY` required in prod for persistence across restarts

### Admin API Key Auth
- All `/admin/*` and `/metrics` endpoints require `X-Admin-Key` header
- `ADMIN_API_KEY` env var, defaults to `dev-only-key` for development
- No environment-based bypass — key always checked
- Audit logging on successful admin access (method, path, IP)

### Route Protection
- `GET /api/profile/{user_id}` — requires valid session token or admin key
- `DELETE /api/profile/{user_id}` — requires admin key only
- `GET/DELETE /api/sessions/{session_id}` — requires valid signed session
- `POST /api/feedback` — validates session exists in database

### Rate Limiting
- Composite key: `X-Session-Token` header → client IP fallback
- `/api/chat`: 20/min, `/admin/*`: 10/min, `/api/feedback`: 5/min, `/api/profile/*`: 10/min
- Known limitation: without real user auth, session rotation bypasses per-session limits

### Deployment Config
- `ENVIRONMENT` env var (`dev`/`staging`/`prod`)
- `ALLOWED_ORIGINS` — comma-separated CORS origins
- `ENFORCE_HTTPS` — enables HTTPSRedirectMiddleware

## Priority 2: Testing Improvements

### Auth Tests (Phase 2A)
- 11 session signer unit tests (sign, verify, tamper, legacy grace/enforced)
- 6 admin auth unit tests (missing/wrong/correct key, audit log)
- Updated all existing route tests with auth headers

### Orchestrator Integration Tests (Phase 2B)
- 14 tests covering: single tool dispatch, multi-tool iteration, max iterations fallback, tool error recovery, semantic cache hit/miss
- Mock Anthropic client with pre-canned tool_use responses, real tool dispatch

### Load Testing (Phase 2C)
- Locust setup with 3 user classes: ChatUser (SSE), AdminUser (read storm), FeedbackUser
- Separate `tests/requirements-load.txt` (not in production deps)
- Anthropic client should be mocked server-side for load tests

### Retrieval Eval Framework (Phase 2D)
- 55 labelled queries (50 HR across 20 categories + 5 adversarial)
- Metrics: keyword recall, adversarial pass rate, per-category breakdown, latency
- Configurable flags: `--expansion on/off`, `--compression on/off`, `--threshold X`

## Priority 3: Retrieval Quality Tuning

### Configurable Constants (Phase 3A)
- `THRESHOLD_FLOOR` (default 0.25), `THRESHOLD_MULTIPLIER` (1.5), `RRF_K` (60), `MAX_RETRIEVAL_RESULTS` (8)
- All in `backend/config.py`, overridable via `.env`

### Parameter Sweep (Phase 3C)
- Two-stage: Stage 1 sweeps 45 configs (expansion OFF), Stage 2 tests top-5 with expansion ON at 3 counts
- Ranks by keyword recall then latency
