"""
FastAPI application entry point.
"""
import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from backend.api.routes_chat import router as chat_router
from backend.api.routes_admin import router as admin_router
from backend.api.routes_feedback import router as feedback_router
from backend.api.routes_profile import router as profile_router
from backend.chat import session_manager
from backend.config import settings as _settings
from backend.memory import profile_store
from backend.lib.admin_auth import require_admin
from backend.lib.limiter import limiter
from backend.lib.logger import get_logger
from backend.retrieval import vector_store

log = get_logger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        is_error = False
        try:
            response = await call_next(request)
            is_error = response.status_code >= 500
            return response
        except Exception:
            is_error = True
            raise
        finally:
            latency_ms = (time.monotonic() - start) * 1000
            from backend.lib.metrics import record_request
            record_request(request.url.path, latency_ms, is_error=is_error)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    log.info("Initialising SQLite schema...")
    await session_manager.init_db()
    await profile_store.init_profile_db()

    log.info("Pre-loading embedding model...")
    from backend.ingestion.embedder import get_model
    get_model()

    log.info("Checking ChromaDB collections...")
    if not vector_store.is_ready():
        log.warning(
            "ChromaDB collections are empty or missing. "
            "Run: python -m backend.ingestion.ingest_pipeline"
        )

    # Start background session cleanup task
    cleanup_task = asyncio.create_task(session_manager.cleanup_loop())
    # Run profile stale cleanup once at startup
    try:
        deleted = await profile_store.cleanup_stale_profiles()
        if deleted:
            log.info("Cleaned stale profiles at startup", extra={"deleted": deleted})
    except Exception:
        log.error("Profile cleanup at startup failed", exc_info=True)
    log.info("Ready.")

    yield

    # Shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="HR Chatbot API", version="1.0.0", lifespan=lifespan)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(MetricsMiddleware)

# CORS — origins from env (ALLOWED_ORIGINS), defaults to localhost:5173
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HTTPS redirect in production
if _settings.enforce_https:
    from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware  # noqa: E402
    app.add_middleware(HTTPSRedirectMiddleware)

app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(feedback_router)
app.include_router(profile_router)


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


@app.get("/metrics", dependencies=[Depends(require_admin)])
async def metrics(request: Request):
    """Return in-memory request metrics (resets on server restart)."""
    from backend.lib.metrics import get_snapshot
    from backend.chat.session_manager import get_feedback_stats
    snapshot = get_snapshot()
    try:
        snapshot["feedback"] = await get_feedback_stats()
    except Exception:
        snapshot["feedback"] = {}
    return snapshot
