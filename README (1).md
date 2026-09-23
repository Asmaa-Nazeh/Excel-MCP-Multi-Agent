# Excel MCP Multi-Agent

A multi-agent system that turns natural-language requests into safe, validated
Excel operations, orchestrated with **LangGraph** and executed through a real
**MCP (Model Context Protocol)-style client/server**, with a **Streamlit** UI.

## Architecture

```text
User
 ↓
Streamlit
 ↓
Router LLM
 ↓
 ┌──────────────┬──────────────┬──────────────┐
 ↓              ↓              ↓
CREATE         UPDATE        INSIGHTS
 ↓              ↓              ↓
Create LLM     Update LLM     Insights LLM
 └──────────────┬──────────────┘
                ↓
         Action Executor
                ↓
           MCP Client
                ↓
        Excel MCP Server
                ↓
             XLSX
```

- **Router LLM** (`agents/router.py`) — classifies every request into exactly
  `CREATE`, `UPDATE`, or `INSIGHTS`. It never touches Excel.
- **Create / Update Agents** (`agents/create_agent.py`, `agents/update_agent.py`)
  — each calls an LLM that returns a single **structured JSON action**
  (`{"action_type": ..., "arguments": {...}}`) chosen from a fixed allow-list
  of MCP tool names. The LLM never writes or executes Python/Excel code.
- **Insights Agent** (`agents/insights_agent.py`) — first retrieves real
  workbook data (`get_sheets`, `read_data`, `calculate_statistics`) through
  the **MCP Client**, then asks the LLM to generate a report grounded only in
  that retrieved data.
- **Action Executor** (`executor/action_executor.py`) — the single safety
  boundary. It re-validates the `action_type` against a predefined allow-list
  and, only if valid, forwards the call to the **MCP Client**. Anything else
  is rejected before it can touch a file.
- **MCP Client / Server** (`mcp/client.py`, `mcp/server.py`) — a real
  client/server pair. The client launches the server as a **separate
  subprocess** and talks to it over stdin/stdout using newline-delimited
  JSON-RPC-style messages (`list_tools`, `call_tool`). The server is the
  *only* process that imports `excel/operations.py`.
- **Excel operations** (`excel/operations.py`) — all actual `.xlsx` I/O,
  built with **OpenPyXL** (structure, cells, formatting) and **Pandas**
  (tabular reads, statistics).
- **LangGraph** (`graph.py`) — wires everything together:
  `START → router → (create_agent | update_agent | insights_agent) → executor → END`.

### Why this is safe

The LLM is never asked to produce, and the system never executes, arbitrary
Python. Every agent must emit one of a small number of predefined
`action_type`s (`create_workbook`, `create_sheet`, `add_row`, `update_cell`,
`delete_row`, `format_sheet`, plus the read-only `insights_report`). The
Action Executor checks this allow-list independently of the agent's own
prompt-level restrictions before calling MCP, so a misbehaving or
jailbroken LLM response simply gets rejected instead of run.

## MCP tools exposed by the Excel MCP Server

```text
create_workbook        read_workbook        get_sheets
add_row                update_cell          delete_row
create_sheet           format_sheet         read_data
calculate_statistics
```

## Project structure

