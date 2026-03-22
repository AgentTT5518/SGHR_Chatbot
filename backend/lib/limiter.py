"""
Shared rate-limiter instance (slowapi).

Uses a composite key: ``X-Session-Token`` header (signed session ID)
when present, falling back to client IP.  This aligns with the session
signing scheme — the same header used for route protection is reused
for rate limiting.

Known limitation: without real user auth, a determined attacker can
create new sessions to bypass per-session limits.  Per-IP limiting
still applies as a backstop.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _get_session_or_ip(request: Request) -> str:
    """Rate-limit key: prefer signed session token, fall back to IP."""
    token = request.headers.get("X-Session-Token", "")
    if token:
        return f"session:{token}"
    return get_remote_address(request)


limiter = Limiter(key_func=_get_session_or_ip)
