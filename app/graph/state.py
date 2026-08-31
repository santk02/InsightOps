"""Shared graph state.

Mirrors the blueprint's AgentState TypedDict (section 6): one small, typed
object that every step reads and writes. `iterations` and `revisions` are
the two fields that guarantee the workflow terminates.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

try:
    from langgraph.graph.message import add_messages
except Exception:  # pragma: no cover - fallback for environments without LangGraph internals
    def add_messages(left, right):  # type: ignore[no-redef]
        # Minimal stand-in: just concatenate message lists if langgraph isn't installed
        return (left or []) + (right or [])


class AgentState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]  # conversation so far (append-only via add_messages)
    request: str  # the original user ask
    user_id: str  # whose memories to recall/persist
    run_id: str  # unique id for this run, used for audit correlation
    plan: list[str]  # ordered steps the supervisor decided on
    step_index: int  # where we are in the plan
    sql: str | None  # last generated SQL
    rows: list[dict[str, Any]] | None  # query result
    chart_path: str | None  # path to the generated chart PNG, if any
    draft: str | None  # candidate answer
    critic_score: float | None  # last LLM-as-judge score
    revisions: int  # count of critic-triggered revisions so far — hard cap enforced elsewhere
    pending_tool: dict[str, Any] | None  # risky call awaiting approval
    approved: bool | None  # outcome of the approval decision
    memories: list[str]  # facts recalled from Mem0 (or the local fallback store)
    iterations: int  # loop guard — hard cap enforced elsewhere
    status: Literal["running", "awaiting_approval", "done", "failed", "denied"]
    approval_required: bool  # True while paused waiting on a human decision
    error: str | None  # last recorded failure, if any
    tool_results: list[dict[str, Any]]  # audit trail of tool invocations for this run
