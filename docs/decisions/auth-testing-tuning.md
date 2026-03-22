# Architecture Decision Records — Auth, Testing, Tuning

## ADR-1: HMAC Session Signing over JWT

**Decision**: Use HMAC-SHA256 signed session IDs instead of JWT tokens.

**Why**: The app uses anonymous sessions with no user claims to encode. JWT adds unnecessary complexity (token expiry, refresh flow, library deps). HMAC signing achieves the goal (tamper prevention) with zero new dependencies and ~20 lines of code.

**Trade-off**: No embedded claims — session data must always be looked up from SQLite. Acceptable since we already do this.

## ADR-2: Admin API Key over User Management System

**Decision**: Simple API key in `.env` rather than a full admin user/role system.

**Why**: The admin dashboard is used by a small team. A full user management system (registration, password hashing, role tables) is over-engineered for the current stage. API key is one env var, one header check.

**Trade-off**: Single shared key, no per-admin audit trail. Mitigated by audit logging the IP. Can upgrade to per-user auth later.

## ADR-3: No Dev-Mode Auth Bypass

**Decision**: Admin key is always required, even in development. `.env.example` ships `ADMIN_API_KEY=dev-only-key`.

**Why**: Environment-based bypass risks misconfigured production deploys being wide open. A known default key for dev is equally convenient but fails safe — a missing key in prod returns 401 rather than silently allowing access.

## ADR-4: Composite Rate Limiting (Session → IP)

**Decision**: Rate limit by `X-Session-Token` header, falling back to client IP.

**Why**: Per-IP limiting is too coarse (shared office IPs) and too loose (VPN rotation). Per-session is better granularity. Reading from a header avoids parsing the JSON body in slowapi's key function (which conflicts with FastAPI body consumption).

**Known limitation**: Without real user auth, attackers can create new sessions to bypass per-session limits. Documented, not solved — requires proper user auth.

## ADR-5: Profile DELETE Requires Admin Key

**Decision**: Profile deletion is admin-only, not self-service.

**Why**: Profile deletion is a destructive, irreversible action. Without real user auth, there's no way to verify "this person owns this profile." Admin key provides a trust boundary. GET is less sensitive — any valid session can read (the user_id is self-identified anyway).

## ADR-6: Separate Load Test Dependencies

**Decision**: `tests/requirements-load.txt` instead of adding locust to `requirements.txt`.

**Why**: Locust is a heavy dependency (gevent, Flask) not needed in production or CI. Separate file avoids polluting production deps and respects the CLAUDE.md Rule 5 boundary on `requirements.txt`.

## ADR-7: Keyword Recall over Chunk ID Matching for Eval

**Decision**: Eval framework measures keyword presence in retrieved text rather than exact chunk ID matching.

**Why**: Chunk IDs are unstable across re-ingestion (ChromaDB assigns UUIDs). Keywords are content-stable — "annual leave" will always appear in relevant chunks regardless of ID. Per-category breakdown still identifies weak areas.

**Trade-off**: Less precise than exact match. Mitigated by using multiple expected keywords per query.

## ADR-8: Two-Stage Parameter Sweep

**Decision**: Sweep in two stages — fast expansion-OFF sweep first, then expansion-ON only on top configs.

**Why**: Full grid (135 configs x 55 queries) with expansion ON means 135 x 55 = 7,425 Haiku API calls just for expansion. Stage 1 (45 configs, no API calls) identifies the best retrieval params. Stage 2 (15 configs) tests expansion variants cheaply on only the winners.

## ADR-9: Grace Period for Session Signing Migration

**Decision**: `SESSION_SIGNING_ENFORCED=false` by default, accepting unsigned legacy IDs.

**Why**: Existing clients have unsigned session IDs in sessionStorage. A hard cutover would break all active sessions. Grace period lets clients naturally migrate (server returns signed token, client stores it). Enforcement enabled in prod after one release cycle.
