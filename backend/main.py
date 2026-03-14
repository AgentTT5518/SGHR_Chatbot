"""
FastAPI application entry point.
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.chat import session_manager
from backend.retrieval import vector_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("[startup] Initialising SQLite schema...")
    await session_manager.init_db()

    print("[startup] Pre-loading embedding model...")
    from backend.ingestion.embedder import get_model
    get_model()

    print("[startup] Checking ChromaDB collections...")
    if not vector_store.is_ready():
        print(
            "[startup] WARNING: ChromaDB collections are empty or missing. "
            "Run: python -m backend.ingestion.ingest_pipeline"
        )

    # Start background session cleanup task
    cleanup_task = asyncio.create_task(session_manager.cleanup_loop())
    print("[startup] Ready.")

    yield

    # Shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="HR Chatbot API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.api.routes_chat import router as chat_router
from backend.api.routes_admin import router as admin_router

app.include_router(chat_router)
app.include_router(admin_router)


@app.get("/health")
async def health():
    model_loaded = True
    try:
        from backend.ingestion.embedder import _model
        model_loaded = _model is not None
    except Exception:
        model_loaded = False

    chroma_ready = vector_store.is_ready()

    return {
        "status": "ok" if (model_loaded and chroma_ready) else "degraded",
        "model": "loaded" if model_loaded else "loading",
        "chroma": "ready" if chroma_ready else "not_ready",
    }
