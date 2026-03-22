"""
Admin API key authentication dependency.

All ``/admin/*`` and ``/metrics`` endpoints require the ``X-Admin-Key``
header to match ``settings.admin_api_key``.  There is no environment-based
bypass — in development, use the default key from ``.env.example``
(``dev-only-key``).
"""
from fastapi import HTTPException, Request

from backend.config import settings
from backend.lib.logger import get_logger

log = get_logger("lib.admin_auth")


async def require_admin(request: Request) -> None:
    """FastAPI ``Depends()`` that enforces admin API key auth.

    Raises:
        HTTPException 401 — key header missing
        HTTPException 403 — key does not match
    """
    key = request.headers.get("X-Admin-Key", "")
    if not key:
        raise HTTPException(status_code=401, detail="Admin API key required")
    if key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid admin API key")

    # Audit trail
    log.info(
        "Admin action authorised",
        extra={
            "method": request.method,
            "path": str(request.url.path),
            "admin_ip": request.client.host if request.client else "unknown",
        },
    )
