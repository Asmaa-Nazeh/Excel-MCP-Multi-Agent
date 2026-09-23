"""
graph.py
--------
LangGraph orchestration wiring the whole pipeline together exactly as:

    START -> router -> (CREATE | UPDATE | INSIGHTS) -> specialized agent -> executor -> END
"""

from langgraph.graph import StateGraph, START, END

from state import AgentState
from agents.router import route_request
from agents.create_agent import run_create_agent
from agents.update_agent import run_update_agent
from agents.insights_agent import run_insights_agent
from executor.action_executor import execute_action


def router_node(state: AgentState) -> AgentState:
    try:
        route = route_request(state["user_request"])
    except Exception as e:
        return {**state, "route": "INSIGHTS", "error": f"Router failed: {e}"}
    return {**state, "route": route}


def create_node(state: AgentState) -> AgentState:
    try:
        action = run_create_agent(state["user_request"], state["file_path"])
    except Exception as e:
        action = {"action_type": "error", "arguments": {}, "explanation": f"Create Agent failed: {e}"}
    return {**state, "action": action}


def update_node(state: AgentState) -> AgentState:
    try:
        action = run_update_agent(state["user_request"], state["file_path"])
    except Exception as e:
        action = {"action_type": "error", "arguments": {}, "explanation": f"Update Agent failed: {e}"}
    return {**state, "action": action}


def insights_node(state: AgentState) -> AgentState:
    try:
        action = run_insights_agent(state["user_request"], state["file_path"])
    except Exception as e:
        action = {"action_type": "error", "arguments": {}, "explanation": f"Insights Agent failed: {e}"}
    return {**state, "action": action}


def executor_node(state: AgentState) -> AgentState:
    result = execute_action(state.get("action", {}), state["file_path"])
    updates: dict = {"executor_result": result}
    if state.get("route") == "INSIGHTS":
        updates["insights"] = result.get("insights", "")
    if not result.get("success", False) and result.get("error"):
        updates["error"] = result["error"]
    return {**state, **updates}


def _select_route(state: AgentState) -> str:
    return state.get("route", "INSIGHTS")


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("router", router_node)
    graph.add_node("create_agent", create_node)
    graph.add_node("update_agent", update_node)
    graph.add_node("insights_agent", insights_node)
    graph.add_node("executor", executor_node)

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        _select_route,
        {
            "CREATE": "create_agent",
            "UPDATE": "update_agent",
            "INSIGHTS": "insights_agent",
        },
    )
    graph.add_edge("create_agent", "executor")
    graph.add_edge("update_agent", "executor")
    graph.add_edge("insights_agent", "executor")
    graph.add_edge("executor", END)

    return graph.compile()
