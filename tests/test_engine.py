"""Engine-level tests covering the report pipeline and the approval pause/resume path."""

from __future__ import annotations

from app.graph.build import InsightOpsEngine
from app.memory.store import MemoryStore


class DummyAudit:
    """No-op audit logger so tests don't depend on a database or touch the real audit log."""

    def log_run_start(self, *args, **kwargs):
        return None

    def log_run_status(self, *args, **kwargs):
        return None

    def log_tool_call(self, *args, **kwargs):
        return None


def test_refund_report_uses_demo_rows(tmp_path):
    """A refund question should complete and surface the planted North-region anomaly."""
    engine = InsightOpsEngine(audit=DummyAudit(), memory=MemoryStore(tmp_path / "memories.json"))
    result = engine.start("Why did refunds spike in the north region in June 2025?")
    assert result["status"] == "done"
    assert result["sql"]  # SQL is always shown so a human can verify the reasoning
    assert result["rows"]
    assert "North" in result["summary"]


def test_write_request_pauses_for_approval(tmp_path):
    """A write-implying request must pause; approving it must then let the run complete."""
    engine = InsightOpsEngine(audit=DummyAudit(), memory=MemoryStore(tmp_path / "memories.json"))
    paused = engine.start("Please write an annotation for this report.")
    assert paused["status"] == "awaiting_approval"
    assert paused["approval_required"] is True
    assert paused["pending_tool"] is not None  # the risky call description shown to the approver

    resumed = engine.approve(paused["run_id"], True, "reviewer")
    assert resumed["status"] == "done"
    assert resumed["approved"] is True
