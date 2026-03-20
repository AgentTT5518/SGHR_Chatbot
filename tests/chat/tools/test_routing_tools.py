"""Tests for routing tools: eligibility checks and escalation."""
from __future__ import annotations

import pytest
import pytest_asyncio

from backend.chat.tools.routing_tools import check_eligibility, escalate_to_hr
from backend.chat.session_manager import init_db, get_escalations, get_or_create


@pytest_asyncio.fixture(autouse=True)
async def _setup_db(tmp_path, monkeypatch):
    """Use a temporary database for escalation tests."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("backend.chat.session_manager.DB_PATH", db_path)
    await init_db()


class TestCheckEligibility:

    @pytest.mark.asyncio
    async def test_workman_under_cap_covered_part_iv(self):
        result = await check_eligibility(
            {"salary_monthly": 4000, "role": "workman", "employment_type": "full_time"}
        )
        assert "YES" in result
        assert "Part IV" in result

    @pytest.mark.asyncio
    async def test_workman_over_cap_not_covered_part_iv(self):
        result = await check_eligibility(
            {"salary_monthly": 5000, "role": "workman", "employment_type": "full_time"}
        )
        assert "NO" in result
        assert "Part IV" in result

    @pytest.mark.asyncio
    async def test_non_workman_under_2600_covered(self):
        result = await check_eligibility(
            {"salary_monthly": 2000, "role": "non_workman", "employment_type": "full_time"}
        )
        assert "YES" in result

    @pytest.mark.asyncio
    async def test_non_workman_over_2600_not_covered(self):
        result = await check_eligibility(
            {"salary_monthly": 3000, "role": "non_workman", "employment_type": "full_time"}
        )
        assert "NO" in result

    @pytest.mark.asyncio
    async def test_manager_executive_not_covered_part_iv(self):
        result = await check_eligibility(
            {"salary_monthly": 5000, "role": "manager_executive", "employment_type": "full_time"}
        )
        assert "NO" in result
        assert "Manager" in result or "manager" in result

    @pytest.mark.asyncio
    async def test_manager_still_covered_by_ea_general(self):
        result = await check_eligibility(
            {"salary_monthly": 8000, "role": "manager_executive", "employment_type": "full_time"}
        )
        assert "ARE covered" in result or "covered by the Employment Act" in result


class TestEscalateToHr:

    @pytest.mark.asyncio
    async def test_creates_escalation_record(self):
        await get_or_create("test-session-123")
        result = await escalate_to_hr(
            {"reason": "Complex dispute", "session_id": "test-session-123"}
        )
        assert "ESC-" in result
        assert "HR review" in result

        # Verify record in DB
        records = await get_escalations()
        assert len(records) >= 1
        record = [r for r in records if r["session_id"] == "test-session-123"][0]
        assert record["reason"] == "Complex dispute"
        assert record["status"] == "pending"

    @pytest.mark.asyncio
    async def test_returns_reference_id(self):
        await get_or_create("sess-456")
        result = await escalate_to_hr(
            {"reason": "Legal question", "session_id": "sess-456"}
        )
        # Should contain ESC-<number>
        assert "ESC-" in result
