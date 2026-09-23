"""
agents/create_agent.py
-----------------------
Create Agent. Uses an LLM to translate the user's request into ONE
structured action (never raw code). The action is validated against a
predefined allow-list here, and again independently by the Action
Executor before anything runs through MCP.
"""

import json

from config import get_llm_client, get_model_name
from prompts import CREATE_SYSTEM_PROMPT
from utils import safe_json_loads
from mcp.client import ExcelMCPClient

ALLOWED_ACTIONS = {"create_workbook", "create_sheet", "add_row", "format_sheet"}


def run_create_agent(user_request: str, file_path: str) -> dict:
    context = _get_context(file_path)

    client = get_llm_client()
    model = get_model_name()

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": CREATE_SYSTEM_PROMPT},
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
    """Fetch just enough real workbook context (via MCP) to help the LLM
    pick sensible sheet names / avoid collisions -- no direct file access."""
    client = None
    try:
        client = ExcelMCPClient()
        return client.call_tool("get_sheets", {"file_path": file_path})
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
            "explanation": f"Create Agent produced unparseable output: {raw[:300]}",
        }

    action_type = data.get("action_type")
    if action_type not in ALLOWED_ACTIONS:
        return {
            "action_type": "error",
            "arguments": {},
            "explanation": f"Create Agent proposed a disallowed action_type: {action_type!r}",
        }

    return {
        "action_type": action_type,
        "arguments": data.get("arguments", {}) or {},
        "explanation": data.get("explanation", ""),
    }
