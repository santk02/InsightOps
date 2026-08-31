"""Workflow engine for InsightOps.

This is a deterministic, synchronous stand-in for a compiled LangGraph
`StateGraph` with a checkpointer (blueprint Phase 2/3). It reproduces the
same node sequence and the same approval-pause/resume *contract* — callers
see identical `status`/`pending_tool`/`approved` semantics — without
requiring a running LangGraph checkpoint backend. See README "Architecture
Notes" for the tradeoffs and how to swap in a real graph.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from threading import RLock
from time import perf_counter
from typing import Any

from app.graph.approval import approval_enabled, build_pending_tool
from app.graph.critic import score_draft, should_revise
from app.graph.nodes import (
    execute_risky_write,
    maybe_run_risky_write,
    run_chart_step,
    run_research_step,
    run_review_step,
    run_sql_step,
)
from app.graph.supervisor import build_plan
from app.memory.store import get_memory_store
from app.observability.audit import get_audit_logger


@dataclass
class InsightOpsEngine:
    """A deterministic, inspectable version of the blueprint workflow."""

    # Where every tool call and run status transition gets recorded (blueprint section 7)
    audit: Any = field(default_factory=get_audit_logger)
    # Preference recall/persistence backend (Mem0 in production, file-backed locally)
    memory: Any = field(default_factory=get_memory_store)
    # Runs currently paused in `awaiting_approval`, keyed by run_id — this in-memory dict
    # is what stands in for a LangGraph checkpointer's suspend/resume state
    _pending_runs: dict[str, dict[str, Any]] = field(
        default_factory=dict, init=False, repr=False
    )
    # Guards `_pending_runs` against concurrent API requests
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def _new_run_id(self) -> str:
        """Generate a fresh, globally-unique run identifier."""
        return str(uuid.uuid4())

    def start(self, request: str, user_id: str = "default") -> dict[str, Any]:
        """Begin a new report run for the given request."""
        run_id = self._new_run_id()
        return self._execute(
            run_id=run_id,
            request=request,
            user_id=user_id,
            approve=False,
            approver=None,
        )

    def approve(self, run_id: str, approved: bool, approver: str) -> dict[str, Any]:
        """Resume a paused run with a human approve/deny decision."""
        with self._lock:
            pending = self._pending_runs.get(run_id)
        if not pending:
            raise KeyError(f"No pending run found for {run_id}")
        return self._execute(
            run_id=run_id,
            request=pending["request"],
            user_id=pending["user_id"],
            approve=approved,
            approver=approver,
            replay_state=pending,
        )

    def list_pending(self) -> list[dict[str, Any]]:
        """Return every run currently paused awaiting approval."""
        with self._lock:
            return list(self._pending_runs.values())

    def _execute(
        self,
        run_id: str,
        request: str,
        user_id: str,
        approve: bool,
        approver: str | None,
        replay_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run (or resume) one report through the sql -> chart -> research -> review -> critic pipeline."""
        started = perf_counter()
        memories = self.memory.recall(user_id, request)  # inject remembered preferences (Mem0-style recall)
        plan = build_plan(request)  # supervisor decides which optional steps this request needs
        self.audit.log_run_start(run_id, user_id, request)

        state: dict[str, Any] = {
            "run_id": run_id,
            "request": request,
            "user_id": user_id,
            "plan": plan,
            "step_index": 0,
            "iterations": 0,
            "revisions": 0,
            "approved": None,
            "approval_required": False,
            "pending_tool": None,
            "rows": None,
            "chart_path": None,
            "draft": None,
            "critic_score": None,
            "status": "running",
            "memories": memories,
            "tool_results": [],
        }

        if replay_state:
            # Resuming a previously-paused run: restore its prior state, then record the decision
            state.update(replay_state)
            state["approved"] = approve

        # Detect whether this request implies a risky write (write_db) before doing anything else
        risky, pending_tool = maybe_run_risky_write(request)
        if risky and approval_enabled() and not approve and replay_state is None:
            # First time seeing this risky request: pause and wait for a human decision.
            # This is the graph's `interrupt()` equivalent — execution stops here and the
            # run is parked in `_pending_runs` until /v1/approve resumes it.
            state["approval_required"] = True
            state["pending_tool"] = build_pending_tool(
                "write_db",
                {"sql": pending_tool["sql"]},
                "Potentially irreversible write action",
            )
            state["status"] = "awaiting_approval"
            with self._lock:
                self._pending_runs[run_id] = state
            self.audit.log_run_status(run_id, "awaiting_approval")
            self.audit.log_tool_call(
                run_id=run_id,
                step_index=0,
                tool_name="write_db",
                risk="risky",
                arguments=pending_tool,
                result_summary="awaiting approval",
                approved_by=None,
                status="awaiting_approval",
            )
            return self._serialize_response(state)
        elif risky and not approval_enabled() and replay_state is None:
            # Approvals globally disabled (local demo mode) — auto-run the write and log who/what approved it
            write_result = execute_risky_write(run_id, request)
            state["tool_results"].append(
                {"tool": "write_db", "source": "auto-approved", "result": write_result}
            )
            self.audit.log_tool_call(
                run_id=run_id,
                step_index=0,
                tool_name="write_db",
                risk="risky",
                arguments=pending_tool or {},
                result_summary="auto-approved and executed",
                approved_by="system",
                status="ok",
            )

        # --- SQL node ---
        sql, rows, source = run_sql_step(request, memories=memories)
        state["sql"] = sql
        state["rows"] = rows
        state["tool_results"].append(
            {"tool": "read_db", "source": source, "row_count": len(rows)}
        )
        self.audit.log_tool_call(
            run_id=run_id,
            step_index=0,
            tool_name="read_db",
            risk="safe",
            arguments={"sql": sql},
            result_summary=f"{len(rows)} rows from {source}",
            approved_by=None,
            status="ok",
        )

        # --- Chart node (skipped internally if the plan/result doesn't call for one) ---
        chart_path = run_chart_step(rows, request)
        state["chart_path"] = chart_path
        if chart_path:
            self.audit.log_tool_call(
                run_id=run_id,
                step_index=1,
                tool_name="make_chart",
                risk="safe",
                arguments={"chart_path": chart_path},
                result_summary="chart created",
                approved_by=None,
                status="ok",
            )

        # --- Research node (optional; only produces evidence when a URL is present) ---
        research = run_research_step(request)
        if research:
            self.audit.log_tool_call(
                run_id=run_id,
                step_index=2,
                tool_name="fetch_page",
                risk="safe",
                arguments={"request": request},
                result_summary=research[:120],
                approved_by=None,
                status="ok",
            )

        # --- Review node ---
        draft = run_review_step(request, rows, chart_path, memories, research=research)
        state["draft"] = draft

        # --- Critic node + bounded revision loop ---
        critic = score_draft(request, draft, rows, chart_path)
        state["critic_score"] = critic.score
        state["iterations"] = len(plan)
        while should_revise(critic.score, state["revisions"]):
            state["revisions"] += 1  # hard-capped by should_revise() at settings.max_revisions
            draft = draft + (" " + " ".join(critic.issues) if critic.issues else "")
            state["draft"] = draft
            critic = score_draft(request, draft, rows, chart_path)
            state["critic_score"] = critic.score

        if approve and replay_state:
            # Approval granted on resume — execute the previously-pending write now
            execute_risky_write(run_id, request)
            self.audit.log_tool_call(
                run_id=run_id,
                step_index=0,
                tool_name="write_db",
                risk="risky",
                arguments=replay_state.get("pending_tool", {}),
                result_summary="approved and resumed",
                approved_by=approver,
                status="ok",
            )
            state["pending_tool"] = None
        elif replay_state and not approve:
            # Denial is a normal path, not an error — the run still completes without the write
            self.audit.log_tool_call(
                run_id=run_id,
                step_index=0,
                tool_name="write_db",
                risk="risky",
                arguments=replay_state.get("pending_tool", {}),
                result_summary="denied by user",
                approved_by=approver,
                status="denied",
            )
            state["pending_tool"] = None

        duration_ms = (perf_counter() - started) * 1000
        state["status"] = "done"
        self.audit.log_run_status(run_id, "done", total_ms=duration_ms)
        self.memory.remember_preference(user_id, request)  # capture "always ..." / "prefer ..." style asks
        with self._lock:
            self._pending_runs.pop(run_id, None)  # run is complete — no longer resumable
        return self._serialize_response(state)

    def _serialize_response(self, state: dict[str, Any]) -> dict[str, Any]:
        """Project internal engine state down to the shape the API returns (see RunResponse)."""
        summary = state.get("draft")
        if state.get("status") == "awaiting_approval":
            summary = "Run paused for approval."
        return {
            "run_id": state["run_id"],
            "status": state["status"],
            "request": state["request"],
            "user_id": state["user_id"],
            "summary": summary,
            "sql": state.get("sql"),
            "rows": state.get("rows"),
            "chart_path": state.get("chart_path"),
            "critic_score": state.get("critic_score"),
            "pending_tool": state.get("pending_tool"),
            "approval_required": bool(state.get("approval_required")),
            "approved": state.get("approved"),
            "revisions": int(state.get("revisions", 0)),
            "iterations": int(state.get("iterations", 0)),
        }


_ENGINE: InsightOpsEngine | None = None


def get_engine() -> InsightOpsEngine:
    """Return a process-wide singleton engine instance."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = InsightOpsEngine()
    return _ENGINE
