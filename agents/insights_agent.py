"""
agents/insights_agent.py
--------------------------
Insights Agent. Retrieves REAL workbook data through the MCP Client
(get_sheets, read_data, calculate_statistics), then asks the LLM to
generate a natural-language report grounded in that data. This agent is
strictly read-only: it never proposes a mutating Excel action.

For architectural symmetry with the Create/Update agents (both of which
hand a structured action to the Action Executor), this agent packages
its finished report as a structured "insights_report" action. The
Action Executor recognizes this action type as a read-only pass-through
(no further MCP calls needed, since the data was already retrieved here).
"""

import json

from config import get_llm_client, get_model_name
from prompts import INSIGHTS_SYSTEM_PROMPT
from mcp.client import ExcelMCPClient


def run_insights_agent(user_request: str, file_path: str) -> dict:
    raw_data = _gather_data(file_path)

    client = get_llm_client()
    model = get_model_name()

    response = client.chat.completions.create(
        model=model,
        temperature=0.3,
        messages=[
            {"role": "system", "content": INSIGHTS_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({
                "user_request": user_request,
                "workbook_data": raw_data,
            }, default=str)},
        ],
    )
    insights_text = (response.choices[0].message.content or "").strip()

    return {
        "action_type": "insights_report",
        "arguments": {"insights": insights_text, "raw_data": raw_data},
        "explanation": "Generated insights from workbook data retrieved live via MCP.",
    }


def _gather_data(file_path: str) -> dict:
    """Pull sheets, row-level data, and statistics through the MCP Client
    -- this is the 'retrieve workbook data through MCP' requirement."""
    client = None
    try:
        client = ExcelMCPClient()
        sheets_result = client.call_tool("get_sheets", {"file_path": file_path})
        data_result = client.call_tool("read_data", {"file_path": file_path, "max_rows": 100})
        stats_result = client.call_tool("calculate_statistics", {"file_path": file_path})
        return {
            "sheets": sheets_result,
            "data": data_result,
            "statistics": stats_result,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if client:
            client.close()
