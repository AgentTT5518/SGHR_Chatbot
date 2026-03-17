# Feature Requirements: Enhancements V2 (Features 3–7)

**Status:** Complete
**Completed:** 2026-03-16
**Branch:** `feature/enhancementsv2`

---

## Feature 3: User Feedback Mechanism

### Summary
Allow users to rate assistant answers with thumbs up or thumbs down, with an optional comment. Ratings are stored per session and message index for later analysis.

### Requirements

| # | Requirement | Status |
|---|-------------|--------|
| F3-1 | Users can rate any completed assistant message with 👍 or 👎 | ✅ |
| F3-2 | Rating is stored in SQLite with session_id, message_index, rating, comment, timestamp | ✅ |
| F3-3 | Feedback is tied to session (cascades on session delete) | ✅ |
| F3-4 | Admin can retrieve paginated feedback list via `GET /admin/feedback` | ✅ |
| F3-5 | Admin can retrieve aggregate stats (total/up/down) via `GET /admin/feedback/stats` | ✅ |
| F3-6 | Rating buttons only appear on complete (non-streaming) assistant messages | ✅ |
| F3-7 | UI shows "Thanks for the feedback!" confirmation after rating | ✅ |

### API Contracts

**POST /api/feedback** — 201 Created
```json
Request:  { "session_id": "uuid", "message_index": 2, "rating": "up", "comment": null }
Response: { "success": true, "id": 42 }
```

**GET /admin/feedback?limit=50&offset=0** — 200 OK
```json
{ "limit": 50, "offset": 0, "records": [{ "id", "session_id", "message_index", "rating", "comment", "created_at" }] }
```

**GET /admin/feedback/stats** — 200 OK
```json
{ "total": 10, "up": 7, "down": 3 }
```

---

## Feature 4: Rate Limiting

### Summary
Protect the API from abuse using per-IP rate limits via `slowapi`. Limits are configurable via `.env`.

### Requirements

| # | Requirement | Status |
|---|-------------|--------|
| F4-1 | `POST /api/chat` limited to 20 requests/minute per IP (default) | ✅ |
| F4-2 | All `/admin/*` endpoints limited to 10 requests/minute per IP (default) | ✅ |
| F4-3 | Exceeded limit returns 429 with `Retry-After` header | ✅ |
| F4-4 | Limits are configurable via `CHAT_RATE_LIMIT` and `ADMIN_RATE_LIMIT` env vars | ✅ |
| F4-5 | Limiter is a shared singleton to avoid circular imports | ✅ |

---

## Feature 5: Admin Dashboard UI

### Summary
A React page providing a visual panel for system health, ingestion triggers, feedback review, and live metrics.

### Requirements

| # | Requirement | Status |
|---|-------------|--------|
| F5-1 | Dashboard accessible via "Admin" button in chat header | ✅ |
| F5-2 | **Health tab**: shows system status, model load state, ChromaDB readiness, document counts | ✅ |
| F5-3 | **Ingestion tab**: shows MOM URL health check + triggers ingestion (with force-rescrape option) | ✅ |
| F5-4 | **Feedback tab**: shows aggregate stats and most recent 50 feedback records | ✅ |
| F5-5 | **Metrics tab**: shows total requests, error count, avg latency, per-endpoint counts; refreshable | ✅ |
| F5-6 | Dashboard replaces the chat view (full-page, "Back to Chat" button returns) | ✅ |
| F5-7 | No auth required (v2; flagged for future) | ✅ |

---

## Feature 6: Retrieval Tuning

### Summary
Improve answer relevance by augmenting semantic (cosine) search with TF-IDF keyword search, merged via Reciprocal Rank Fusion. Mode is configurable.

### Requirements

| # | Requirement | Status |
|---|-------------|--------|
| F6-1 | `RETRIEVAL_MODE=hybrid` (default) uses TF-IDF + semantic search merged with RRF | ✅ |
| F6-2 | `RETRIEVAL_MODE=semantic` falls back to original cosine-only retrieval | ✅ |
| F6-3 | TF-IDF vectorizer is lazily fitted over all ChromaDB documents on first query | ✅ |
| F6-4 | Keyword searcher cache is invalidated after re-ingestion | ✅ |
| F6-5 | If corpus is empty or keyword search fails, falls back gracefully to semantic | ✅ |
| F6-6 | Hybrid mode still caps results at 8 chunks (same as semantic) | ✅ |

### RRF formula
```
score(doc) = Σ 1 / (k + rank_in_list + 1)   where k = 60
```
Scores are summed across the semantic rank list and the keyword rank list.

---

## Feature 7: Monitoring / Observability

### Summary
In-memory request metrics collected via middleware, exposed at `GET /metrics`. Integrates feedback stats for a single dashboard view.

### Requirements

| # | Requirement | Status |
|---|-------------|--------|
| F7-1 | Every HTTP request is timed by `MetricsMiddleware` | ✅ |
| F7-2 | Metrics track: total requests, total errors (5xx), avg latency ms, per-path counts | ✅ |
| F7-3 | `GET /metrics` returns current snapshot including feedback aggregate | ✅ |
| F7-4 | Metrics are in-memory (reset on server restart — no external dependency) | ✅ |
| F7-5 | Metrics are thread-safe via `threading.Lock` | ✅ |

---

## Out of Scope (V2)

- Admin authentication / password protection
- Persistent metrics storage (Prometheus/Grafana)
- Feedback comments UI (stored in DB, not surfaced in chat UI)
- Rate limit configuration per-user (session-based), not per-IP
