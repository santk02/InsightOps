"""Supervisor logic for the report workflow."""

from __future__ import annotations

from typing import Literal

from app.config import get_settings

Route = Literal["sql", "chart", "research", "review", "critic", "done"]


def build_plan(request: str) -> list[str]:
    request_l = request.lower()
    plan: list[str] = ["sql"]
    if any(keyword in request_l for keyword in ("chart", "graph", "plot", "visual", "trend")):
        plan.append("chart")
    if any(keyword in request_l for keyword in ("research", "context", "news", "web", "external")):
        plan.append("research")
    plan.extend(["review", "critic"])
    return plan


def route_next(state: dict) -> Route:
    settings = get_settings()
    iterations = int(state.get("iterations", 0))
    if iterations >= settings.max_iterations:
        return "done"

    plan = state.get("plan") or build_plan(state.get("request", ""))
    step_index = int(state.get("step_index", 0))
    if step_index >= len(plan):
        return "done"
    return plan[step_index]  # type: ignore[return-value]

