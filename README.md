# SGHR Chatbot

An AI-powered HR assistant for Singapore employment law. Combines **RAG (Retrieval-Augmented Generation)** with Claude AI to answer employee and HR questions grounded in the **Singapore Employment Act** and **Ministry of Manpower (MOM) guidelines** — with source citations.

---

## Features

- **Role-based answers** — toggle between Employee and HR Professional mode for tailored responses
- **Source citations** — every answer cites the specific Employment Act section or MOM URL
- **Streaming responses** — real-time token streaming via Server-Sent Events
- **Conversation history** — multi-turn sessions persisted in SQLite
- **Fallback guidance** — directs users to MOM when no relevant documents are found

---

## Architecture

```
Frontend (React + Vite)       Backend (FastAPI)          Data Layer
─────────────────────         ─────────────────          ──────────
ChatWindow                    POST /api/chat       ──>   ChromaDB
MessageBubble                 GET  /api/sessions          ├── employment_act
InputBar          ──SSE──>    DELETE /api/sessions        └── mom_guidelines
RoleToggle                    POST /admin/ingest    ──>   SQLite (sessions)
StatusBanner                  GET  /health
```

**Stack:**
- **Backend:** Python, FastAPI, Anthropic SDK, ChromaDB, SQLite, sentence-transformers (BGE)
- **Frontend:** React 19, Vite, react-markdown
- **AI Model:** `claude-sonnet-4-6`
- **Embeddings:** `BAAI/bge-base-en-v1.5`

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- An [Anthropic API key](https://console.anthropic.com/)
- Singapore Employment Act PDF (available from [AGC Singapore](https://sso.agc.gov.sg/Act/EmA1968))

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/AgentTT5518/SGHR_Chatbot.git
cd SGHR_Chatbot
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set your Anthropic API key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

### 4. Run one-time setup

Downloads the BGE embedding model (~440 MB), installs Playwright Chromium, and initialises the SQLite schema.

```bash
python setup.py
```

### 5. Ingest documents

```bash
# With the Employment Act PDF (recommended)
python -m backend.ingestion.ingest_pipeline --pdf path/to/employment_act.pdf

# Without PDF (web scraper fallback — slower, may hit bot protection)
python -m backend.ingestion.ingest_pipeline
```

This scrapes MOM guidelines and indexes everything into ChromaDB. Takes 5–15 minutes on first run; subsequent runs use cached JSON files.

### 6. Install frontend dependencies

```bash
cd frontend
npm install
```

---

## Running the App

Start the backend and frontend in separate terminals:

```bash
# Terminal 1 — Backend (port 8000)
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — Frontend (port 5173)
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

---

## Project Structure

```
SGHR_Chatbot/
├── backend/
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # Settings & paths
│   ├── api/
│   │   ├── routes_chat.py         # Chat & session endpoints
│   │   └── routes_admin.py        # Ingestion & health endpoints
│   ├── chat/
│   │   ├── rag_chain.py           # RAG pipeline + Claude streaming
│   │   ├── prompts.py             # Role-based system prompts
│   │   └── session_manager.py     # SQLite conversation storage
│   ├── retrieval/
│   │   ├── retriever.py           # Query logic + threshold filtering
│   │   └── vector_store.py        # ChromaDB wrapper
│   └── ingestion/
│       ├── ingest_pipeline.py     # Orchestrator
│       ├── ingest_employment_act_pdf.py  # PDF parser
│       ├── scraper_employment_act.py     # Web scraper fallback
│       ├── scraper_mom.py         # MOM website crawler
│       ├── chunker.py             # Token-aware text chunking
│       └── embedder.py            # BGE embedding wrapper
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── api/chatApi.js         # Fetch + SSE stream client
│       ├── hooks/useChat.js       # Chat state (useReducer)
│       └── components/            # ChatWindow, MessageBubble, InputBar, ...
├── setup.py                       # One-time initialisation
├── requirements.txt
└── .env.example
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat` | Stream a RAG response (SSE) |
| `GET` | `/api/sessions/{id}/history` | Fetch conversation history |
| `DELETE` | `/api/sessions/{id}` | Delete a session |
| `POST` | `/admin/ingest` | Trigger ingestion pipeline |
| `GET` | `/admin/collections` | ChromaDB document counts |
| `GET` | `/admin/health/sources` | Validate MOM seed URLs |
| `GET` | `/health` | Backend health check |

### Chat request

```json
POST /api/chat
{
  "session_id": "abc-123",
  "message": "How many days of annual leave am I entitled to?",
  "user_role": "employee"
}
```

Response is a stream of `text/event-stream` events:

```
data: {"token": "Under", "done": false}
data: {"token": " the", "done": false}
...
data: {"token": "", "done": true, "sources": [{"label": "Employment Act, Part IV, s 88A", "url": "..."}]}
```

---

## Configuration

All settings are in `backend/config.py` and can be overridden via `.env`:

| Setting | Default | Description |
|---------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required |
| `claude_model` | `claude-sonnet-4-6` | Claude model ID |
| `embedding_model` | `BAAI/bge-base-en-v1.5` | BGE embedding model |
| `max_tokens` | `2048` | Max response tokens |
| `session_ttl_hours` | `2` | Inactivity timeout |
| `session_history_pairs` | `10` | Conversation turns kept in context |

---

## Data Sources

- **Singapore Employment Act** — parsed from official PDF or scraped from [SSO AGC](https://sso.agc.gov.sg/Act/EmA1968)
- **MOM Guidelines** — scraped from [mom.gov.sg](https://www.mom.gov.sg) (14 seed URLs covering leave, salary, termination, workplace fairness)

All data is indexed locally in ChromaDB. No external API calls are made at query time beyond the Anthropic API.

---

## Disclaimer

This chatbot is for **informational purposes only** and does not constitute legal advice. Employment law is complex and fact-specific. Always verify with [MOM](https://www.mom.gov.sg) or consult a qualified Singapore employment lawyer for your specific situation.
