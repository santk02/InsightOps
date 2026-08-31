"""Pydantic models used by the InsightOps API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    """Request payload for a report run."""

    request: str = Field(..., min_length=3)  # the natural-language ask, e.g. "why did refunds spike..."
    user_id: str = "default"  # identifies whose memories to recall/persist


class ApproveRequest(BaseModel):
    """Approve or deny a pending risky action."""

    run_id: str  # the paused run to resume
    approved: bool  # True = execute the risky tool, False = deny and continue without it
    approver: str = "human"  # identity recorded in the audit log


class MemoryCreateRequest(BaseModel):
    """Store a durable preference or fact."""

    user_id: str = "default"
    text: str = Field(..., min_length=1)  # the fact/preference text to remember


class MemoryRecord(BaseModel):
    """A persisted memory item."""

    id: str
    user_id: str
    text: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunResponse(BaseModel):
    """Response returned by a run or resume operation."""

    run_id: str
    status: str  # running | awaiting_approval | done | failed | denied
    request: str
    user_id: str
    summary: str | None = None  # the final (or in-progress) narrative
    sql: str | None = None  # generated SQL, shown so a human can verify the reasoning
    rows: list[dict[str, Any]] | None = None  # query result set
    chart_path: str | None = None  # path to the generated PNG, if any
    critic_score: float | None = None  # last LLM-as-judge score (0.0-1.0)
    pending_tool: dict[str, Any] | None = None  # risky call waiting on /v1/approve
    approval_required: bool = False  # True while paused awaiting a human decision
    approved: bool | None = None  # outcome of the approval decision, once resolved
    revisions: int = 0  # how many critic-triggered revision passes ran
    iterations: int = 0  # how many plan steps were executed


class DeadLetterRecord(BaseModel):
    """A failed job that should be replayable."""

    id: int
    run_id: str
    payload: dict[str, Any]
    error: str
    attempts: int
    created_at: datetime
