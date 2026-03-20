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
from backend.lib.logger import get_logger

log = get_logger(__name__)

DB_PATH = str(SESSIONS_DB)

CREATE_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT,
    summary TEXT DEFAULT '',
    session_facts_json TEXT DEFAULT '{}',
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

CREATE TABLE IF NOT EXISTS escalations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'reviewed', 'resolved')),
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


async def _migrate_schema(conn: aiosqlite.Connection) -> None:
    """Add columns introduced after initial release (idempotent)."""
    cursor = await conn.execute("PRAGMA table_info(sessions)")
    existing = {row[1] for row in await cursor.fetchall()}

    migrations = [
        ("user_id", "ALTER TABLE sessions ADD COLUMN user_id TEXT"),
        ("summary", "ALTER TABLE sessions ADD COLUMN summary TEXT DEFAULT ''"),
        ("session_facts_json", "ALTER TABLE sessions ADD COLUMN session_facts_json TEXT DEFAULT '{}'"),
    ]
    for col, sql in migrations:
        if col not in existing:
            await conn.execute(sql)
            log.info("Migrated sessions table", extra={"added_column": col})
    await conn.commit()


async def init_db():
    """Create tables if they don't exist."""
    from pathlib import Path
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with _get_conn() as conn:
        await conn.executescript(CREATE_SCHEMA)
        await _migrate_schema(conn)
        await conn.commit()


async def get_or_create(session_id: str, user_id: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with _get_conn() as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id, user_id, created_at, last_active) VALUES (?, ?, ?, ?)",
            (session_id, user_id, now, now),
        )
        # Update user_id if provided and session already exists without one
        if user_id:
            await conn.execute(
                "UPDATE sessions SET user_id = ? WHERE session_id = ? AND (user_id IS NULL OR user_id = '')",
                (user_id, session_id),
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


async def update_summary(session_id: str, summary: str) -> None:
    """Update the running conversation summary for a session."""
    async with _get_conn() as conn:
        await conn.execute(
            "UPDATE sessions SET summary = ? WHERE session_id = ?",
            (summary, session_id),
        )
        await conn.commit()


async def update_session_facts(session_id: str, facts: dict) -> None:
    """Update extracted session facts (merge with existing)."""
    import json
    async with _get_conn() as conn:
        # Fetch existing facts and merge
        cursor = await conn.execute(
            "SELECT session_facts_json FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        existing: dict = {}
        if row and row["session_facts_json"]:
            try:
                existing = json.loads(row["session_facts_json"])
            except (json.JSONDecodeError, TypeError):
                existing = {}
        # Merge: new values overwrite, but don't overwrite with None/empty
        for k, v in facts.items():
            if v is not None and v != "":
                existing[k] = v
        await conn.execute(
            "UPDATE sessions SET session_facts_json = ? WHERE session_id = ?",
            (json.dumps(existing), session_id),
        )
        await conn.commit()


async def get_session_context(session_id: str) -> dict:
    """Return summary, facts, and message count for a session."""
    import json
    async with _get_conn() as conn:
        cursor = await conn.execute(
            "SELECT summary, session_facts_json FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return {"summary": "", "facts": {}, "message_count": 0}

        facts: dict = {}
        if row["session_facts_json"]:
            try:
                facts = json.loads(row["session_facts_json"])
            except (json.JSONDecodeError, TypeError):
                facts = {}

        # Get message count
        count_cursor = await conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?",
            (session_id,),
        )
        count_row = await count_cursor.fetchone()
        msg_count = count_row["cnt"] if count_row else 0

    return {
        "summary": row["summary"] or "",
        "facts": facts,
        "message_count": msg_count,
    }


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
                log.info("Cleaned up stale sessions", extra={"deleted": deleted})
        except asyncio.CancelledError:
            break
        except Exception:
            log.error("Session cleanup error", exc_info=True)


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


# ── Escalations ──────────────────────────────────────────────────────────────

async def create_escalation(session_id: str, reason: str) -> int:
    """Create an escalation record. Returns the new escalation ID."""
    async with _get_conn() as conn:
        cursor = await conn.execute(
            "INSERT INTO escalations (session_id, reason) VALUES (?, ?)",
            (session_id, reason),
        )
        await conn.commit()
        return cursor.lastrowid


async def get_escalations(
    status: str | None = None, limit: int = 50, offset: int = 0
) -> list[dict]:
    """Fetch escalation records newest-first with optional status filter."""
    async with _get_conn() as conn:
        if status:
            cursor = await conn.execute(
                """
                SELECT id, session_id, reason, status, created_at
                FROM escalations
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (status, limit, offset),
            )
        else:
            cursor = await conn.execute(
                """
                SELECT id, session_id, reason, status, created_at
                FROM escalations
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
            "reason": row["reason"],
            "status": row["status"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


async def update_escalation_status(escalation_id: int, status: str) -> bool:
    """Update an escalation's status. Returns True if a row was updated."""
    async with _get_conn() as conn:
        cursor = await conn.execute(
            "UPDATE escalations SET status = ? WHERE id = ?",
            (status, escalation_id),
        )
        await conn.commit()
        return cursor.rowcount > 0
