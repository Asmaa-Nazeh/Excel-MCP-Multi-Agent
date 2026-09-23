"""
excel/operations.py
--------------------
The ONLY module that actually touches .xlsx files, using OpenPyXL for
structural/cell operations and Pandas for tabular reads/statistics.

Every function is pure, synchronous, JSON-serializable-in/out, and
defensive (returns {"success": False, "error": ...} instead of raising,
so the MCP server can safely forward results to the client).

These functions are wrapped as MCP tools in mcp/server.py -- nothing
outside this file (and the server that exposes it) should import
openpyxl/pandas directly.
"""

import os
import math
import datetime
import decimal
from typing import Optional, List, Dict, Any

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
import pandas as pd


def _ensure_parent_dir(file_path: str) -> None:
    parent = os.path.dirname(file_path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _json_safe(value: Any) -> Any:
    """Recursively convert a value into something json.dumps can handle.

    Excel cells commonly come back from pandas/openpyxl as types that are
    NOT natively JSON-serializable: pandas.Timestamp / datetime.date /
    datetime.time (date columns), decimal.Decimal, numpy scalar types
    (int64, float64, bool_ -- anything with a .item() method), and NaN/NaT
    for missing values. This normalizes all of those into plain
    str / int / float / bool / None so results can always cross the MCP
    JSON-RPC boundary safely.
    """
    if value is None:
        return None

    # Missing values: NaN (float) or NaT (pandas) all report True for pd.isna
    # on scalars; guard with a try since pd.isna on some objects can raise.
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, (pd.Timestamp, datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, pd.Timedelta):
        return str(value)
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, float) and math.isnan(value):
        return None

    # numpy scalar types (int64, float64, bool_, etc.) all expose .item()
    if hasattr(value, "item") and not isinstance(value, (list, dict, str, bytes)):
        try:
            return _json_safe(value.item())
        except Exception:
            pass

    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]

    return value


def _df_to_records(df: pd.DataFrame, max_rows: int) -> List[Dict[str, Any]]:
    """Convert a DataFrame to a list of JSON-safe {column: value} dicts."""
    df = df.head(max_rows)
    records = []
    for row in df.to_dict(orient="records"):
        records.append({str(k): _json_safe(v) for k, v in row.items()})
    return records


# ---------------------------------------------------------------------------
# Tool: create_workbook
# ---------------------------------------------------------------------------
def create_workbook(file_path: str, sheet_name: str = "Sheet1",
                     headers: Optional[List[str]] = None) -> Dict[str, Any]:
    try:
        _ensure_parent_dir(file_path)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = sheet_name or "Sheet1"
        if headers:
            ws.append(headers)
            for cell in ws[1]:
                cell.font = Font(bold=True)
        wb.save(file_path)
        return {"success": True, "file_path": file_path, "sheet_name": ws.title, "headers": headers or []}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Tool: read_workbook
# ---------------------------------------------------------------------------
def read_workbook(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        summary = {}
        for name in wb.sheetnames:
            ws = wb[name]
            summary[name] = {"max_row": ws.max_row, "max_col": ws.max_column}
        wb.close()
        return {"success": True, "file_path": file_path, "sheets": summary}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Tool: get_sheets
# ---------------------------------------------------------------------------
def get_sheets(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True)
        sheets = wb.sheetnames
        wb.close()
        return {"success": True, "sheets": sheets}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Tool: create_sheet
# ---------------------------------------------------------------------------
def create_sheet(file_path: str, sheet_name: str,
                  headers: Optional[List[str]] = None) -> Dict[str, Any]:
    try:
        if not os.path.exists(file_path):
            # No workbook yet -> create one with this as the first sheet.
            return create_workbook(file_path, sheet_name, headers)

        wb = openpyxl.load_workbook(file_path)
        if sheet_name in wb.sheetnames:
            wb.close()
            return {"success": False, "error": f"Sheet '{sheet_name}' already exists."}
        ws = wb.create_sheet(sheet_name)
        if headers:
            ws.append(headers)
            for cell in ws[1]:
                cell.font = Font(bold=True)
        wb.save(file_path)
        wb.close()
        return {"success": True, "sheet_name": sheet_name, "headers": headers or []}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Tool: add_row
# ---------------------------------------------------------------------------
def add_row(file_path: str, sheet_name: str, row_values: List[Any]) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}
    try:
        wb = openpyxl.load_workbook(file_path)
        if sheet_name not in wb.sheetnames:
            wb.close()
            return {"success": False, "error": f"Sheet '{sheet_name}' not found."}
        ws = wb[sheet_name]
        ws.append(row_values)
        new_row_number = ws.max_row
        wb.save(file_path)
        wb.close()
        return {"success": True, "sheet_name": sheet_name, "row_number": new_row_number, "row_values": row_values}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Tool: update_cell
