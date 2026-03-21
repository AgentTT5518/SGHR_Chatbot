"""
Profile routes — user profile CRUD for privacy compliance.
GET    /api/profile/{user_id} — return profile (for future settings page)
DELETE /api/profile/{user_id} — delete profile (privacy compliance)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.lib.logger import get_logger

log = get_logger("api.routes_profile")

router = APIRouter(prefix="/api/profile")


@router.get("/{user_id}")
async def get_profile(user_id: str):
    """Return a user's profile data."""
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
async def delete_profile(user_id: str):
    """Delete a user's profile (privacy compliance)."""
    from backend.memory.profile_store import delete_profile as _delete_profile
    try:
        await _delete_profile(user_id)
        return {"success": True, "message": "Profile deleted"}
    except Exception as exc:
        log.error("Failed to delete profile", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete profile") from exc
