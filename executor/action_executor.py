"""
executor/action_executor.py
-----------------------------
Action Executor. Receives a structured action ({"action_type": ..., "arguments": ...})
produced by one of the three agents and maps it onto a predefined MCP tool call.

This is the sole safety boundary between "what an LLM said it wants to do" and
"what actually happens to a real .xlsx file": the action_type MUST be one of a
fixed allow-list of MCP tool names. Anything else (including an "error" action,
or an unrecognized action_type) is rejected without touching MCP or Excel at all.
No arbitrary code from the LLM is ever executed.
"""

from typing import Any, Dict

from mcp.client import ExcelMCPClient

# The only Excel-mutating tools the executor is allowed to invoke.
MUTATING_ACTIONS = {
    "create_workbook",
    "create_sheet",
    "add_row",
    "update_cell",
    "delete_row",
    "format_sheet",
}


def execute_action(action: Dict[str, Any], file_path: str) -> Dict[str, Any]:
    if not action:
        return {"success": False, "error": "No action was produced by the agent."}

    action_type = action.get("action_type")
    arguments = dict(action.get("arguments") or {})

    # The agent itself flagged a failure (e.g. unparseable / disallowed LLM output).
    if action_type == "error":
        return {"success": False, "error": action.get("explanation", "Unknown agent error.")}

    # Read-only insights report: data was already retrieved via MCP inside the
    # Insights Agent, so the executor simply finalizes/returns the result.
    if action_type == "insights_report":
        return {
            "success": True,
            "action_type": action_type,
            "insights": arguments.get("insights", ""),
            "raw_data": arguments.get("raw_data", {}),
            "explanation": action.get("explanation", ""),
        }

    # Hard safety check: reject anything not on the predefined MCP tool allow-list.
    if action_type not in MUTATING_ACTIONS:
        return {"success": False, "error": f"Action '{action_type}' is not a permitted MCP tool. Rejected."}

    # Ensure the action targets the session's active workbook unless the agent
    # explicitly supplied a different path.
    arguments.setdefault("file_path", file_path)

    client = None
    try:
        client = ExcelMCPClient()
        result = client.call_tool(action_type, arguments)
    except Exception as e:
        return {"success": False, "error": str(e), "action_type": action_type, "arguments": arguments}
    finally:
        if client:
            client.close()

    return {
        "success": bool(result.get("success", False)),
        "action_type": action_type,
        "arguments": arguments,
        "result": result,
        "explanation": action.get("explanation", ""),
    }
