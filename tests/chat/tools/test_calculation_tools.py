"""Tests for calculation tools: leave entitlement and notice period."""
from __future__ import annotations

import pytest

from backend.chat.tools.calculation_tools import (
    EA_RULES_VERSION,
    calculate_leave_entitlement,
    calculate_notice_period,
)


class TestAnnualLeave:

    @pytest.mark.asyncio
    async def test_year_1_gives_7_days(self):
        result = await calculate_leave_entitlement(
            {"tenure_years": 1, "employment_type": "full_time", "leave_type": "annual"}
        )
        assert "7 days" in result
        assert "s 43" in result

    @pytest.mark.asyncio
    async def test_year_3_gives_9_days(self):
        result = await calculate_leave_entitlement(
            {"tenure_years": 3, "employment_type": "full_time", "leave_type": "annual"}
        )
        assert "9 days" in result

    @pytest.mark.asyncio
    async def test_year_8_gives_14_days(self):
        result = await calculate_leave_entitlement(
            {"tenure_years": 8, "employment_type": "full_time", "leave_type": "annual"}
        )
        assert "14 days" in result

    @pytest.mark.asyncio
    async def test_year_10_gives_14_days(self):
        result = await calculate_leave_entitlement(
            {"tenure_years": 10, "employment_type": "full_time", "leave_type": "annual"}
        )
        assert "14 days" in result

    @pytest.mark.asyncio
    async def test_under_1_year(self):
        result = await calculate_leave_entitlement(
            {"tenure_years": 0.5, "employment_type": "full_time", "leave_type": "annual"}
        )
        assert "3 months" in result.lower() or "1 completed year" in result.lower()

    @pytest.mark.asyncio
    async def test_part_time_prorated(self):
        result = await calculate_leave_entitlement(
            {"tenure_years": 2, "employment_type": "part_time", "leave_type": "annual"}
        )
        assert "pro-rate" in result.lower() or "Part-Time" in result


class TestSickLeave:

    @pytest.mark.asyncio
    async def test_full_entitlement(self):
        result = await calculate_leave_entitlement(
            {"tenure_years": 1, "employment_type": "full_time", "leave_type": "sick"}
        )
        assert "14 days" in result
        assert "60 days" in result

    @pytest.mark.asyncio
    async def test_under_3_months(self):
        result = await calculate_leave_entitlement(
            {"tenure_years": 0.1, "employment_type": "full_time", "leave_type": "sick"}
        )
        assert "3 months" in result


class TestMaternityLeave:

    @pytest.mark.asyncio
    async def test_eligible(self):
        result = await calculate_leave_entitlement(
            {"tenure_years": 1, "employment_type": "full_time", "leave_type": "maternity"}
        )
        assert "16 weeks" in result

    @pytest.mark.asyncio
    async def test_under_3_months(self):
        result = await calculate_leave_entitlement(
            {"tenure_years": 0.1, "employment_type": "full_time", "leave_type": "maternity"}
        )
        assert "3 months" in result


class TestPaternityLeave:

    @pytest.mark.asyncio
    async def test_entitlement(self):
        result = await calculate_leave_entitlement(
            {"tenure_years": 1, "employment_type": "full_time", "leave_type": "paternity"}
        )
        assert "2 weeks" in result


class TestChildcareLeave:

    @pytest.mark.asyncio
    async def test_eligible(self):
        result = await calculate_leave_entitlement(
            {"tenure_years": 1, "employment_type": "full_time", "leave_type": "childcare"}
        )
        assert "6 days" in result

    @pytest.mark.asyncio
    async def test_under_3_months(self):
        result = await calculate_leave_entitlement(
            {"tenure_years": 0.1, "employment_type": "full_time", "leave_type": "childcare"}
        )
        assert "3 months" in result


class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_negative_tenure(self):
        result = await calculate_leave_entitlement(
            {"tenure_years": -1, "employment_type": "full_time", "leave_type": "annual"}
        )
        assert "Error" in result or "negative" in result.lower()

    @pytest.mark.asyncio
    async def test_unknown_leave_type(self):
        result = await calculate_leave_entitlement(
            {"tenure_years": 1, "employment_type": "full_time", "leave_type": "bereavement"}
        )
        assert "Error" in result or "unknown" in result.lower()

    @pytest.mark.asyncio
    async def test_includes_ea_version(self):
        result = await calculate_leave_entitlement(
            {"tenure_years": 1, "employment_type": "full_time", "leave_type": "annual"}
        )
        assert EA_RULES_VERSION in result


class TestNoticePeriod:

    @pytest.mark.asyncio
    async def test_under_26_weeks(self):
        result = await calculate_notice_period({"tenure_years": 0.3})
        assert "1 day" in result
        assert "s 10" in result

    @pytest.mark.asyncio
    async def test_26_weeks_to_2_years(self):
        result = await calculate_notice_period({"tenure_years": 1})
        assert "1 week" in result

    @pytest.mark.asyncio
    async def test_2_to_5_years(self):
        result = await calculate_notice_period({"tenure_years": 3})
        assert "2 weeks" in result

    @pytest.mark.asyncio
    async def test_5_plus_years(self):
        result = await calculate_notice_period({"tenure_years": 6})
        assert "4 weeks" in result

    @pytest.mark.asyncio
    async def test_with_contract_notice(self):
        result = await calculate_notice_period(
            {"tenure_years": 1, "contract_notice": "1 month"}
        )
        assert "1 month" in result
        assert "contractual" in result.lower() or "Contractual" in result

    @pytest.mark.asyncio
    async def test_negative_tenure(self):
        result = await calculate_notice_period({"tenure_years": -1})
        assert "Error" in result
