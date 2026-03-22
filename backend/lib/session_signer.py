"""
HMAC-based session ID signing and verification.

The server generates session IDs and signs them with HMAC-SHA256.
Clients receive and store the signed format: ``{uuid}.{signature}``.
"""
import hashlib
import hmac
import uuid

from backend.config import settings
from backend.lib.logger import get_logger

log = get_logger("lib.session_signer")


def create_signed_session() -> str:
    """Generate a new UUID and return it in signed form ``uuid.sig``."""
    session_id = str(uuid.uuid4())
    return _sign(session_id)


def verify_session_id(signed: str | None) -> str | None:
    """Validate a signed session token and return the raw session ID.

    Returns:
        The raw session UUID if valid, or ``None`` if the token is
        missing, empty, tampered, or an unsigned legacy ID when
        enforcement is enabled.
    """
    if not signed:
        return None

    parts = signed.rsplit(".", 1)

    # Signed format: uuid.signature
    if len(parts) == 2:
        session_id, sig = parts
        expected = _make_signature(session_id)
        if hmac.compare_digest(sig, expected):
            return session_id
        log.warning("Tampered session signature rejected")
        return None

    # Legacy unsigned format (no dot separator)
    if settings.session_signing_enforced:
        log.warning("Unsigned session ID rejected (enforcement enabled)")
        return None

    # Grace period: accept unsigned IDs
    log.info("Accepting unsigned legacy session ID (grace period)")
    return signed


def sign_existing(session_id: str) -> str:
    """Sign an existing raw session ID (e.g. for legacy migration)."""
    return _sign(session_id)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _sign(session_id: str) -> str:
    return f"{session_id}.{_make_signature(session_id)}"


def _make_signature(session_id: str) -> str:
    key = settings.effective_secret_key.encode()
    return hmac.new(key, session_id.encode(), hashlib.sha256).hexdigest()[:16]
