"""
Profile routes — user profile CRUD for privacy compliance.
GET    /api/profile/{user_id} — return profile (requires valid session or admin)
DELETE /api/profile/{user_id} — delete profile (requires admin key)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from backend.config import settings
from backend.lib.limiter import limiter
from backend.lib.logger import get_logger
from backend.lib.session_signer import verify_session_id

log = get_logger("api.routes_profile")

router = APIRouter(prefix="/api/profile")


def _require_session_or_admin(request: Request) -> None:
    """Allow access if the caller has a valid session token or admin key."""
    admin_key = request.headers.get("X-Admin-Key", "")
    if admin_key == settings.admin_api_key:
        return

    token = request.headers.get("X-Session-Token", "")
    if token and verify_session_id(token) is not None:
        return

    raise HTTPException(status_code=403, detail="Valid session token or admin key required")


def _require_admin(request: Request) -> None:
    """Allow access only with a valid admin key."""
    key = request.headers.get("X-Admin-Key", "")
    if not key:
        raise HTTPException(status_code=401, detail="Admin API key required")
    if key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid admin API key")


@router.get("/{user_id}")
@limiter.limit(settings.profile_rate_limit)
async def get_profile(request: Request, user_id: str):
    """Return a user's profile data. Requires a valid session or admin key."""
    _require_session_or_admin(request)
    from backend.memory.profile_store import get_profile as _get_profile
    try:
        profile = await _get_profile(user_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        return profile
    except HTTPException:
        raise
    except Exception as exc:
        log.error("Failed to fetch profile", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch profile") from exc


@router.delete("/{user_id}")
@limiter.limit(settings.profile_rate_limit)
async def delete_profile(request: Request, user_id: str):
    """Delete a user's profile (privacy compliance). Requires admin key."""
    _require_admin(request)
    from backend.memory.profile_store import delete_profile as _delete_profile
    try:
        await _delete_profile(user_id)
        return {"success": True, "message": "Profile deleted"}
    except Exception as exc:
        log.error("Failed to delete profile", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete profile") from exc
