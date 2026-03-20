"""
Routing tools: eligibility checks and escalation to human HR.
"""
from __future__ import annotations

from typing import Any

from backend.lib.logger import get_logger

log = get_logger("chat.tools.routing_tools")

# ── EA Coverage Thresholds ───────────────────────────────────────────────────

_WORKMAN_SALARY_CAP = 4500       # Part IV applies to workmen earning ≤ $4,500/month
_NON_WORKMAN_SALARY_CAP = 2600   # Part IV applies to non-workmen earning ≤ $2,600/month

# Roles excluded from EA entirely
_EXCLUDED_ROLES = {"seafarer", "domestic_worker", "statutory_board_employee"}


async def check_eligibility(tool_input: dict[str, Any]) -> str:
    """Check Employment Act eligibility based on salary, role, and employment type."""
    salary: float = tool_input["salary_monthly"]
    role: str = tool_input["role"]
    employment_type: str = tool_input["employment_type"]

    log.info(
        "Checking EA eligibility",
        extra={"salary": salary, "role": role, "employment_type": employment_type},
    )

    if role in _EXCLUDED_ROLES:
        return (
            f"Employees in the '{role}' category are generally excluded from "
            "the Employment Act.\n"
            "Reference: Employment Act, s 2 (definition of 'employee') and First Schedule"
        )

    lines: list[str] = []

    # General EA coverage
    lines.append("**Employment Act General Coverage:**")
    if role in ("manager_executive", "pmet"):
        if salary > _WORKMAN_SALARY_CAP:
            lines.append(
                f"At ${salary:,.0f}/month as a {role.replace('_', ' ')}, "
                "you ARE covered by the Employment Act for core provisions "
                "(salary payment, termination, public holidays, sick leave, maternity/paternity leave). "
                "Note: managers and executives above $4,500/month were brought under the EA from 1 April 2019."
            )
        else:
            lines.append(
                f"At ${salary:,.0f}/month as a {role.replace('_', ' ')}, "
                "you ARE covered by the Employment Act."
            )
    else:
        lines.append(
            f"At ${salary:,.0f}/month as a {role.replace('_', ' ')}, "
            "you ARE covered by the Employment Act."
        )

    # Part IV eligibility (rest days, hours of work, overtime)
    lines.append("\n**Part IV Coverage (Rest Days, Hours of Work, Overtime):**")

    if role == "workman":
        if salary <= _WORKMAN_SALARY_CAP:
            lines.append(
                f"YES — As a workman earning ${salary:,.0f}/month (≤ ${_WORKMAN_SALARY_CAP:,}), "
                "Part IV applies. You are entitled to rest day provisions, "
                "regulated working hours, and overtime pay."
            )
        else:
            lines.append(
                f"NO — As a workman earning ${salary:,.0f}/month (> ${_WORKMAN_SALARY_CAP:,}), "
                "Part IV does NOT apply."
            )
    elif role == "non_workman":
        if salary <= _NON_WORKMAN_SALARY_CAP:
            lines.append(
                f"YES — As a non-workman earning ${salary:,.0f}/month (≤ ${_NON_WORKMAN_SALARY_CAP:,}), "
                "Part IV applies."
            )
        else:
            lines.append(
                f"NO — As a non-workman earning ${salary:,.0f}/month (> ${_NON_WORKMAN_SALARY_CAP:,}), "
                "Part IV does NOT apply."
            )
    else:
        # manager_executive / pmet
        lines.append(
            "NO — Managers and executives are NOT covered by Part IV "
            "regardless of salary."
        )

    lines.append(
        "\nReference: Employment Act, s 2 (definitions) + Part IV (s 36–65) + "
        "Fourth Schedule"
    )

    return "\n".join(lines)


# ── Escalation ───────────────────────────────────────────────────────────────

async def escalate_to_hr(tool_input: dict[str, Any]) -> str:
    """
    Log an escalation request and return a reference ID.
    MVP: writes to SQLite. Future: trigger email/Slack notification.
    """
    reason: str = tool_input["reason"]
    session_id: str = tool_input["session_id"]

    log.info("Escalating to HR", extra={"session_id": session_id, "reason": reason})

    from backend.chat.session_manager import create_escalation

    escalation_id = await create_escalation(session_id=session_id, reason=reason)

    # Notification hook stub — replace with email/Slack integration later
    _notify_hr(escalation_id, reason)

    return (
        f"Your question has been flagged for HR review.\n"
        f"Reference ID: ESC-{escalation_id}\n"
        f"An HR professional will review this conversation and follow up."
    )


def _notify_hr(escalation_id: int, reason: str) -> None:
    """Stub notification hook. Replace with email/Slack in production."""
    log.info(
        "HR notification stub — would send alert",
        extra={"escalation_id": escalation_id, "reason": reason},
    )


def register_routing_tools() -> None:
    """Register all routing tool handlers in the tool registry."""
    from backend.chat.tools.registry import register_tool

    register_tool("check_eligibility", check_eligibility)
    register_tool("escalate_to_hr", escalate_to_hr)
