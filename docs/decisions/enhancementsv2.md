# ADR: Enhancements V2 (Features 3–7)

**Status:** Accepted
**Date:** 2026-03-16
**Branch:** `feature/enhancementsv2`

---

## ADR-01: Rate Limiting Library — slowapi

**Decision:** Use `slowapi` (built on `limits`) for rate limiting.

**Alternatives considered:**
- `fastapi-limiter` (requires Redis)
- Custom middleware with an in-memory dict

**Rationale:** `slowapi` is the de-facto FastAPI rate-limiting library, mirrors Flask-Limiter's API, requires no external service, and supports per-route decorators cleanly. The `limits` library provides storage backends upgradeable to Redis later.

**Consequence:** The shared `Limiter` singleton lives in `backend/lib/limiter.py` (not `main.py`) to avoid circular imports when routes import it.

---

## ADR-02: Limiter as a Shared Module (not imported from main.py)

**Decision:** Create `backend/lib/limiter.py` to hold the `Limiter` singleton.

**Problem:** If routes import `limiter` from `backend.main`, and `main.py` imports routes, a circular import occurs.

**Solution:** Extract `limiter` into its own module; both `main.py` and route files import from `backend.lib.limiter`.

---

## ADR-03: Keyword Search — TF-IDF (not BM25)

**Decision:** Use `sklearn.feature_extraction.text.TfidfVectorizer` for keyword search.

**Alternatives considered:**
- `rank_bm25` — BM25 implementation, no external service
- Elasticsearch / OpenSearch — full-featured, but external service dependency

**Rationale:** `scikit-learn` is already a common dependency and `TfidfVectorizer` with `sublinear_tf=True` approximates BM25 behaviour well for this corpus size. No additional service or process is needed.

**Consequence:** The TF-IDF matrix is re-fitted lazily on first query after startup. After re-ingestion, `reset_searcher()` is called in `_run_ingest()` to invalidate the cache. Fitting takes ~1–3s on first use.

---

## ADR-04: Retrieval Merge — Reciprocal Rank Fusion (RRF)

**Decision:** Use RRF (k=60) to merge semantic and keyword ranked lists.

**Alternatives considered:**
- Linear score interpolation (`α * semantic_score + (1-α) * keyword_score`) — requires tuning α and normalising heterogeneous score scales
- Re-ranking with a cross-encoder — requires a second model, adds latency

**Rationale:** RRF is parameter-free (k=60 is the conventional default), score-scale agnostic, and consistently outperforms linear interpolation in information retrieval benchmarks. It is the industry standard for hybrid search.

---

## ADR-05: Feedback Stored Per Message Index (not message ID)

**Decision:** `feedback.message_index` stores the 0-based array index of the message in the frontend conversation list.

**Alternatives considered:**
- Foreign key to `messages.id` — would require the frontend to know DB row IDs, coupling backend storage to frontend state

**Rationale:** The frontend has no knowledge of DB message IDs (they are not returned by any API). Using array index is simpler, and is sufficient for analysis since the full conversation can always be retrieved alongside feedback records.

---

## ADR-06: In-Memory Metrics (not Prometheus)

**Decision:** Track request metrics in a Python dict protected by `threading.Lock`. Expose via `GET /metrics` as plain JSON.

**Alternatives considered:**
- `prometheus_fastapi_instrumentator` — adds Prometheus exposition format, requires scraper
- OpenTelemetry — full observability stack, significant setup overhead

**Rationale:** The goal is lightweight local/dev observability with zero infrastructure dependencies. In-memory metrics are sufficient. If production monitoring is needed later, the `record_request()` call site can be replaced with an OpenTelemetry counter without changing the route layer.

**Consequence:** Metrics reset on server restart. This is documented and accepted for v2.

---

## ADR-07: Admin Dashboard as Full-Page Toggle (not a Route)

**Decision:** `AdminDashboard` is rendered by toggling `showAdmin` state in `App.jsx`. No client-side router is introduced.

**Alternatives considered:**
- `react-router-dom` with `/admin` route
- Separate HTML page / app

**Rationale:** The project deliberately has no client-side router (keeping deps minimal). A full-page state toggle achieves the same UX with zero additional dependencies. A router can be added later if more pages are needed.

---

## ADR-08: Admin Dashboard — No Authentication (V2)

**Decision:** The admin dashboard requires no password in V2.

**Rationale:** The app is local/dev-only. Adding auth (even HTTP Basic) adds complexity that is not justified at this stage. The decision is explicitly flagged for future resolution before any public deployment.
