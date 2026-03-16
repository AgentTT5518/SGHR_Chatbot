# Plan: Enhancements V2 (Features 3–7)

**Status:** Complete
**Created:** 2026-03-16
**Completed:** 2026-03-16
**Feature Branch:** `feature/enhancementsv2`

---

## Goal / Problem Statement

Add five enhancements to make the SGHR Chatbot production-ready:
1. **User Feedback** — Let users rate answers (thumbs up/down) to track quality
2. **Rate Limiting** — Protect the API from abuse
3. **Admin Dashboard UI** — Give admins a visual panel for ingestion/health/feedback
4. **Retrieval Tuning** — Improve answer relevance with hybrid search
5. **Monitoring/Observability** — Add metrics endpoint and structured event tracking

---

## Feature 3: User Feedback Mechanism

### Approach
- New SQLite table `feedback` (id, session_id, message_index, rating, comment, created_at)
- New endpoint `POST /api/feedback` to record thumbs up/down + optional comment
- New endpoint `GET /admin/feedback` to list feedback (with pagination)
- Frontend: add thumbs up/down buttons on assistant messages in `MessageBubble.jsx`

### Files
| Action | File Path | Description |
|--------|-----------|-------------|
| Modify | `backend/chat/session_manager.py` | Add feedback table + CRUD |
| Create | `backend/api/routes_feedback.py` | POST /api/feedback, GET /admin/feedback |
| Modify | `backend/main.py` | Register feedback router |
| Modify | `frontend/src/components/MessageBubble.jsx` | Add thumbs up/down buttons |
| Modify | `frontend/src/api/chatApi.js` | Add submitFeedback() function |
| Create | `tests/test_feedback.py` | Tests for feedback endpoints |

---

## Feature 4: Rate Limiting

### Approach
- Use `slowapi` (built on `limits` library) — lightweight, FastAPI-native
- Limit `/api/chat` to 20 requests/minute per IP
- Limit `/admin/*` to 10 requests/minute per IP
- Return 429 Too Many Requests with retry-after header
- Add `slowapi` to requirements.txt

### Files
| Action | File Path | Description |
|--------|-----------|-------------|
| Modify | `backend/main.py` | Add slowapi limiter + exception handler |
| Modify | `backend/api/routes_chat.py` | Add rate limit decorator |
| Modify | `backend/api/routes_admin.py` | Add rate limit decorator |
| Modify | `requirements.txt` | Add slowapi |
| Create | `tests/test_rate_limiting.py` | Tests for 429 responses |

---

## Feature 5: Admin Dashboard UI

### Approach
- New React page at `/admin` with simple tab layout (no router needed — toggle state)
- Tabs: **Health** (collection counts + source health), **Ingestion** (trigger + status), **Feedback** (table of user ratings)
- Reuses existing admin API endpoints + new feedback endpoint
- Accessible via a small "Admin" link in the footer

### Files
| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `frontend/src/pages/AdminDashboard.jsx` | Admin page with 3 tabs |
| Create | `frontend/src/api/adminApi.js` | API client for admin endpoints |
| Modify | `frontend/src/App.jsx` | Add admin page toggle/routing |
| Modify | `frontend/src/styles/index.css` | Admin dashboard styles |

---

## Feature 6: Retrieval Tuning

### Approach
- Add keyword-based (BM25-style) scoring alongside semantic search
- Implement TF-IDF scoring using `scikit-learn`'s `TfidfVectorizer` on stored chunks
- Reciprocal Rank Fusion (RRF) to merge semantic + keyword rankings
- Make retrieval mode configurable: "semantic" (current), "hybrid" (new default)
- Add config option `retrieval_mode` to `backend/config.py`

### Files
| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `backend/retrieval/keyword_search.py` | TF-IDF keyword search module |
| Modify | `backend/retrieval/retriever.py` | Add hybrid mode with RRF merging |
| Modify | `backend/config.py` | Add retrieval_mode setting |
| Modify | `requirements.txt` | Add scikit-learn |
| Create | `tests/test_keyword_search.py` | Tests for keyword search |
| Modify | `tests/test_retriever.py` | Tests for hybrid mode |

---

## Feature 7: Monitoring / Observability

### Approach
- New `GET /metrics` endpoint returning JSON metrics (not Prometheus format — keep it simple)
- Track: total requests, avg response time, error count, active sessions, feedback stats
- Use middleware to collect request timing
- In-memory metrics store (resets on restart — sufficient for local/dev)
- Expose on admin dashboard as a "Metrics" tab

### Files
| Action | File Path | Description |
|--------|-----------|-------------|
| Create | `backend/lib/metrics.py` | In-memory metrics collector |
| Modify | `backend/main.py` | Add metrics middleware + /metrics endpoint |
| Modify | `frontend/src/pages/AdminDashboard.jsx` | Add Metrics tab |
| Modify | `frontend/src/api/adminApi.js` | Add fetchMetrics() |
| Create | `tests/test_metrics.py` | Tests for metrics collection |

---

## Implementation Order

1. **Feature 3 (Feedback)** — foundation for admin dashboard and metrics
2. **Feature 4 (Rate Limiting)** — quick win, independent
3. **Feature 6 (Retrieval Tuning)** — backend-only, independent
4. **Feature 7 (Monitoring)** — needs feedback table to exist
5. **Feature 5 (Admin Dashboard)** — depends on all backend endpoints being ready

---

## Cross-Boundary Edits Required

These files are shared across features and need modification:
- `backend/main.py` — router registration, middleware, metrics endpoint
- `backend/config.py` — new settings
- `requirements.txt` — new dependencies
- `frontend/src/App.jsx` — admin page routing

All changes are additive (no breaking changes to existing code).

---

## Open Questions
- [ ] Should rate limits be configurable via .env? (Proposed: yes, with sensible defaults)
- [ ] Should feedback be anonymous or tied to session? (Proposed: tied to session_id)
- [ ] Should admin dashboard require a password? (Proposed: no for v2, flag for later)

## Decisions Made
- Use slowapi for rate limiting (lightweight, FastAPI-native)
- Use TF-IDF for keyword search (no external service needed)
- In-memory metrics (no Prometheus/Grafana dependency)
- Admin dashboard as a page toggle, not a separate app

## Comments / Review Notes
-
