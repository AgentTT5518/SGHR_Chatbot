"""
Profile memory store — persists user employment context across sessions.

Uses the same SQLite database as session_manager (backend/data/sessions.db).
Profiles merge new facts without overwriting existing non-null values.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import aiosqlite

from backend.config import SESSIONS_DB
from backend.lib.logger import get_logger

log = get_logger("memory.profile_store")

DB_PATH = str(SESSIONS_DB)

CREATE_PROFILE_TABLE = """
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    employment_type TEXT,
    salary_bracket TEXT,
    tenure_years REAL,
    company TEXT,
    topics_json TEXT DEFAULT '[]',
    preferences_json TEXT DEFAULT '{}',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


@asynccontextmanager
async def _get_conn():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn


async def init_profile_db() -> None:
    """Create user_profiles table if it doesn't exist."""
    from pathlib import Path
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with _get_conn() as conn:
        await conn.executescript(CREATE_PROFILE_TABLE)
        await conn.commit()
    log.info("Profile database initialised")


async def get_profile(user_id: str) -> dict | None:
    """Fetch a user profile. Returns None if not found."""
    async with _get_conn() as conn:
        cursor = await conn.execute(
            "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
    if not row:
        return None

    topics: list = []
    preferences: dict = {}
    try:
        topics = json.loads(row["topics_json"] or "[]")
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        preferences = json.loads(row["preferences_json"] or "{}")
    except (json.JSONDecodeError, TypeError):
        pass

    return {
        "user_id": row["user_id"],
        "employment_type": row["employment_type"],
        "salary_bracket": row["salary_bracket"],
        "tenure_years": row["tenure_years"],
        "company": row["company"],
        "topics": topics,
        "preferences": preferences,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def upsert_profile(user_id: str, facts: dict) -> None:
    """Merge new facts into existing profile — never overwrite with nulls/empty."""
    now = datetime.now(timezone.utc).isoformat()
    existing = await get_profile(user_id)

    if existing is None:
        # Insert new profile
        topics = facts.get("topics", [])
        preferences = facts.get("preferences", {})
        async with _get_conn() as conn:
            await conn.execute(
                """INSERT INTO user_profiles
                   (user_id, employment_type, salary_bracket, tenure_years,
                    company, topics_json, preferences_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    facts.get("employment_type"),
                    facts.get("salary_bracket"),
                    facts.get("tenure_years"),
                    facts.get("company"),
                    json.dumps(topics),
                    json.dumps(preferences),
                    now,
                    now,
                ),
            )
            await conn.commit()
        log.info("Created new profile", extra={"user_id": user_id})
        return

    # Merge: only overwrite with non-null, non-empty values
    merged: dict = {}
    for field in ("employment_type", "salary_bracket", "company"):
        new_val = facts.get(field)
        if new_val is not None and new_val != "":
            merged[field] = new_val
        else:
            merged[field] = existing.get(field)

    # tenure_years: numeric, overwrite if provided
    new_tenure = facts.get("tenure_years")
    if new_tenure is not None:
        merged["tenure_years"] = new_tenure
    else:
        merged["tenure_years"] = existing.get("tenure_years")

    # topics: merge lists (deduplicate)
    new_topics = facts.get("topics", [])
    existing_topics = existing.get("topics", [])
    merged_topics = list(dict.fromkeys(existing_topics + new_topics))

    # preferences: merge dicts
    existing_prefs = existing.get("preferences", {})
    new_prefs = facts.get("preferences", {})
    merged_prefs = {**existing_prefs, **{k: v for k, v in new_prefs.items() if v is not None}}

    async with _get_conn() as conn:
        await conn.execute(
            """UPDATE user_profiles SET
               employment_type = ?, salary_bracket = ?, tenure_years = ?,
               company = ?, topics_json = ?, preferences_json = ?, updated_at = ?
               WHERE user_id = ?""",
            (
                merged["employment_type"],
                merged["salary_bracket"],
                merged["tenure_years"],
                merged["company"],
                json.dumps(merged_topics),
                json.dumps(merged_prefs),
                now,
                user_id,
            ),
        )
        await conn.commit()
    log.info("Updated profile", extra={"user_id": user_id})


async def delete_profile(user_id: str) -> None:
    """Delete a user profile (privacy compliance)."""
    async with _get_conn() as conn:
        await conn.execute(
            "DELETE FROM user_profiles WHERE user_id = ?", (user_id,)
        )
        await conn.commit()
    log.info("Deleted profile", extra={"user_id": user_id})


async def cleanup_stale_profiles(retention_years: int = 2) -> int:
    """Delete profiles not updated in N years. Returns count deleted."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_years * 365)).isoformat()
    async with _get_conn() as conn:
        cursor = await conn.execute(
            "DELETE FROM user_profiles WHERE updated_at < ?", (cutoff,)
        )
        await conn.commit()
        deleted = cursor.rowcount
    if deleted:
        log.info("Cleaned stale profiles", extra={"deleted": deleted})
    return deleted
