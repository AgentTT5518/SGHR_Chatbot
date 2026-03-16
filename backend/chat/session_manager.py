"""
SQLite-backed session manager using aiosqlite.
Stores conversation history across server restarts.
Foreign keys with ON DELETE CASCADE handle message cleanup automatically.
"""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import aiosqlite

from backend.config import SESSIONS_DB, settings

DB_PATH = str(SESSIONS_DB)

CREATE_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_active DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    message_index INTEGER NOT NULL,
    rating TEXT NOT NULL CHECK(rating IN ('up', 'down')),
    comment TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
"""


@asynccontextmanager
async def _get_conn():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = aiosqlite.Row
        yield conn


async def init_db():
    """Create tables if they don't exist."""
    from pathlib import Path
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with _get_conn() as conn:
        await conn.executescript(CREATE_SCHEMA)
        await conn.commit()


async def get_or_create(session_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with _get_conn() as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id, created_at, last_active) VALUES (?, ?, ?)",
            (session_id, now, now),
        )
        await conn.commit()


async def add_message(session_id: str, role: str, content: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with _get_conn() as conn:
        await conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        await conn.execute(
            "UPDATE sessions SET last_active = ? WHERE session_id = ?",
            (now, session_id),
        )
        await conn.commit()


async def get_history(session_id: str, last_n_pairs: int | None = None) -> list[dict]:
    """
    Fetch conversation history for a session.
    Returns messages as list of {role, content} dicts (oldest first).
    last_n_pairs: if set, returns only the last N user+assistant pairs (2N messages).
    """
    if last_n_pairs is None:
        last_n_pairs = settings.session_history_pairs

    limit = last_n_pairs * 2
    async with _get_conn() as conn:
        cursor = await conn.execute(
            """
            SELECT role, content FROM (
                SELECT id, role, content, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
            ) ORDER BY created_at ASC, id ASC
            """,
            (session_id, limit),
        )
        rows = await cursor.fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


async def get_full_history(session_id: str) -> list[dict]:
    """Fetch all messages for a session (used by the history API endpoint)."""
    async with _get_conn() as conn:
        cursor = await conn.execute(
            "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY created_at ASC, id ASC",
            (session_id,),
        )
        rows = await cursor.fetchall()
    return [{"role": row["role"], "content": row["content"], "created_at": row["created_at"]} for row in rows]


async def session_exists(session_id: str) -> bool:
    async with _get_conn() as conn:
        cursor = await conn.execute(
            "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
        )
        return await cursor.fetchone() is not None


async def delete_session(session_id: str) -> None:
    """Delete session and its messages (cascades automatically)."""
    async with _get_conn() as conn:
        await conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        await conn.commit()


async def cleanup_stale_sessions(ttl_hours: int | None = None) -> int:
    """Delete sessions inactive longer than ttl_hours. Returns count deleted."""
    if ttl_hours is None:
        ttl_hours = settings.session_ttl_hours
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=ttl_hours)).isoformat()
    async with _get_conn() as conn:
        cursor = await conn.execute(
            "DELETE FROM sessions WHERE last_active < ?", (cutoff,)
        )
        await conn.commit()
        return cursor.rowcount


async def cleanup_loop():
    """Background task: periodically evict stale sessions."""
    while True:
        try:
            await asyncio.sleep(3600)  # run every hour
            deleted = await cleanup_stale_sessions()
            if deleted:
                print(f"[session_manager] Cleaned up {deleted} stale sessions")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[session_manager] Cleanup error: {e}")


async def add_feedback(
    session_id: str,
    message_index: int,
    rating: str,
    comment: str | None = None,
) -> int:
    """Insert a feedback record. Returns the new row id."""
    async with _get_conn() as conn:
        cursor = await conn.execute(
            "INSERT INTO feedback (session_id, message_index, rating, comment) VALUES (?, ?, ?, ?)",
            (session_id, message_index, rating, comment),
        )
        await conn.commit()
        return cursor.lastrowid


async def get_feedback(limit: int = 50, offset: int = 0) -> list[dict]:
    """Fetch feedback records newest-first with pagination."""
    async with _get_conn() as conn:
        cursor = await conn.execute(
            """
            SELECT id, session_id, message_index, rating, comment, created_at
            FROM feedback
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = await cursor.fetchall()
    return [
        {
            "id": row["id"],
            "session_id": row["session_id"],
            "message_index": row["message_index"],
            "rating": row["rating"],
            "comment": row["comment"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


async def get_feedback_stats() -> dict:
    """Return aggregate counts: total, up, down."""
    async with _get_conn() as conn:
        cursor = await conn.execute(
            "SELECT rating, COUNT(*) as cnt FROM feedback GROUP BY rating"
        )
        rows = await cursor.fetchall()
    stats = {"total": 0, "up": 0, "down": 0}
    for row in rows:
        stats[row["rating"]] = row["cnt"]
        stats["total"] += row["cnt"]
    return stats
