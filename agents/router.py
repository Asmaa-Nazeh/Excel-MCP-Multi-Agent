"""
agents/router.py
-----------------
Router LLM. Classifies the user's request into exactly one of
CREATE / UPDATE / INSIGHTS. It never calls the MCP client and never
touches Excel data -- classification only.
"""

from config import get_llm_client, get_model_name
from prompts import ROUTER_SYSTEM_PROMPT
from utils import safe_json_loads

VALID_ROUTES = {"CREATE", "UPDATE", "INSIGHTS"}


def route_request(user_request: str) -> str:
    client = get_llm_client()
    model = get_model_name()

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": user_request},
        ],
    )
    raw = response.choices[0].message.content or ""
    route = _extract_route(raw)
    if route not in VALID_ROUTES:
        route = _fallback_route(user_request)
    return route


def _extract_route(raw: str) -> str:
    try:
        data = safe_json_loads(raw)
        route = str(data.get("route", "")).strip().upper()
        if route in VALID_ROUTES:
            return route
    except Exception:
        pass
    upper = raw.upper()
    for r in VALID_ROUTES:
        if r in upper:
            return r
    return ""


def _fallback_route(user_request: str) -> str:
    """Last-resort keyword heuristic, only used if the LLM output could
    not be parsed at all (keeps the pipeline resilient to LLM hiccups)."""
    text = user_request.lower()
    if any(k in text for k in ["create", "new workbook", "new file", "new sheet", "make a"]):
        return "CREATE"
    if any(k in text for k in ["update", "change", "edit", "delete", "add row", "set cell", "remove row"]):
        return "UPDATE"
    return "INSIGHTS"
