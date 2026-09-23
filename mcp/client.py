"""
mcp/client.py
-------------
Excel MCP Client.

Launches mcp/server.py as a real, separate subprocess and communicates
with it over stdin/stdout using the same newline-delimited JSON-RPC-style
protocol described in mcp/server.py. This is the ONLY object in the
codebase that agents / the Action Executor are allowed to use to reach
Excel data -- nobody imports excel/operations.py directly except the
server itself.

Usage:
    client = ExcelMCPClient()
    tools = client.list_tools()
    result = client.call_tool("get_sheets", {"file_path": "book.xlsx"})
    client.close()

    # or as a context manager
    with ExcelMCPClient() as client:
        client.call_tool(...)
"""

import sys
import os
import json
import subprocess
import threading
import itertools
from typing import Any, Dict, Optional

SERVER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")


class MCPError(Exception):
    """Raised when the MCP server returns an error or is unreachable."""


class ExcelMCPClient:
    _id_counter = itertools.count(1)

    def __init__(self, server_script: str = SERVER_SCRIPT, python_executable: Optional[str] = None):
        self.server_script = server_script
        self.python_executable = python_executable or sys.executable
        self._lock = threading.Lock()
        self._proc = subprocess.Popen(
            [self.python_executable, self.server_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def _send(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if self._proc.poll() is not None:
            stderr = self._proc.stderr.read() if self._proc.stderr else ""
            raise MCPError(f"MCP server process is not running. Stderr: {stderr}")

        req_id = next(self._id_counter)
        request = {"id": req_id, "method": method, "params": params}

        with self._lock:
            assert self._proc.stdin is not None
            self._proc.stdin.write(json.dumps(request) + "\n")
            self._proc.stdin.flush()
            assert self._proc.stdout is not None
            line = self._proc.stdout.readline()

        if not line:
            stderr = self._proc.stderr.read() if self._proc.stderr else ""
            raise MCPError(f"No response from MCP server (process may have crashed). Stderr: {stderr}")

        try:
            response = json.loads(line)
        except json.JSONDecodeError as e:
            raise MCPError(f"Malformed response from MCP server: {line!r} ({e})")

        if response.get("error"):
            raise MCPError(str(response["error"]))

        return response.get("result", {})

    def list_tools(self) -> Dict[str, Any]:
        """Return the list of tools the Excel MCP Server exposes."""
        return self._send("list_tools", {})

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Invoke one of the server's predefined Excel tools by name."""
        return self._send("call_tool", {"name": name, "arguments": arguments or {}})

    def close(self) -> None:
        try:
            if self._proc.poll() is None:
                if self._proc.stdin:
                    self._proc.stdin.close()
                self._proc.terminate()
                self._proc.wait(timeout=5)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass

    def __enter__(self) -> "ExcelMCPClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
