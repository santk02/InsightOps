"""Shared graph state."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

try:
    from langgraph.graph.message import add_messages
except Exception:  # pragma: no cover - fallback for environments without LangGraph internals
    def add_messages(left, right):  # type: ignore[no-redef]
        return (left or []) + (right or [])


class AgentState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    request: str
    user_id: str
    run_id: str
    plan: list[str]
    step_index: int
    sql: str | None
    rows: list[dict[str, Any]] | None
    chart_path: str | None
    draft: str | None
    critic_score: float | None
    revisions: int
    pending_tool: dict[str, Any] | None
    approved: bool | None
    memories: list[str]
    iterations: int
    status: Literal["running", "awaiting_approval", "done", "failed", "denied"]
    approval_required: bool
    error: str | None
    tool_results: list[dict[str, Any]]

