"""Supervisor logic for the report workflow.

Owns routing: given the request, decide which steps run (`build_plan`) and,
for a real LangGraph-style state-graph traversal, which node runs next
(`route_next`). The engine in build.py currently walks the plan directly
rather than calling `route_next` on every hop, but the function is kept as
the seam a real `StateGraph` would call into — see README "Architecture
Notes" for the difference between this engine and a live LangGraph graph.
"""

from __future__ import annotations

from typing import Literal

from app.config import get_settings

Route = Literal["sql", "chart", "research", "review", "critic", "done"]


def build_plan(request: str) -> list[str]:
    """Decide which optional steps a request needs, based on simple keyword heuristics."""
    request_l = request.lower()
    plan: list[str] = ["sql"]  # every report starts by answering from the database
    if any(keyword in request_l for keyword in ("chart", "graph", "plot", "visual", "trend")):
        plan.append("chart")  # only chart when the request implies a visual
    if any(keyword in request_l for keyword in ("research", "context", "news", "web", "external")):
        plan.append("research")  # only fetch external context when asked for it
    plan.extend(["review", "critic"])  # every report ends with a draft + a critic pass
    return plan


def route_next(state: dict) -> Route:
    """Given the current state, return the next node to run — the supervisor's core decision.

    Enforces the iteration hard cap from the blueprint: the agent never gets
    to decide for itself whether to keep going past `max_iterations`.
    """
    settings = get_settings()
    iterations = int(state.get("iterations", 0))
    if iterations >= settings.max_iterations:
        return "done"  # runaway-loop guard — force stop regardless of plan progress

    plan = state.get("plan") or build_plan(state.get("request", ""))
    step_index = int(state.get("step_index", 0))
    if step_index >= len(plan):
        return "done"
    return plan[step_index]  # type: ignore[return-value]
