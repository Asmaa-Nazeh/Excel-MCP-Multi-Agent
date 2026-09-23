"""
app.py
------
Streamlit UI for the Excel MCP Multi-Agent system.

Flow implemented on screen:
    Upload / start a workbook -> type a natural-language request -> Run
    -> see which route the Router LLM chose -> see the structured action
    and executor result -> see insights (if INSIGHTS route) -> download
    the resulting .xlsx file.

The active workbook path is kept in st.session_state so it persists as
the "active workbook" for the whole browser session.
"""

import os
import io
import json
from datetime import datetime

import streamlit as st
import pandas as pd

from config import UPLOAD_DIR, OPENROUTER_MODEL
from graph import build_graph

st.set_page_config(page_title="Excel MCP Multi-Agent", page_icon="📊", layout="wide")


# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------
if "active_file" not in st.session_state:
    st.session_state.active_file = None
if "history" not in st.session_state:
    st.session_state.history = []


@st.cache_resource(show_spinner=False)
def get_graph():
    return build_graph()


def _save_uploaded_file(uploaded_file) -> str:
    dest_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
    with open(dest_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return dest_path


def _preview_workbook(file_path: str):
    if not file_path or not os.path.exists(file_path):
        st.info("No active workbook yet. Upload a file or run a CREATE request to generate one.")
        return
    try:
        sheets = pd.read_excel(file_path, sheet_name=None)
        tabs = st.tabs(list(sheets.keys()))
        for tab, (name, df) in zip(tabs, sheets.items()):
            with tab:
                st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not preview workbook yet ({e}).")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("📊 Excel MCP Multi-Agent")
    st.caption("Router LLM → Create/Update/Insights Agent → Action Executor → MCP → Excel")

    st.markdown("**LLM model:** `%s`" % OPENROUTER_MODEL)
    st.markdown("---")

    st.subheader("1. Workbook")
    uploaded = st.file_uploader("Upload an Excel file (.xlsx)", type=["xlsx"])
    if uploaded is not None:
        path = _save_uploaded_file(uploaded)
        st.session_state.active_file = path
        st.success(f"Active workbook set: {os.path.basename(path)}")

    st.caption("...or start fresh and let a CREATE request generate one:")
    new_name = st.text_input("New workbook file name", value="new_workbook.xlsx")
    if st.button("Start new workbook session"):
        st.session_state.active_file = os.path.join(UPLOAD_DIR, new_name)
        st.info(
            f"Active workbook path set to '{new_name}' (not yet created on disk — "
            "ask the CREATE agent to create it)."
        )

    if st.session_state.active_file:
        st.markdown("---")
        st.markdown("**Active workbook:**")
        st.code(st.session_state.active_file)
        if os.path.exists(st.session_state.active_file):
            with open(st.session_state.active_file, "rb") as f:
                st.download_button(
                    "⬇️ Download current workbook",
                    data=f.read(),
                    file_name=os.path.basename(st.session_state.active_file),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )


# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------
st.header("Natural-language Excel request")

if not st.session_state.active_file:
    st.warning("Upload a workbook or start a new workbook session in the sidebar first.")

user_request = st.text_area(
    "What do you want to do?",
    placeholder=(
        "Examples:\n"
        "- Create a new sheet called 'Budget' with columns Category, Planned, Actual\n"
        "- Add a row to Sheet1: Alice, 29, Engineering\n"
        "- Update cell B2 in Sheet1 to 500\n"
        "- Give me insights on the sales data"
    ),
    height=120,
)

run_clicked = st.button("🚀 Run Workflow", type="primary", disabled=not st.session_state.active_file)

st.markdown("### Workbook preview")
_preview_workbook(st.session_state.active_file)

if run_clicked:
    if not user_request.strip():
        st.error("Please enter a request.")
    else:
        graph = get_graph()
        initial_state = {
            "user_request": user_request,
            "file_path": st.session_state.active_file,
        }
        with st.spinner("Running Router → Agent → Action Executor..."):
            try:
                result_state = graph.invoke(initial_state)
            except Exception as e:
                st.error(f"Workflow failed: {e}")
                result_state = None

        if result_state:
            route = result_state.get("route", "UNKNOWN")
            executor_result = result_state.get("executor_result", {})
            insights_text = result_state.get("insights", "")

            st.markdown("### Result")
            route_color = {"CREATE": "🟢", "UPDATE": "🟡", "INSIGHTS": "🔵"}.get(route, "⚪")
            st.info(f"{route_color} **Selected route:** `{route}`")

            if result_state.get("action"):
                with st.expander("Structured action produced by the agent"):
                    st.json(result_state["action"])

            if executor_result.get("success"):
                st.success("Action Executor completed the operation successfully via MCP.")
            else:
                st.error(f"Execution failed: {executor_result.get('error', 'Unknown error')}")

            with st.expander("Action Executor result (raw)"):
                st.json(executor_result)

            if route == "INSIGHTS" and insights_text:
                st.markdown("### 📈 Generated Insights")
                st.markdown(insights_text)

            st.session_state.history.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "request": user_request,
                "route": route,
                "success": executor_result.get("success", False),
            })

            # Refresh preview + offer download again now that the file may have changed.
            st.markdown("### Updated workbook preview")
            _preview_workbook(st.session_state.active_file)

            if os.path.exists(st.session_state.active_file):
                with open(st.session_state.active_file, "rb") as f:
                    st.download_button(
                        "⬇️ Download updated workbook",
                        data=f.read(),
                        file_name=os.path.basename(st.session_state.active_file),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="download_after_run",
                        use_container_width=True,
                    )

# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------
if st.session_state.history:
    st.markdown("---")
    st.subheader("Session history")
    hist_df = pd.DataFrame(st.session_state.history)
    st.dataframe(hist_df, use_container_width=True)
