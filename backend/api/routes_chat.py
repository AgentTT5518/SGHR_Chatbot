"""
Chat API routes.
POST /api/chat        — stream a RAG response (SSE)
GET  /api/sessions/{session_id}/history — fetch conversation history
DELETE /api/sessions/{session_id}       — delete a session
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.chat import rag_chain, session_manager

router = APIRouter(prefix="/api")


class ChatRequest(BaseModel):
    session_id: str
    message: str
    user_role: str = "employee"  # "employee" | "hr"


@router.post("/chat")
async def chat(req: ChatRequest):
    return StreamingResponse(
        rag_chain.stream_rag_response(
            session_id=req.session_id,
            user_message=req.message,
            user_role=req.user_role,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable Nginx buffering for SSE
        },
    )


@router.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str):
    if not await session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await session_manager.get_full_history(session_id)
    return {"session_id": session_id, "messages": messages}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    await session_manager.delete_session(session_id)
    return {"success": True}
