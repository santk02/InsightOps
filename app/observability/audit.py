"""Audit logging for runs and tool calls.

The blueprint uses PostgreSQL for the audit trail. This module tries the
database first and falls back to a JSONL file when the database is unavailable
so the rest of the app remains usable in local development and tests.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg

from app.config import get_settings


def _utcnow() -> datetime:
    """Timezone-aware current time for every logged event."""
    return datetime.now(timezone.utc)


def _json_default(value: Any) -> Any:
    """json.dumps default= hook — serialize datetimes as ISO 8601 strings."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass
class AuditLogger:
    """Persist audit events to Postgres when available, otherwise to disk."""

    fallback_path: Path | None = None  # JSONL file used when the database write fails

    def __post_init__(self) -> None:
        """Resolve the fallback file path and cache the audit database URL."""
        settings = get_settings()
        if self.fallback_path is None:
            base_dir = Path(os.getenv("INSIGHTOPS_DATA_DIR", Path.home() / ".insightops"))
            base_dir.mkdir(parents=True, exist_ok=True)
            self.fallback_path = base_dir / "audit.jsonl"
        self._database_url = settings.database_url

    def _append_fallback(self, payload: dict[str, Any]) -> None:
        """Append one JSON line to the local fallback log — used whenever the DB write fails."""
        assert self.fallback_path is not None
        self.fallback_path.parent.mkdir(parents=True, exist_ok=True)
        with self.fallback_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=_json_default))
            handle.write("\n")

    def _execute(self, sql: str, params: tuple[Any, ...]) -> bool:
        """Run one write against the audit database; return False (never raise) on any failure."""
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                conn.commit()
            return True
        except Exception:
            return False  # caller falls back to the JSONL file — audit logging must never break a run

    def log_run_start(self, run_id: str, user_id: str, request: str) -> None:
        """Record the start of a new run (upserts in case of a retried start)."""
        payload = {
            "event": "run_start",
            "run_id": run_id,
            "user_id": user_id,
            "request": request,
            "created_at": _utcnow(),
        }
        if not self._execute(
            """
            INSERT INTO runs (run_id, user_id, request, status, started_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (run_id) DO UPDATE
            SET user_id = EXCLUDED.user_id,
                request = EXCLUDED.request,
                status = EXCLUDED.status
            """,
            (run_id, user_id, request, "running"),
        ):
            self._append_fallback(payload)

    def log_run_status(
        self,
        run_id: str,
        status: str,
        total_cost: float | None = None,
        total_ms: float | None = None,
    ) -> None:
        """Update a run's status (and, for terminal states, its end time / cost / duration)."""
        payload = {
            "event": "run_status",
            "run_id": run_id,
            "status": status,
            "total_cost": total_cost,
            "total_ms": total_ms,
            "created_at": _utcnow(),
        }
        if not self._execute(
            """
            UPDATE runs
            SET status = %s,
                ended_at = CASE WHEN %s IN ('done', 'failed', 'denied') THEN NOW() ELSE ended_at END,
                total_cost = COALESCE(%s, total_cost),
                total_ms = COALESCE(%s, total_ms)
            WHERE run_id = %s
            """,
            (status, status, total_cost, total_ms, run_id),
        ):
            self._append_fallback(payload)

    def log_tool_call(
        self,
        run_id: str,
        step_index: int,
        tool_name: str,
        risk: str,
        arguments: dict[str, Any],
        result_summary: str,
        approved_by: str | None,
        status: str,
        attempts: int = 1,
        latency_ms: float | None = None,
    ) -> None:
        """Record one tool invocation — this is the row-level record the compliance story relies on."""
        payload = {
            "event": "tool_call",
            "run_id": run_id,
            "step_index": step_index,
            "tool_name": tool_name,
            "risk": risk,
            "arguments": arguments,
            "result_summary": result_summary,
            "approved_by": approved_by,
            "status": status,
            "attempts": attempts,
            "latency_ms": latency_ms,
            "created_at": _utcnow(),
        }
        if not self._execute(
            """
            INSERT INTO tool_calls
            (run_id, step_index, tool_name, risk, arguments, result_summary, approved_by, status, attempts, latency_ms)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                step_index,
                tool_name,
                risk,
                json.dumps(arguments, default=_json_default),
                result_summary,
                approved_by,
                status,
                attempts,
                latency_ms,
            ),
        ):
            self._append_fallback(payload)

    def record_dead_letter(self, run_id: str, payload: dict[str, Any], error: str, attempts: int) -> None:
        """Record a job that exhausted its retries, mirroring what QueueWorker writes to the DLQ store."""
        item = {
            "event": "dead_letter",
            "run_id": run_id,
            "payload": payload,
            "error": error,
            "attempts": attempts,
            "created_at": _utcnow(),
        }
        if not self._execute(
            """
            INSERT INTO dead_letters (run_id, payload, error, attempts)
            VALUES (%s, %s::jsonb, %s, %s)
            """,
            (run_id, json.dumps(payload, default=_json_default), error, attempts),
        ):
            self._append_fallback(item)


def get_audit_logger() -> AuditLogger:
    """Construct a fresh AuditLogger (cheap — connections are opened per call, not held open)."""
    return AuditLogger()
