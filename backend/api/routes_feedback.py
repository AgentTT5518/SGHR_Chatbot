"""
Feedback routes.
POST /api/feedback       — record thumbs up/down on an assistant message
GET  /admin/feedback     — list feedback records (paginated)
GET  /admin/feedback/stats — aggregate up/down counts
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from backend.chat import session_manager
from backend.config import settings
from backend.lib.admin_auth import require_admin
from backend.lib.limiter import limiter
from backend.lib.logger import get_logger

log = get_logger("api.routes_feedback")

router = APIRouter()


class FeedbackRequest(BaseModel):
    session_id: str
    message_index: int
    rating: str  # "up" | "down"
    comment: str | None = None

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: str) -> str:
        if v not in ("up", "down"):
            raise ValueError("rating must be 'up' or 'down'")
        return v


@router.post("/api/feedback", status_code=201)
@limiter.limit(settings.feedback_rate_limit)
async def submit_feedback(request: Request, req: FeedbackRequest):
    """Record a thumbs-up or thumbs-down on an assistant message.

    Validates that the session exists to prevent feedback for non-existent
    sessions.  Accepts a signed session token via ``X-Session-Token`` header
    or the raw session ID in the body (grace period).
    """
    from backend.lib.session_signer import verify_session_id

    # Verify the session token if provided in header
    token = request.headers.get("X-Session-Token", "")
    if token:
        verified = verify_session_id(token)
        if verified is None:
            raise HTTPException(status_code=403, detail="Invalid session token")

    # Verify the session exists in the database
    if not await session_manager.session_exists(req.session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        row_id = await session_manager.add_feedback(
            session_id=req.session_id,
            message_index=req.message_index,
            rating=req.rating,
            comment=req.comment,
        )
        log.info(
            "Feedback recorded",
            extra={"session_id": req.session_id, "rating": req.rating, "row_id": row_id},
        )
        return {"success": True, "id": row_id}
    except Exception as exc:
        log.error("Failed to record feedback", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to record feedback") from exc


@router.get("/admin/feedback", dependencies=[Depends(require_admin)])
async def list_feedback(limit: int = 50, offset: int = 0):
    """Paginated list of feedback records, newest first."""
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")
    try:
        records = await session_manager.get_feedback(limit=limit, offset=offset)
        return {"limit": limit, "offset": offset, "records": records}
    except Exception as exc:
        log.error("Failed to fetch feedback", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch feedback") from exc


@router.get("/admin/feedback/stats", dependencies=[Depends(require_admin)])
async def feedback_stats():
    """Aggregate up/down counts."""
    try:
        return await session_manager.get_feedback_stats()
    except Exception as exc:
        log.error("Failed to fetch feedback stats", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch feedback stats") from exc
