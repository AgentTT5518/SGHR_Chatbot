"""
Tests for backend.memory.profile_store — CRUD, merge logic, stale cleanup.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import aiosqlite
import pytest

from backend.memory import profile_store


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path):
    """Point profile_store at a temporary SQLite database."""
    db_path = str(tmp_path / "test_profiles.db")
    with patch.object(profile_store, "DB_PATH", db_path):
        asyncio.get_event_loop().run_until_complete(profile_store.init_profile_db())
        yield


# ── CRUD ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_get_profile():
    await profile_store.upsert_profile("user-1", {
        "employment_type": "full-time",
        "salary_bracket": "$3000-$4000",
        "tenure_years": 2.5,
        "company": "Acme Corp",
    })
    profile = await profile_store.get_profile("user-1")
    assert profile is not None
    assert profile["employment_type"] == "full-time"
    assert profile["salary_bracket"] == "$3000-$4000"
    assert profile["tenure_years"] == 2.5
    assert profile["company"] == "Acme Corp"


@pytest.mark.asyncio
async def test_get_nonexistent_profile():
    profile = await profile_store.get_profile("nonexistent")
    assert profile is None


@pytest.mark.asyncio
async def test_delete_profile():
    await profile_store.upsert_profile("user-del", {"company": "DeleteCo"})
    await profile_store.delete_profile("user-del")
    assert await profile_store.get_profile("user-del") is None


# ── Merge logic ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_merge_does_not_overwrite_with_nulls():
    await profile_store.upsert_profile("user-merge", {
        "employment_type": "full-time",
        "company": "OrigCo",
    })
    # Update with partial facts — should NOT overwrite company
    await profile_store.upsert_profile("user-merge", {
        "salary_bracket": "$5000-$6000",
    })
    profile = await profile_store.get_profile("user-merge")
    assert profile["company"] == "OrigCo"
    assert profile["salary_bracket"] == "$5000-$6000"
    assert profile["employment_type"] == "full-time"


@pytest.mark.asyncio
async def test_merge_does_not_overwrite_with_empty_string():
    await profile_store.upsert_profile("user-empty", {
        "company": "SolidCo",
    })
    await profile_store.upsert_profile("user-empty", {
        "company": "",
    })
    profile = await profile_store.get_profile("user-empty")
    assert profile["company"] == "SolidCo"


@pytest.mark.asyncio
async def test_merge_topics_deduplicated():
    await profile_store.upsert_profile("user-topics", {
        "topics": ["leave", "salary"],
    })
    await profile_store.upsert_profile("user-topics", {
        "topics": ["salary", "termination"],
    })
    profile = await profile_store.get_profile("user-topics")
    assert profile["topics"] == ["leave", "salary", "termination"]


@pytest.mark.asyncio
async def test_merge_preferences():
    await profile_store.upsert_profile("user-prefs", {
        "preferences": {"lang": "en"},
    })
    await profile_store.upsert_profile("user-prefs", {
        "preferences": {"detail": "brief"},
    })
    profile = await profile_store.get_profile("user-prefs")
    assert profile["preferences"]["lang"] == "en"
    assert profile["preferences"]["detail"] == "brief"


# ── Stale cleanup ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cleanup_stale_profiles():
    await profile_store.upsert_profile("user-fresh", {"company": "Fresh"})
    await profile_store.upsert_profile("user-stale", {"company": "Stale"})

    # Manually backdate the stale profile
    async with profile_store._get_conn() as conn:
        old_date = (datetime.now(timezone.utc) - timedelta(days=800)).isoformat()
        await conn.execute(
            "UPDATE user_profiles SET updated_at = ? WHERE user_id = ?",
            (old_date, "user-stale"),
        )
        await conn.commit()

    deleted = await profile_store.cleanup_stale_profiles(retention_years=2)
    assert deleted == 1
    assert await profile_store.get_profile("user-fresh") is not None
    assert await profile_store.get_profile("user-stale") is None
