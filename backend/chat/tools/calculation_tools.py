"""
Calculation tools: deterministic Python calculations for Singapore Employment Act
entitlements. Every result cites the EA section it derives from.

Rules are based on the Employment Act (Cap. 91) as at January 2025.
"""
from __future__ import annotations

from typing import Any

from backend.lib.logger import get_logger

log = get_logger("chat.tools.calculation_tools")

EA_RULES_VERSION = "2025-01"


# ── Annual Leave (EA s43) ────────────────────────────────────────────────────

_ANNUAL_LEAVE_TABLE: dict[int, int] = {
    1: 7, 2: 8, 3: 9, 4: 10, 5: 11, 6: 12, 7: 13,
}
_ANNUAL_LEAVE_MAX = 14  # 8+ years


def _calc_annual_leave(tenure_years: float, employment_type: str) -> str:
    completed = int(tenure_years)
    if completed < 1:
        return (
            "Annual leave entitlement begins after completing 3 months of service, "
            "but the full entitlement is earned after 1 completed year of service.\n"
            "Reference: Employment Act, s 43"
        )

    days = _ANNUAL_LEAVE_TABLE.get(completed, _ANNUAL_LEAVE_MAX)

    if employment_type == "part_time":
        # Pro-rated based on hours worked relative to full-time equivalent
        result = (
            f"Part-time annual leave is pro-rated based on hours worked.\n"
            f"Full-time equivalent for {completed} year(s) of service: {days} days.\n"
            f"Formula: {days} × (part-time hours per week ÷ full-time hours per week).\n"
            f"Reference: Employment Act, s 43 + Employment Act (Part-Time Employees) Regulations"
        )
    else:
        result = (
            f"Annual leave entitlement: {days} days for {completed} year(s) of service.\n"
            f"Reference: Employment Act, s 43 (Fourth Schedule)"
        )
    return result


# ── Sick Leave (EA s89) ──────────────────────────────────────────────────────

_SICK_LEAVE_OUTPATIENT = 14
_SICK_LEAVE_HOSPITALISATION = 60
_SICK_LEAVE_MIN_SERVICE_MONTHS = 6


def _calc_sick_leave(tenure_years: float, employment_type: str) -> str:
    months = tenure_years * 12
    if months < 3:
        return (
            "Paid sick leave entitlement begins after 3 months of service.\n"
            "Reference: Employment Act, s 89(2)"
        )

    if months < _SICK_LEAVE_MIN_SERVICE_MONTHS:
        # Partial entitlement: 3-6 months
        if months < 4:
            outpatient, hosp = 5, 15
        elif months < 5:
            outpatient, hosp = 8, 30
        else:
            outpatient, hosp = 11, 45

        if employment_type == "part_time":
            return (
                f"Part-time sick leave is pro-rated based on hours worked.\n"
                f"Full-time equivalent at {months:.0f} months: {outpatient} days outpatient, "
                f"{hosp} days hospitalisation.\n"
                f"Reference: Employment Act, s 89 + Part-Time Employees Regulations"
            )
        return (
            f"Sick leave entitlement at {months:.0f} months of service: "
            f"{outpatient} days outpatient, {hosp} days hospitalisation.\n"
            f"Note: Full entitlement is reached after 6 months of service.\n"
            f"Reference: Employment Act, s 89(2)"
        )

    if employment_type == "part_time":
        return (
            f"Part-time sick leave is pro-rated based on hours worked.\n"
            f"Full-time equivalent: {_SICK_LEAVE_OUTPATIENT} days outpatient + "
            f"{_SICK_LEAVE_HOSPITALISATION} days hospitalisation leave.\n"
            f"Reference: Employment Act, s 89 + Part-Time Employees Regulations"
        )
    return (
        f"Sick leave entitlement: {_SICK_LEAVE_OUTPATIENT} days outpatient + "
        f"{_SICK_LEAVE_HOSPITALISATION} days hospitalisation leave per year.\n"
        f"The {_SICK_LEAVE_HOSPITALISATION} days is inclusive of the "
        f"{_SICK_LEAVE_OUTPATIENT} outpatient days.\n"
        f"Reference: Employment Act, s 89(1)"
    )


# ── Maternity Leave (EA Part IX) ─────────────────────────────────────────────

def _calc_maternity_leave(tenure_years: float, employment_type: str) -> str:
    months = tenure_years * 12
    if months < 3:
        return (
            "Government-Paid Maternity Leave requires at least 3 months of service "
            "before the child's birth.\n"
            "Reference: Employment Act, Part IX + Child Development Co-Savings Act"
        )
    return (
        "Maternity leave entitlement: 16 weeks.\n"
        "- First 8 weeks: employer-paid.\n"
        "- Last 8 weeks: Government-paid (capped at $10,000/week for first two births; "
        "all 16 weeks Government-paid for third and subsequent births).\n"
        "Conditions: must have served employer for at least 3 months before birth, "
        "and given at least 1 week's notice.\n"
        "Reference: Employment Act, Part IX, s 76 + Child Development Co-Savings Act"
    )


