"""
Chat API routes.
POST /api/chat        — stream a RAG response (SSE)
GET  /api/sessions/{session_id}/history — fetch conversation history
DELETE /api/sessions/{session_id}       — delete a session
"""
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.chat import orchestrator, rag_chain, session_manager
from backend.config import settings
from backend.lib.limiter import limiter
from backend.lib.logger import get_logger
from backend.lib.session_signer import (
    create_signed_session,
    sign_existing,
    verify_session_id,
)

log = get_logger("api.routes_chat")

router = APIRouter(prefix="/api")


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    user_role: str = "employee"  # "employee" | "hr"
    user_id: str | None = None


def _resolve_session(raw_session_id: str | None) -> tuple[str, str]:
    """Return ``(raw_session_id, signed_session_token)``.

    Three cases:
    * ``None`` / empty → new session (server generates + signs)
    * Valid signed token → extract raw ID
    * Legacy unsigned ID → accept in grace period, sign it

    Raises HTTPException 403 if the token is tampered or unsigned when
    enforcement is enabled.
    """
    if not raw_session_id:
        signed = create_signed_session()
        raw = signed.rsplit(".", 1)[0]
        return raw, signed

    verified = verify_session_id(raw_session_id)
    if verified is None:
        raise HTTPException(status_code=403, detail="Invalid session token")

    # If the incoming value was unsigned (legacy), sign it for the client
    if "." not in raw_session_id:
        return verified, sign_existing(verified)

    return verified, raw_session_id


async def _inject_signed_session(
    inner_stream: AsyncGenerator[str, None],
    signed_token: str,
) -> AsyncGenerator[str, None]:
    """Wrap an SSE stream to inject ``signed_session_id`` into the done event."""
    async for chunk in inner_stream:
        if chunk.startswith("data: "):
            raw = chunk[6:].strip()
            if raw:
                try:
                    event = json.loads(raw)
                    if event.get("done"):
                        event["signed_session_id"] = signed_token
                        yield f"data: {json.dumps(event)}\n\n"
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass
        yield chunk


@router.post("/chat")
@limiter.limit(settings.chat_rate_limit)
async def chat(request: Request, req: ChatRequest):
    raw_id, signed_token = _resolve_session(req.session_id)

    if settings.use_orchestrator:
        stream = orchestrator.orchestrate(
            session_id=raw_id,
            user_id=req.user_id or "",
            user_message=req.message,
            user_role=req.user_role,
        )
    else:
        stream = rag_chain.stream_rag_response(
            session_id=raw_id,
            user_message=req.message,
            user_role=req.user_role,
            user_id=req.user_id,
        )
    return StreamingResponse(
        _inject_signed_session(stream, signed_token),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _verify_session_token(request: Request, session_id: str) -> str:
    """Verify the session from path param or X-Session-Token header.

    Returns the raw session ID on success; raises 403 on failure.
    """
    # Prefer the header (contains the signed token)
    token = request.headers.get("X-Session-Token", "") or session_id
    verified = verify_session_id(token)
    if verified is None:
        raise HTTPException(status_code=403, detail="Invalid session token")
    return verified


@router.get("/sessions/{session_id}/history")
async def get_session_history(request: Request, session_id: str):
    raw_id = _verify_session_token(request, session_id)
    if not await session_manager.session_exists(raw_id):
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await session_manager.get_full_history(raw_id)
    return {"session_id": raw_id, "messages": messages}


@router.delete("/sessions/{session_id}")
async def delete_session(request: Request, session_id: str):
    raw_id = _verify_session_token(request, session_id)
    await session_manager.delete_session(raw_id)
    return {"success": True}
