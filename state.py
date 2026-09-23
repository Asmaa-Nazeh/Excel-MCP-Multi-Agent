"""
state.py
--------
Shared state schema passed between LangGraph nodes:
Router -> {Create|Update|Insights} Agent -> Action Executor.
"""

from typing import TypedDict, Optional, Dict, Any


class AgentState(TypedDict, total=False):
    # Input
    user_request: str          # natural-language request from the user
    file_path: str             # active workbook path for this session

    # Router output
    route: str                 # "CREATE" | "UPDATE" | "INSIGHTS"

    # Agent output (structured action, never raw code)
    action: Dict[str, Any]

    # Action Executor output
    executor_result: Dict[str, Any]

    # Convenience field populated for the INSIGHTS route
    insights: str

    # Populated if something goes wrong anywhere in the pipeline
    error: Optional[str]
