"""
mcp/server.py
-------------
Excel MCP Server.

This is a real, standalone server process. It is launched by the MCP
Client (mcp/client.py) as a subprocess and communicates over stdin/stdout
using newline-delimited JSON-RPC-style messages:

    request:  {"id": 1, "method": "call_tool", "params": {"name": "...", "arguments": {...}}}
    response: {"id": 1, "result": {...}}            (on success)
              {"id": 1, "error": "..."}              (on failure)

    request:  {"id": 2, "method": "list_tools", "params": {}}
    response: {"id": 2, "result": {"tools": [{"name": ..., "description": ...}, ...]}}

It exposes exactly these tools, each backed by excel/operations.py
(OpenPyXL + Pandas). This is the ONLY process in the system that is
allowed to touch .xlsx files:

    create_workbook, read_workbook, get_sheets, add_row, update_cell,
    delete_row, create_sheet, format_sheet, read_data, calculate_statistics

Run standalone for manual testing:
    python mcp/server.py
    (then type a JSON request line and press enter, e.g.)
    {"id": 1, "method": "list_tools", "params": {}}
"""

import sys
import os
import json
import traceback

# Make sure the project root (parent of this file's directory) is importable
# regardless of the working directory the server is launched from, so that
# `from excel import operations` resolves correctly when this script is run
# directly (python mcp/server.py) as its own subprocess.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from excel import operations as excel_ops  # noqa: E402

TOOLS = {
    "create_workbook": excel_ops.create_workbook,
    "read_workbook": excel_ops.read_workbook,
    "get_sheets": excel_ops.get_sheets,
    "add_row": excel_ops.add_row,
    "update_cell": excel_ops.update_cell,
    "delete_row": excel_ops.delete_row,
    "create_sheet": excel_ops.create_sheet,
    "format_sheet": excel_ops.format_sheet,
    "read_data": excel_ops.read_data,
    "calculate_statistics": excel_ops.calculate_statistics,
}

TOOL_DESCRIPTIONS = {
    "create_workbook": "Create a new .xlsx workbook with an initial sheet and optional headers.",
    "read_workbook": "Read basic structural info (rows/cols per sheet) of a workbook.",
    "get_sheets": "List all sheet names in a workbook.",
    "add_row": "Append a row of values to the end of a sheet.",
    "update_cell": "Update the value of a single cell (e.g. 'B3').",
    "delete_row": "Delete a row by its 1-based row number.",
    "create_sheet": "Create a new sheet in an existing (or new) workbook, with optional headers.",
    "format_sheet": "Apply basic formatting: bold headers, header fill color, autofit columns.",
    "read_data": "Read tabular data from a sheet (or all sheets) as records, via pandas.",
    "calculate_statistics": "Compute basic statistics (count, sum, mean, min, max, std) for numeric columns.",
}


def handle_request(request: dict) -> dict:
    req_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    try:
        if method == "list_tools":
            tools = [{"name": name, "description": TOOL_DESCRIPTIONS.get(name, "")} for name in TOOLS]
            return {"id": req_id, "result": {"tools": tools}}

        if method == "call_tool":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if name not in TOOLS:
                return {"id": req_id, "error": f"Unknown tool: {name}"}
            func = TOOLS[name]
            result = func(**arguments)
            return {"id": req_id, "result": result}

        return {"id": req_id, "error": f"Unknown method: {method}"}

    except TypeError as e:
        return {"id": req_id, "error": f"Invalid arguments for tool '{params.get('name')}': {e}"}
    except Exception as e:  # pragma: no cover - defensive catch-all
        return {"id": req_id, "error": f"{e}\n{traceback.format_exc()}"}


def main() -> None:
    """Blocking read loop: one JSON request per line on stdin, one JSON
    response per line on stdout. Runs until stdin is closed."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            sys.stdout.write(json.dumps({"id": None, "error": f"Invalid JSON request: {e}"}) + "\n")
            sys.stdout.flush()
            continue

        response = handle_request(request)
        try:
            payload = json.dumps(response)
        except TypeError:
            # Defense in depth: excel/operations.py already normalizes
            # pandas/numpy/date types to JSON-safe values, but if some
            # other non-serializable type ever slips through, fall back
            # to stringifying it rather than crashing the server process
            # (which would otherwise kill every pending tool call).
            payload = json.dumps(response, default=str)
        sys.stdout.write(payload + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
