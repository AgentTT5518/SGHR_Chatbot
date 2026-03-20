"""
Tool registry: schema definitions and dispatch for all Claude tool-use tools.
Each tool has an Anthropic-format schema and an async handler function.
"""
from __future__ import annotations

from typing import Any, Callable, Coroutine

from backend.lib.logger import get_logger

log = get_logger("chat.tools.registry")

# Type alias for tool handlers: async (dict) -> str
ToolHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, str]]

# ── Tool Schemas (Anthropic format) ──────────────────────────────────────────

TOOL_SCHEMAS: list[dict[str, Any]] = [
    # ── Retrieval Tools ──
    {
        "name": "search_employment_act",
        "description": (
            "Search the Singapore Employment Act for legal provisions, statutory rights, "
            "penalties, and obligations. Use this when the user asks about legal entitlements, "
            "specific Act sections, or employer obligations under the law. "
            "Do NOT use this for practical how-to procedures — use search_mom_guidelines instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query describing what to find in the Employment Act.",
                },
                "section_filter": {
                    "type": "string",
                    "description": (
                        "Optional: filter to a specific Part (e.g. 'Part IV', 'Part X') "
                        "to narrow results."
                    ),
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_mom_guidelines",
        "description": (
            "Search the Ministry of Manpower (MOM) guidelines for practical procedures, "
            "administrative processes, and how-to guidance. Use this when the user asks about "
            "filing claims, applying for passes, or following MOM processes. "
            "Do NOT use this for legal provisions — use search_employment_act instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query describing what MOM guidance to find.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_all_policies",
        "description": (
            "Search across both the Employment Act and MOM guidelines simultaneously. "
            "Use this when the query spans both legal provisions and practical guidance, "
            "or when you are unsure which source is most relevant. "
            "Prefer the specific search tools when the source is clear."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to run across all policy sources.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_legal_definitions",
        "description": (
            "Retrieve the legal definitions from Section 2 of the Singapore Employment Act. "
            "Use this when the user asks what a legal term means (e.g. 'workman', 'employee', "
            "'basic rate of pay') or when you need to clarify a defined term in your answer. "
            "Do NOT use this for general search — use search_employment_act instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "term": {
                    "type": "string",
                    "description": "The legal term to look up (e.g. 'workman', 'employee').",
                },
            },
            "required": ["term"],
        },
    },
    # ── Calculation Tools ──
    {
        "name": "calculate_leave_entitlement",
        "description": (
            "Calculate statutory leave entitlement under the Singapore Employment Act. "
            "Supports annual leave, sick leave, maternity, paternity, and childcare leave. "
            "Use this when the user asks how many days of leave they are entitled to. "
            "Do NOT use this for contractual leave that exceeds statutory minimums."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tenure_years": {
                    "type": "number",
                    "description": "Number of years of service with the current employer.",
                },
                "employment_type": {
                    "type": "string",
                    "enum": ["full_time", "part_time"],
                    "description": "Whether the employee is full-time or part-time.",
                },
                "leave_type": {
                    "type": "string",
                    "enum": ["annual", "sick", "maternity", "paternity", "childcare"],
                    "description": "The type of leave to calculate.",
                },
            },
            "required": ["tenure_years", "employment_type", "leave_type"],
        },
    },
    {
        "name": "calculate_notice_period",
        "description": (
            "Calculate the minimum notice period required to terminate employment "
            "under the Singapore Employment Act (Section 10). The result depends on "
            "the length of service and any contractual notice terms. "
            "Use this when the user asks about resignation or termination notice requirements."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tenure_years": {
                    "type": "number",
                    "description": "Number of years of service with the current employer.",
                },
                "contract_notice": {
                    "type": "string",
                    "description": (
                        "Optional: notice period specified in the employment contract "
                        "(e.g. '1 month', '2 weeks'). If provided and more favourable, "
                        "this overrides the statutory minimum."
                    ),
                },
            },
            "required": ["tenure_years"],
        },
    },
    # ── Routing Tools ──
    {
        "name": "check_eligibility",
        "description": (
            "Check whether an employee is covered by specific parts of the Singapore "
            "Employment Act based on their salary, role, and employment type. "
            "Use this when you need to determine if Part IV (rest days, hours, overtime) "
            "or other provisions apply to the user. "
            "Do NOT guess eligibility — always use this tool for salary threshold checks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "salary_monthly": {
                    "type": "number",
                    "description": "Employee's monthly basic salary in SGD.",
                },
                "role": {
                    "type": "string",
                    "enum": ["workman", "non_workman", "manager_executive", "pmet"],
                    "description": (
                        "The employee's role category. 'workman' = manual labour; "
                        "'non_workman' = clerical/non-manual; 'manager_executive' or 'pmet' "
                        "= managerial/executive/professional."
                    ),
                },
                "employment_type": {
                    "type": "string",
                    "enum": ["full_time", "part_time", "contract", "temporary"],
                    "description": "The type of employment arrangement.",
                },
            },
            "required": ["salary_monthly", "role", "employment_type"],
        },
    },
    {
        "name": "escalate_to_hr",
        "description": (
            "Escalate the current conversation to a human HR professional for review. "
            "Use this when the user's question involves a complex dispute, potential legal "
            "action, or a situation that requires professional HR judgement beyond what the "
            "chatbot can provide. Always explain to the user why you are escalating."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "A clear description of why this conversation needs HR review.",
                },
                "session_id": {
                    "type": "string",
                    "description": "The current session ID for tracking the escalation.",
                },
            },
            "required": ["reason", "session_id"],
        },
    },
]

# ── Dispatch Map ─────────────────────────────────────────────────────────────
# Populated by register_tool() calls from each tool module.

TOOL_DISPATCH: dict[str, ToolHandler] = {}


def register_tool(name: str, handler: ToolHandler) -> None:
    """Register an async handler for a tool name."""
    TOOL_DISPATCH[name] = handler
    log.info("Tool registered", extra={"tool": name})


def get_all_schemas() -> list[dict[str, Any]]:
    """Return all tool schemas for passing to the Anthropic API."""
    return TOOL_SCHEMAS


def register_all_tools() -> None:
    """Register handlers from all tool modules. Call once at startup."""
    from backend.chat.tools.retrieval_tools import register_retrieval_tools
    from backend.chat.tools.calculation_tools import register_calculation_tools
    from backend.chat.tools.routing_tools import register_routing_tools

    register_retrieval_tools()
    register_calculation_tools()
    register_routing_tools()
    log.info("All tools registered", extra={"count": len(TOOL_DISPATCH)})


async def dispatch_tool(name: str, tool_input: dict[str, Any]) -> str:
    """
    Look up and execute a tool handler by name.
    Returns the tool result as a string.
    Raises KeyError if the tool name is not registered.
    """
    handler = TOOL_DISPATCH.get(name)
    if handler is None:
        msg = f"Unknown tool: {name!r}. Registered tools: {list(TOOL_DISPATCH.keys())}"
        log.error(msg)
        raise KeyError(msg)

    log.info("Dispatching tool", extra={"tool": name, "input_keys": list(tool_input.keys())})
    result = await handler(tool_input)
    log.info("Tool completed", extra={"tool": name, "result_length": len(result)})
    return result
