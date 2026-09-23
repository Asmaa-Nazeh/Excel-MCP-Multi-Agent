"""
agents/update_agent.py
------------------------
Update Agent. Uses an LLM to translate the user's request into ONE
structured action (never raw code). Validated against a predefined
allow-list here, and again independently by the Action Executor.
"""

import json

from config import get_llm_client, get_model_name
from prompts import UPDATE_SYSTEM_PROMPT
from utils import safe_json_loads
from mcp.client import ExcelMCPClient

ALLOWED_ACTIONS = {"update_cell", "add_row", "delete_row", "format_sheet"}


def run_update_agent(user_request: str, file_path: str) -> dict:
    context = _get_context(file_path)

    client = get_llm_client()
    model = get_model_name()

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": UPDATE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({
                "user_request": user_request,
                "file_path": file_path,
                "context": context,
            }, default=str)},
        ],
    )
    raw = response.choices[0].message.content or ""
    return _parse_action(raw)


def _get_context(file_path: str) -> dict:
    """Fetch sheet names + a small data preview (via MCP) so the LLM can
    resolve which sheet/cell/row the user means, and the right column
    order for new rows."""
    client = None
    try:
        client = ExcelMCPClient()
        sheets = client.call_tool("get_sheets", {"file_path": file_path})
        preview = client.call_tool("read_data", {"file_path": file_path, "max_rows": 5})
        return {"sheets": sheets, "preview": preview}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if client:
            client.close()


def _parse_action(raw: str) -> dict:
    try:
        data = safe_json_loads(raw)
    except Exception:
        return {
            "action_type": "error",
            "arguments": {},
            "explanation": f"Update Agent produced unparseable output: {raw[:300]}",
        }

    action_type = data.get("action_type")
    if action_type not in ALLOWED_ACTIONS:
        return {
            "action_type": "error",
            "arguments": {},
            "explanation": f"Update Agent proposed a disallowed action_type: {action_type!r}",
        }

    return {
        "action_type": action_type,
        "arguments": data.get("arguments", {}) or {},
        "explanation": data.get("explanation", ""),
    }
