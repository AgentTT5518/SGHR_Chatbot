# Architecture — SGHR Chatbot

> Last updated: 2026-03-16 | Updated by: Claude Code

## System Overview
SGHR Chatbot is a RAG-powered HR assistant that answers questions about the Singapore Employment Act and MOM guidelines. It serves employees and HR managers via a React chat interface, streaming responses from Claude through a FastAPI backend backed by ChromaDB vector search.

## Architecture Diagram
```mermaid
graph TB
    subgraph Client["Client (React + Vite :5173)"]
        UI[Chat UI]
        ADMIN[Admin Dashboard]
    end

    subgraph Server["Backend (FastAPI :8000)"]
        API[API Routes]
        FEEDBACK[Feedback Routes]
        RAG[RAG Chain]
        SM[Session Manager]
        RET[Retriever]
        KS[Keyword Search]
        METRICS[Metrics Middleware]
        LIMITER[Rate Limiter]
    end

    subgraph Storage
        CHROMA[(ChromaDB\nVector Store)]
        SQLITE[(SQLite\nSessions + Feedback)]
    end

    subgraph External
        CLAUDE[Anthropic Claude\nclaude-sonnet-4-6]
        BGE[BGE Embedding\nModel local]
    end

    UI -->|POST /api/chat SSE| API
    UI -->|POST /api/feedback| FEEDBACK
    ADMIN -->|GET /admin/* + /metrics| API
    API --> RAG
    API --> LIMITER
    FEEDBACK --> SM
    RAG --> SM
    RAG --> RET
    RET -->|semantic search| CHROMA
    RET --> KS
    KS -->|TF-IDF over corpus| CHROMA
    BGE -->|embed at ingest| CHROMA
    RAG -->|stream| CLAUDE
    SM --> SQLITE
    METRICS -->|record timing| API
```

## Component Map

| Component | Location | Responsibility | Dependencies |
|-----------|----------|----------------|--------------|
| API Routes - Chat | `backend/api/routes_chat.py` | POST /api/chat (SSE), session history, session delete | rag_chain, session_manager, limiter |
| API Routes - Admin | `backend/api/routes_admin.py` | Admin/ingestion triggers, health checks, collection counts | ingestion pipeline, limiter |
| API Routes - Feedback | `backend/api/routes_feedback.py` | POST /api/feedback, GET /admin/feedback, GET /admin/feedback/stats | session_manager |
| RAG Chain | `backend/chat/rag_chain.py` | Retrieve → prompt → stream Claude response | retriever, session_manager, prompts, Anthropic SDK |
| Session Manager | `backend/chat/session_manager.py` | CRUD for conversation history + feedback, TTL cleanup | aiosqlite, SQLite |
| Prompts | `backend/chat/prompts.py` | System prompt builder, context formatter, source extractor | — |
| Retriever | `backend/retrieval/retriever.py` | Hybrid retrieval (semantic + keyword RRF) + definitions injection | vector_store, keyword_search |
| Keyword Search | `backend/retrieval/keyword_search.py` | TF-IDF over ChromaDB corpus, lazy singleton, RRF input | scikit-learn |
| Vector Store | `backend/retrieval/vector_store.py` | ChromaDB wrapper (collections, readiness check, bulk fetch) | chromadb |
| Ingest Pipeline | `backend/ingestion/ingest_pipeline.py` | Orchestrates scrape → chunk → embed → store | scraper, chunker, embedder |
| Embedder | `backend/ingestion/embedder.py` | BGE model wrapper, lazy singleton | sentence-transformers |
| Chunker | `backend/ingestion/chunker.py` | Text splitting with overlap | — |
| Scrapers | `backend/ingestion/scraper_*.py` | Fetch Employment Act PDF and MOM web pages | playwright, pdfminer, bs4 |
| Config | `backend/config.py` | Pydantic settings, reads `.env` | pydantic-settings |
| Logger | `backend/lib/logger.py` | Structured JSON logger factory | Python logging |
| Limiter | `backend/lib/limiter.py` | Shared slowapi rate-limiter singleton (avoids circular imports) | slowapi |
| Metrics | `backend/lib/metrics.py` | In-memory request counter: totals, errors, avg latency, per-path counts | threading.Lock |
| Frontend App | `frontend/src/` | React chat interface, SSE streaming, feedback buttons, admin dashboard | React 19, Vite |

## Data Model

### Core Entities

| Entity | Storage | Key Fields | Relationships |
|--------|---------|------------|---------------|
| Session | SQLite `sessions` | session_id, created_at, last_active | Has many Messages, Has many Feedback |
| Message | SQLite `messages` | id, session_id, role, content, created_at | Belongs to Session |
| Feedback | SQLite `feedback` | id, session_id, message_index, rating (up/down), comment, created_at | Belongs to Session |
| Document Chunk | ChromaDB | id, text, metadata (source, section, page) | — |

### Schema Notes
- Sessions expire after `SESSION_TTL_HOURS` (default 2h); background cleanup loop runs every 1 hour
- Feedback is tied to `session_id` + `message_index`; cascades on session delete
- ChromaDB uses two collections: `employment_act` (PDF) and `mom_guidelines` (web)
- BGE embeddings are 768-dimensional

