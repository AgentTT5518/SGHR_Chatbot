"""
Admin routes for triggering re-ingestion and health checks.
POST /admin/ingest — run the ingestion pipeline
GET  /admin/health/sources — check MOM URL health
GET  /admin/collections — document counts from ChromaDB
GET  /admin/verified-answers — list verified answers cache
POST /admin/verified-answers — add verified answer to cache
DELETE /admin/verified-answers/{id} — remove verified answer
GET  /admin/feedback/candidates — thumbs-up answers not yet cached
GET  /admin/faq-patterns — FAQ query clusters and knowledge gaps
"""
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.config import RAW_SCRAPED_DIR, settings
from backend.ingestion.scraper_mom import SEED_URLS, HEADERS
from backend.lib.admin_auth import require_admin
from backend.lib.limiter import limiter
from backend.lib.logger import get_logger

log = get_logger("api.routes_admin")

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


class IngestRequest(BaseModel):
    force_rescrape: bool = False


def _run_ingest(force_rescrape: bool):
    if force_rescrape:
        # Remove cached files to force re-scrape
        for fname in ["employment_act.json", "mom_pages.json"]:
            path = RAW_SCRAPED_DIR / fname
            if path.exists():
                path.unlink()
        # Invalidate keyword search cache after re-ingestion
        try:
            from backend.retrieval.keyword_search import reset_searcher
            reset_searcher()
        except Exception:
            pass

    from backend.ingestion.ingest_pipeline import run
    run()


@router.post("/ingest")
@limiter.limit(settings.admin_rate_limit)
async def trigger_ingest(request: Request, req: IngestRequest, background_tasks: BackgroundTasks):
    """
    Trigger the ingestion pipeline in the background.
    Check /admin/health/sources first to validate MOM URLs.
    """
    background_tasks.add_task(_run_ingest, req.force_rescrape)
    return {
        "status": "started",
        "message": "Ingestion pipeline started in background. Check server logs for progress.",
        "force_rescrape": req.force_rescrape,
    }


@router.get("/health/sources")
@limiter.limit(settings.admin_rate_limit)
async def check_source_health(request: Request):
    """Validate all MOM seed URLs are reachable before ingestion."""
    results = []
    async with httpx.AsyncClient(headers=HEADERS) as client:
        for url in SEED_URLS:
            try:
                r = await client.head(url, timeout=10, follow_redirects=True)
                results.append({"url": url, "status": r.status_code, "ok": r.status_code == 200})
            except Exception as e:
                results.append({"url": url, "status": None, "ok": False, "error": str(e)})

    ok_count = sum(1 for r in results if r["ok"])
    return {
        "total": len(results),
        "ok": ok_count,
        "failed": len(results) - ok_count,
        "results": results,
    }


@router.get("/collections")
@limiter.limit(settings.admin_rate_limit)
async def collection_counts(request: Request):
    """Return current document counts in ChromaDB collections."""
    from backend.retrieval.vector_store import get_collection
    try:
        ea = get_collection("employment_act").count()
        mom = get_collection("mom_guidelines").count()
        return {"employment_act": ea, "mom_guidelines": mom}
    except Exception as e:
        return {"error": str(e)}


@router.get("/escalations")
@limiter.limit(settings.admin_rate_limit)
async def list_escalations(
    request: Request,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List escalation records, optionally filtered by status."""
    from backend.chat.session_manager import get_escalations
    return await get_escalations(status=status, limit=limit, offset=offset)


# ── Verified Answers Cache ──────────────────────────────────────────────────


class VerifiedAnswerRequest(BaseModel):
    question: str
    answer: str
    sources: list[dict] = []


@router.get("/verified-answers")
@limiter.limit(settings.admin_rate_limit)
async def list_verified_answers(request: Request):
    """List all cached verified answers."""
    from backend.memory.semantic_cache import list_verified_answers as _list
    try:
        return {"answers": _list()}
    except Exception as exc:
        log.error("Failed to list verified answers", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list verified answers") from exc


@router.post("/verified-answers", status_code=201)
@limiter.limit(settings.admin_rate_limit)
async def create_verified_answer(request: Request, req: VerifiedAnswerRequest):
    """Admin approves an answer into the semantic cache."""
    from backend.memory.semantic_cache import add_verified_answer
    try:
        doc_id = add_verified_answer(
            question=req.question,
            answer=req.answer,
            sources=req.sources,
        )
        return {"success": True, "id": doc_id}
    except Exception as exc:
        log.error("Failed to add verified answer", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add verified answer") from exc


@router.delete("/verified-answers/{answer_id}")
@limiter.limit(settings.admin_rate_limit)
async def delete_verified_answer(request: Request, answer_id: str):
    """Remove a verified answer from the cache."""
    from backend.memory.semantic_cache import remove_verified_answer
    try:
        remove_verified_answer(answer_id)
        return {"success": True, "message": "Verified answer removed"}
    except Exception as exc:
        log.error("Failed to remove verified answer", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to remove verified answer") from exc


# ── FAQ Patterns ───────────────────────────────────────────────────────────


@router.get("/faq-patterns")
@limiter.limit(settings.admin_rate_limit)
async def get_faq_patterns(request: Request, days: int = 30):
    """Return top query clusters and knowledge gaps for admin review."""
    from backend.memory.faq_analyzer import analyze_query_patterns, identify_gaps
    try:
        top_patterns = await analyze_query_patterns(days=days)
        knowledge_gaps = await identify_gaps(days=days)
        return {"top_patterns": top_patterns, "knowledge_gaps": knowledge_gaps}
    except Exception as exc:
        log.error("FAQ pattern analysis failed", exc_info=True)
        raise HTTPException(status_code=500, detail="FAQ pattern analysis failed") from exc


@router.get("/feedback/candidates")
@limiter.limit(settings.admin_rate_limit)
async def feedback_candidates(request: Request):
    """Return thumbs-up feedback entries with their messages for cache review.

    Joins feedback (rating='up') with the corresponding assistant message
    so admins can approve answers into the verified cache.
    """
    from backend.chat.session_manager import get_feedback, get_full_history
    try:
        feedback_records = await get_feedback(limit=100, offset=0)
        candidates = []
        for rec in feedback_records:
            if rec["rating"] != "up":
                continue
            # Fetch the session history to get the actual Q&A
            history = await get_full_history(rec["session_id"])
            msg_idx = rec["message_index"]
            # message_index is 0-based index in the conversation
            # Find assistant message at that index and the preceding user message
            if msg_idx < 0 or msg_idx >= len(history):
                continue
            assistant_msg = history[msg_idx]
            if assistant_msg["role"] != "assistant":
                continue
            # Find preceding user message
            user_msg = ""
            if msg_idx > 0 and history[msg_idx - 1]["role"] == "user":
                user_msg = history[msg_idx - 1]["content"]

            candidates.append({
                "feedback_id": rec["id"],
                "session_id": rec["session_id"],
                "question": user_msg,
                "answer": assistant_msg["content"],
                "created_at": rec["created_at"],
            })
        return {"candidates": candidates}
    except Exception as exc:
        log.error("Failed to fetch feedback candidates", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch candidates") from exc