# ── Paternity Leave (GPEA) ──────────────────────────────────────────────────

def _calc_paternity_leave(tenure_years: float, employment_type: str) -> str:
    return (
        "Government-Paid Paternity Leave: 2 weeks.\n"
        "Conditions: the child is a Singapore citizen, the father is lawfully married "
        "to the child's mother, and has served the employer for at least 3 continuous months "
        "before the birth.\n"
        "Reference: Child Development Co-Savings Act (Government-Paid Paternity Leave)"
    )


# ── Childcare Leave (CCDA) ──────────────────────────────────────────────────

def _calc_childcare_leave(tenure_years: float, employment_type: str) -> str:
    months = tenure_years * 12
    if months < 3:
        return (
            "Childcare leave requires at least 3 months of service.\n"
            "Reference: Child Development Co-Savings Act"
        )
    return (
        "Childcare leave entitlement:\n"
        "- Child under 7 years old: 6 days per year "
        "(first 3 days employer-paid, last 3 days Government-paid).\n"
        "- Child aged 7 to 12: 2 days per year (employer-paid).\n"
        "Conditions: employee must have served at least 3 months, "
        "child must be a Singapore citizen.\n"
        "Reference: Child Development Co-Savings Act, s 12A"
    )


# ── Dispatch ─────────────────────────────────────────────────────────────────

_LEAVE_CALCULATORS: dict[str, Any] = {
    "annual": _calc_annual_leave,
    "sick": _calc_sick_leave,
    "maternity": _calc_maternity_leave,
    "paternity": _calc_paternity_leave,
    "childcare": _calc_childcare_leave,
}


async def calculate_leave_entitlement(tool_input: dict[str, Any]) -> str:
    """Calculate statutory leave entitlement."""
    tenure_years: float = tool_input["tenure_years"]
    employment_type: str = tool_input["employment_type"]
    leave_type: str = tool_input["leave_type"]

    if tenure_years < 0:
        return "Error: tenure_years cannot be negative."

    calculator = _LEAVE_CALCULATORS.get(leave_type)
    if calculator is None:
        return f"Error: unknown leave type '{leave_type}'. Valid types: {list(_LEAVE_CALCULATORS.keys())}"

    log.info(
        "Calculating leave entitlement",
        extra={"leave_type": leave_type, "tenure_years": tenure_years, "employment_type": employment_type},
    )
    result = calculator(tenure_years, employment_type)
    return f"{result}\n\n(EA rules version: {EA_RULES_VERSION})"


# ── Notice Period (EA s10) ───────────────────────────────────────────────────

_NOTICE_BRACKETS: list[tuple[float, str]] = [
    (26 / 52, "1 day"),          # < 26 weeks
    (2.0, "1 week"),             # 26 weeks to < 2 years
    (5.0, "2 weeks"),            # 2 to < 5 years
    (float("inf"), "4 weeks"),   # 5+ years
]


async def calculate_notice_period(tool_input: dict[str, Any]) -> str:
    """Calculate the minimum statutory notice period."""
    tenure_years: float = tool_input["tenure_years"]
    contract_notice: str | None = tool_input.get("contract_notice")

    if tenure_years < 0:
        return "Error: tenure_years cannot be negative."

    statutory = "1 day"
    for threshold, period in _NOTICE_BRACKETS:
        if tenure_years < threshold:
            statutory = period
            break

    log.info(
        "Calculating notice period",
        extra={"tenure_years": tenure_years, "contract_notice": contract_notice},
    )

    result = f"Statutory minimum notice period: {statutory} (for {tenure_years} year(s) of service).\n"
    result += "Reference: Employment Act, s 10(3)\n"

    if contract_notice:
        result += (
            f"\nContractual notice period: {contract_notice}.\n"
            "Where the contract specifies a notice period, either party must give "
            "at least the contractual notice or the statutory minimum, whichever is longer.\n"
            "Reference: Employment Act, s 10(1)–(3)"
        )
    else:
        result += (
            "\nIf no notice period is specified in the contract, "
            "the statutory minimum above applies.\n"
            "Reference: Employment Act, s 10(3)"
        )

    return f"{result}\n\n(EA rules version: {EA_RULES_VERSION})"


def register_calculation_tools() -> None:
    """Register all calculation tool handlers in the tool registry."""
    from backend.chat.tools.registry import register_tool

    register_tool("calculate_leave_entitlement", calculate_leave_entitlement)
    register_tool("calculate_notice_period", calculate_notice_period)