## API Endpoints

| Method | Path | Description | Auth | Rate Limit | Status |
|--------|------|-------------|------|------------|--------|
| GET | `/health` | System health (model loaded, chroma ready) | No | — | ✅ |
| GET | `/metrics` | In-memory request metrics + feedback stats | No | — | ✅ |
| POST | `/api/chat` | Stream RAG response (SSE) | No | 20/min per IP | ✅ |
| GET | `/api/sessions/{session_id}/history` | Fetch conversation history | No | — | ✅ |
| DELETE | `/api/sessions/{session_id}` | Delete session | No | — | ✅ |
| POST | `/api/feedback` | Record thumbs-up/down on an assistant message | No | — | ✅ |
| POST | `/admin/ingest` | Trigger ingestion pipeline in background | No | 10/min per IP | ✅ |
| GET | `/admin/health/sources` | Validate MOM seed URLs are reachable | No | 10/min per IP | ✅ |
| GET | `/admin/collections` | Return ChromaDB document counts | No | 10/min per IP | ✅ |
| GET | `/admin/feedback` | Paginated list of feedback records | No | — | ✅ |
| GET | `/admin/feedback/stats` | Aggregate up/down counts | No | — | ✅ |

## External Integrations

| Service | Purpose | Config | Rate Limits | Error Handling |
|---------|---------|--------|-------------|----------------|
| Anthropic Claude | Generate HR answers | `ANTHROPIC_API_KEY` in `.env` | Per plan | Catches `APIError`, streams error token to client |
| ChromaDB | Vector similarity search | Local dir `backend/data/chroma_db/` | Local — no limits | `is_ready()` check at startup |
| BGE Model | Text embeddings | Local cache via sentence-transformers | Local — no limits | Lazy-loaded singleton, warning if missing |

## Error Handling Strategy

### Error Flow
```
Client Error  -> FastAPI validation -> 422 JSON response
Rate Limit    -> slowapi -> 429 JSON with Retry-After header
API Error     -> try/except in rag_chain -> SSE error event to client
Claude Error  -> anthropic.APIError caught -> error SSE token
Service Error -> log.error() -> propagate or fallback message
Zero results  -> FALLBACK_MESSAGE streamed + session still saved
```

### API Error Response Format (non-streaming)
```json
{ "detail": "Human-readable description" }
```
### SSE Error Format (streaming)
```json
{ "error": "Human-readable description", "done": true, "sources": [] }
```

## Security

### Secret Management
- All secrets in `.env` (never committed)
- `.env.example` maintained with placeholders for all required vars
- Secrets loaded only via `backend/config.py` (pydantic-settings)
- Pre-commit scan pattern: `sk-ant-` (CLAUDE.md Rule 1)

### Input Validation
- All API inputs validated via Pydantic models (`ChatRequest`, `FeedbackRequest`)
- `user_role` constrained to `"employee"` | `"hr"` (prompt logic)
- `rating` constrained to `"up"` | `"down"` (DB CHECK constraint + Pydantic validator)
- Session IDs are UUIDs generated client-side

### Rate Limiting
- `/api/chat` limited to 20 requests/minute per IP (configurable via `CHAT_RATE_LIMIT`)
- `/admin/*` limited to 10 requests/minute per IP (configurable via `ADMIN_RATE_LIMIT`)
- Returns 429 with `Retry-After` header on excess

### Deployment Security
- CORS restricted to `http://localhost:5173` in dev
- No auth currently — add before any public deployment
- `.env` in `.gitignore`; only `.env.example` committed

## Feature Log

| Feature | Date | Key Decisions | Files Changed |
|---------|------|---------------|---------------|
| Initial Release | 2026-03-15 | RAG with ChromaDB + BGE; SSE streaming; SQLite sessions; dual-role prompts (employee/hr); Section 2 definitions injection | All initial files |
| Best-Practice Setup | 2026-03-15 | Added CLAUDE.md, ARCHITECTURE.md, settings.json, brand docs, structured logger | `CLAUDE.md`, `ARCHITECTURE.md`, `.claude/settings.json`, `docs/brand/`, `backend/lib/logger.py`, `.env.example` |
| Enhancements V2 (Features 3–7) | 2026-03-16 | User feedback (thumbs up/down → SQLite); slowapi rate limiting (20/min chat, 10/min admin); hybrid retrieval with TF-IDF + RRF; in-memory metrics middleware; admin dashboard UI with 4 tabs | `session_manager.py`, `routes_feedback.py`, `routes_chat.py`, `routes_admin.py`, `main.py`, `config.py`, `keyword_search.py`, `retriever.py`, `vector_store.py`, `lib/limiter.py`, `lib/metrics.py`, `MessageBubble.jsx`, `ChatWindow.jsx`, `App.jsx`, `useChat.js`, `chatApi.js`, `adminApi.js`, `AdminDashboard.jsx`, `index.css`, `requirements.txt` |

> Add a row after completing each feature.

---
_Maintained by Claude Code per CLAUDE.md Rule 4._