# ---------------------------------------------------------------------------
def update_cell(file_path: str, sheet_name: str, cell: str, value: Any) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}
    try:
        wb = openpyxl.load_workbook(file_path)
        if sheet_name not in wb.sheetnames:
            wb.close()
            return {"success": False, "error": f"Sheet '{sheet_name}' not found."}
        ws = wb[sheet_name]
        ws[cell] = value
        wb.save(file_path)
        wb.close()
        return {"success": True, "sheet_name": sheet_name, "cell": cell, "value": value}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Tool: delete_row
# ---------------------------------------------------------------------------
def delete_row(file_path: str, sheet_name: str, row_number: int) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}
    try:
        wb = openpyxl.load_workbook(file_path)
        if sheet_name not in wb.sheetnames:
            wb.close()
            return {"success": False, "error": f"Sheet '{sheet_name}' not found."}
        ws = wb[sheet_name]
        row_number = int(row_number)
        if row_number < 1 or row_number > ws.max_row:
            wb.close()
            return {"success": False, "error": f"Row {row_number} out of range (1-{ws.max_row})."}
        ws.delete_rows(row_number, 1)
        wb.save(file_path)
        wb.close()
        return {"success": True, "sheet_name": sheet_name, "deleted_row": row_number}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Tool: format_sheet
# ---------------------------------------------------------------------------
def format_sheet(file_path: str, sheet_name: str, header_bold: bool = True,
                  header_fill_color: Optional[str] = None,
                  autofit_columns: bool = True) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}
    try:
        wb = openpyxl.load_workbook(file_path)
        if sheet_name not in wb.sheetnames:
            wb.close()
            return {"success": False, "error": f"Sheet '{sheet_name}' not found."}
        ws = wb[sheet_name]

        if header_bold and ws.max_row >= 1:
            for cell in ws[1]:
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal="center")
                if header_fill_color:
                    cell.fill = PatternFill(start_color=header_fill_color,
                                             end_color=header_fill_color,
                                             fill_type="solid")

        if autofit_columns:
            for col_cells in ws.columns:
                length = max((len(str(c.value)) if c.value is not None else 0 for c in col_cells), default=0)
                col_letter = get_column_letter(col_cells[0].column)
                ws.column_dimensions[col_letter].width = max(10, length + 2)

        wb.save(file_path)
        wb.close()
        return {"success": True, "sheet_name": sheet_name, "header_bold": header_bold,
                "header_fill_color": header_fill_color, "autofit_columns": autofit_columns}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Tool: read_data
# ---------------------------------------------------------------------------
def read_data(file_path: str, sheet_name: Optional[str] = None, max_rows: int = 200) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}
    try:
        if sheet_name:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            return {
                "success": True,
                "sheet_name": sheet_name,
                "columns": [str(c) for c in df.columns],
                "row_count": int(min(df.shape[0], max_rows)),
                "records": _df_to_records(df, max_rows),
            }
        all_sheets = pd.read_excel(file_path, sheet_name=None)
        out = {}
        for name, df in all_sheets.items():
            out[name] = {
                "columns": [str(c) for c in df.columns],
                "row_count": int(min(df.shape[0], max_rows)),
                "records": _df_to_records(df, max_rows),
            }
        return {"success": True, "sheets": out}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Tool: calculate_statistics
# ---------------------------------------------------------------------------
def calculate_statistics(file_path: str, sheet_name: Optional[str] = None,
                          columns: Optional[List[str]] = None) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}
    try:
        if sheet_name:
            sheets = {sheet_name: pd.read_excel(file_path, sheet_name=sheet_name)}
        else:
            sheets = pd.read_excel(file_path, sheet_name=None)

        stats_out: Dict[str, Any] = {}
        for name, df in sheets.items():
            numeric_df = df.select_dtypes(include="number")
            if columns:
                numeric_df = numeric_df[[c for c in columns if c in numeric_df.columns]]
            sheet_stats = {}
            for col in numeric_df.columns:
                series = numeric_df[col].dropna()
                if series.empty:
                    continue
                sheet_stats[str(col)] = {
                    "count": int(series.count()),
                    "sum": float(series.sum()),
                    "mean": float(series.mean()),
                    "min": float(series.min()),
                    "max": float(series.max()),
                    "std": float(series.std()) if series.count() > 1 else 0.0,
                }
            stats_out[name] = sheet_stats
        return {"success": True, "statistics": stats_out}
    except Exception as e:
        return {"success": False, "error": str(e)}
