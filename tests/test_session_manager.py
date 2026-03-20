"""
Tests for backend.chat.session_manager — session CRUD, user_id, summary, facts.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import pytest_asyncio

from backend.chat import session_manager


@pytest_asyncio.fixture(autouse=True)
async def fresh_db(tmp_path):
    """Point session_manager at a temp DB for each test."""
    db_path = str(tmp_path / "test_sessions.db")
    with patch.object(session_manager, "DB_PATH", db_path):
        await session_manager.init_db()
        yield


# ── get_or_create with user_id ───────────────────────────────────────────────


class TestGetOrCreateUserId:
    @pytest.mark.asyncio
    async def test_creates_session_with_user_id(self):
        await session_manager.get_or_create("sess-1", user_id="user-abc")
        ctx = await session_manager.get_session_context("sess-1")
        assert ctx["message_count"] == 0

        # Verify user_id was stored
        async with session_manager._get_conn() as conn:
            cursor = await conn.execute(
                "SELECT user_id FROM sessions WHERE session_id = ?", ("sess-1",)
            )
            row = await cursor.fetchone()
        assert row["user_id"] == "user-abc"

    @pytest.mark.asyncio
    async def test_creates_session_without_user_id(self):
        """Backward compatibility: user_id is optional."""
        await session_manager.get_or_create("sess-2")
        exists = await session_manager.session_exists("sess-2")
        assert exists

    @pytest.mark.asyncio
    async def test_updates_null_user_id_on_second_call(self):
        """If session was created without user_id, a later call fills it in."""
        await session_manager.get_or_create("sess-3")
        await session_manager.get_or_create("sess-3", user_id="user-xyz")

        async with session_manager._get_conn() as conn:
            cursor = await conn.execute(
                "SELECT user_id FROM sessions WHERE session_id = ?", ("sess-3",)
            )
            row = await cursor.fetchone()
        assert row["user_id"] == "user-xyz"

    @pytest.mark.asyncio
    async def test_does_not_overwrite_existing_user_id(self):
        """Once set, user_id should not be overwritten."""
        await session_manager.get_or_create("sess-4", user_id="user-original")
        await session_manager.get_or_create("sess-4", user_id="user-new")

        async with session_manager._get_conn() as conn:
            cursor = await conn.execute(
                "SELECT user_id FROM sessions WHERE session_id = ?", ("sess-4",)
            )
            row = await cursor.fetchone()
        assert row["user_id"] == "user-original"


# ── Summary and facts ────────────────────────────────────────────────────────


class TestSummaryAndFacts:
    @pytest.mark.asyncio
    async def test_update_and_get_summary(self):
        await session_manager.get_or_create("sess-sum")
        await session_manager.update_summary("sess-sum", "User asked about leave.")
        ctx = await session_manager.get_session_context("sess-sum")
        assert ctx["summary"] == "User asked about leave."

    @pytest.mark.asyncio
    async def test_update_and_get_facts(self):
        await session_manager.get_or_create("sess-fact")
        await session_manager.update_session_facts("sess-fact", {"employment_type": "full-time", "tenure_years": 3})
        ctx = await session_manager.get_session_context("sess-fact")
        assert ctx["facts"]["employment_type"] == "full-time"
        assert ctx["facts"]["tenure_years"] == 3

    @pytest.mark.asyncio
    async def test_facts_merge_preserves_existing(self):
        """New facts merge with existing; None values don't overwrite."""
        await session_manager.get_or_create("sess-merge")
        await session_manager.update_session_facts("sess-merge", {"employment_type": "full-time", "salary": 5000})
        await session_manager.update_session_facts("sess-merge", {"tenure_years": 2, "salary": None})
        ctx = await session_manager.get_session_context("sess-merge")
        assert ctx["facts"]["employment_type"] == "full-time"
        assert ctx["facts"]["salary"] == 5000  # not overwritten by None
        assert ctx["facts"]["tenure_years"] == 2

    @pytest.mark.asyncio
    async def test_get_session_context_nonexistent(self):
        ctx = await session_manager.get_session_context("no-such-session")
        assert ctx["summary"] == ""
        assert ctx["facts"] == {}
        assert ctx["message_count"] == 0

    @pytest.mark.asyncio
    async def test_message_count_in_context(self):
        await session_manager.get_or_create("sess-count")
        await session_manager.add_message("sess-count", "user", "Hello")
        await session_manager.add_message("sess-count", "assistant", "Hi there!")
        ctx = await session_manager.get_session_context("sess-count")
        assert ctx["message_count"] == 2
