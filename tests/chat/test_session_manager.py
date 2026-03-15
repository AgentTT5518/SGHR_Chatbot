"""
Tests for backend.chat.session_manager

Uses a temporary SQLite file per test so tests are fully isolated.
Patches DB_PATH in session_manager to redirect all queries to the temp DB.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

import backend.chat.session_manager as sm


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect session_manager to a fresh temp DB and initialise schema."""
    db_file = str(tmp_path / "test_sessions.db")
    monkeypatch.setattr(sm, "DB_PATH", db_file)
    await sm.init_db()
    yield db_file


# ── init_db ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_init_db_creates_tables(db):
    async with aiosqlite.connect(db) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in await cursor.fetchall()}
    assert "sessions" in tables
    assert "messages" in tables


# ── get_or_create ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_or_create_inserts_session(db):
    await sm.get_or_create("sess-001")
    assert await sm.session_exists("sess-001")


@pytest.mark.asyncio
async def test_get_or_create_is_idempotent(db):
    await sm.get_or_create("sess-002")
    await sm.get_or_create("sess-002")  # second call must not raise
    assert await sm.session_exists("sess-002")


# ── session_exists ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_exists_false_for_unknown(db):
    assert not await sm.session_exists("does-not-exist")


# ── add_message / get_history ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_and_get_history(db):
    await sm.get_or_create("sess-003")
    await sm.add_message("sess-003", "user", "What is annual leave?")
    await sm.add_message("sess-003", "assistant", "You are entitled to 7–14 days.")

    history = await sm.get_history("sess-003")
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "What is annual leave?"}
    assert history[1] == {"role": "assistant", "content": "You are entitled to 7–14 days."}


@pytest.mark.asyncio
async def test_get_history_respects_last_n_pairs(db):
    await sm.get_or_create("sess-004")
    for i in range(5):
        await sm.add_message("sess-004", "user", f"question {i}")
        await sm.add_message("sess-004", "assistant", f"answer {i}")

    history = await sm.get_history("sess-004", last_n_pairs=2)
    assert len(history) == 4
    # Should be the last 2 pairs (questions 3 and 4)
    assert history[0]["content"] == "question 3"
    assert history[-1]["content"] == "answer 4"


@pytest.mark.asyncio
async def test_get_history_empty_session(db):
    await sm.get_or_create("sess-005")
    history = await sm.get_history("sess-005")
    assert history == []


# ── get_full_history ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_full_history_includes_created_at(db):
    await sm.get_or_create("sess-006")
    await sm.add_message("sess-006", "user", "Hello")

    full = await sm.get_full_history("sess-006")
    assert len(full) == 1
    assert "created_at" in full[0]
    assert full[0]["role"] == "user"
    assert full[0]["content"] == "Hello"


# ── delete_session ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_session_removes_session_and_messages(db):
    await sm.get_or_create("sess-007")
    await sm.add_message("sess-007", "user", "test")

    await sm.delete_session("sess-007")

    assert not await sm.session_exists("sess-007")
    history = await sm.get_history("sess-007")
    assert history == []


@pytest.mark.asyncio
async def test_delete_nonexistent_session_is_safe(db):
    await sm.delete_session("ghost-session")  # must not raise


# ── cleanup_stale_sessions ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cleanup_removes_stale_sessions(db):
    await sm.get_or_create("stale-001")

    # Back-date last_active to 3 hours ago
    stale_time = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            "UPDATE sessions SET last_active = ? WHERE session_id = ?",
            (stale_time, "stale-001"),
        )
        await conn.commit()

    deleted = await sm.cleanup_stale_sessions(ttl_hours=2)
    assert deleted == 1
    assert not await sm.session_exists("stale-001")


@pytest.mark.asyncio
async def test_cleanup_keeps_active_sessions(db):
    await sm.get_or_create("active-001")

    deleted = await sm.cleanup_stale_sessions(ttl_hours=2)
    assert deleted == 0
    assert await sm.session_exists("active-001")


@pytest.mark.asyncio
async def test_cleanup_returns_zero_when_nothing_to_delete(db):
    deleted = await sm.cleanup_stale_sessions(ttl_hours=1)
    assert deleted == 0


# ── cleanup_loop ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cleanup_loop_cancels_cleanly(db):
    """cleanup_loop must exit without raising when cancelled."""
    task = asyncio.create_task(sm.cleanup_loop())
    await asyncio.sleep(0)  # yield to let the task start
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass  # expected during first asyncio.sleep inside the loop
    assert task.done()