```text
excel_mcp_agent/
│
├── app.py                    # Streamlit UI
├── graph.py                  # LangGraph orchestration
├── state.py                  # Shared LangGraph state schema
├── config.py                 # .env / LLM client config
├── prompts.py                # System prompts for router + 3 agents
├── utils.py                  # Shared helpers (robust JSON parsing)
│
├── agents/
│   ├── router.py              # Router LLM
│   ├── create_agent.py        # Create Agent
│   ├── update_agent.py        # Update Agent
│   └── insights_agent.py      # Insights Agent
│
├── executor/
│   └── action_executor.py     # Validates + executes structured actions via MCP
│
├── mcp/
│   ├── client.py               # MCP Client (subprocess + stdio JSON-RPC)
│   └── server.py               # MCP Server (exposes the 10 Excel tools)
│
├── excel/
│   └── operations.py           # OpenPyXL + Pandas implementations
│
├── data/
│   └── uploads/                # Uploaded / generated workbooks live here
│
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

```bash
cd excel_mcp_agent
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# then edit .env and set OPENAI_API_KEY (and optionally OPENAI_BASE_URL / OPENAI_MODEL)
```

## Run the app

```bash
streamlit run app.py
```

Then, in the browser tab that opens:
1. Upload an `.xlsx` file (or start a new workbook session in the sidebar).
2. Type a natural-language request.
3. Click **Run Workflow**.
4. See the selected route, the structured action, the executor result, and
   (for `INSIGHTS` requests) the generated report.
5. Download the resulting workbook from the sidebar or the result panel.

## Running the MCP server standalone (optional, for testing/debugging)

The Streamlit app launches the MCP server automatically as a subprocess
whenever the MCP Client is used — there is no separate process to start for
normal use. To test the server directly:

```bash
python mcp/server.py
```

It will block, waiting for newline-delimited JSON on stdin. Try:

```json
{"id": 1, "method": "list_tools", "params": {}}
```

```json
{"id": 2, "method": "call_tool", "params": {"name": "create_workbook", "arguments": {"file_path": "data/uploads/test.xlsx", "sheet_name": "Sheet1", "headers": ["Name", "Score"]}}}
```

Each line you type is one request; the server prints one JSON response line
back per request.

## Example requests to try

- `Create a new sheet called Budget with columns Category, Planned, Actual`
- `Add a row to Sheet1: Alice, 29, Engineering, 75000`
- `Update cell C2 in Sheet1 to 80000`
- `Delete row 4 from Sheet1`
- `Format the Budget sheet with a bold, light-blue header`
- `Give me insights on this workbook's data`
- `Summarize trends and any outliers in the Sales sheet`

## Data type handling (dates, categories, missing values)

Real workbooks mix numeric, text, date, and empty cells in the same sheet.
`excel/operations.py` normalizes every value that crosses the MCP boundary
via a `_json_safe()` helper so this never breaks the pipeline:

| Source value                                   | Sent over MCP as        |
|-------------------------------------------------|--------------------------|
| `datetime.date` / `datetime.datetime` / `pandas.Timestamp` | ISO-8601 string, e.g. `"2024-01-05T00:00:00"` |
| Missing cell (`NaN` / `NaT` / empty)             | `null`                   |
| `numpy.int64`, `numpy.float64`, etc.             | plain Python `int` / `float` |
| `decimal.Decimal`                                | `float`                  |
| Text / category columns                          | unchanged                |

`calculate_statistics` only aggregates numeric columns (via
`DataFrame.select_dtypes(include="number")`), so date and category columns
are automatically excluded from sums/means/etc. instead of causing an error.

`mcp/server.py` also has a `default=str` fallback around its JSON encoding,
so if any other non-serializable type ever shows up in the future, the
server degrades gracefully (stringifies it) instead of crashing and losing
the whole response.

## Troubleshooting

- **"OPENAI_API_KEY is not set"** — copy `.env.example` to `.env` and fill
  in your key; never hard-code it in source.
- **"No response from MCP server" / MCP server crashed** — check the error
  message returned; if it mentions a JSON serialization error for a type
  not listed in the table above, extend `_json_safe()` in
  `excel/operations.py` to handle it.
- **Router picks the "wrong" category** — the Router LLM uses `temperature=0`
  for consistency; if a request is genuinely ambiguous, rephrase it to be
  more explicit (e.g. start with "Create...", "Update...", or "Summarize...").
- **Agent proposes a disallowed action** — this is expected and safe: the
  Action Executor rejects any `action_type` outside its predefined MCP tool
  allow-list before touching a file. Rephrase the request so it maps
  cleanly onto one of the tools listed above.
