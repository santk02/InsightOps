"""Pydantic models used by the InsightOps API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    """Request payload for a report run."""

    request: str = Field(..., min_length=3)
    user_id: str = "default"


class ApproveRequest(BaseModel):
    """Approve or deny a pending risky action."""

    run_id: str
    approved: bool
    approver: str = "human"


class MemoryCreateRequest(BaseModel):
    """Store a durable preference or fact."""

    user_id: str = "default"
    text: str = Field(..., min_length=1)


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
    status: str
    request: str
    user_id: str
    summary: str | None = None
    sql: str | None = None
    rows: list[dict[str, Any]] | None = None
    chart_path: str | None = None
    critic_score: float | None = None
    pending_tool: dict[str, Any] | None = None
    approval_required: bool = False
    approved: bool | None = None
    revisions: int = 0
    iterations: int = 0


class DeadLetterRecord(BaseModel):
    """A failed job that should be replayable."""

    id: int
    run_id: str
    payload: dict[str, Any]
    error: str
    attempts: int
    created_at: datetime

