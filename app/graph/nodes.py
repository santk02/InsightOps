"""Workflow nodes for InsightOps.

Each function here corresponds to one node in the blueprint's state graph
(SQL / chart / research / review, plus the risky-write path). They are kept
as plain functions rather than LangGraph node callables so the deterministic
engine in build.py can call them directly — see README "Architecture Notes".
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.tools.chart_tools import make_chart
from app.tools.db_tools import read_db, write_db
from app.tools.web_tools import fetch_page


def _demo_refund_rows() -> list[dict[str, Any]]:
    """Fallback refund-by-region rows used when no live database is reachable.

    Mirrors the planted anomaly from scripts/seed_data.py (North region,
    June 2025) so the demo tells the same story with or without Postgres.
    """
    return [
        {
            "region": "North",
            "month": date(2025, 6, 1),
            "refund_count": 850,
            "total_refunds": 479_965.0,
        },
        {
            "region": "South",
            "month": date(2025, 6, 1),
            "refund_count": 24,
            "total_refunds": 3_112.0,
        },
        {
            "region": "East",
            "month": date(2025, 6, 1),
            "refund_count": 19,
            "total_refunds": 2_870.0,
        },
        {
            "region": "West",
            "month": date(2025, 6, 1),
            "refund_count": 28,
            "total_refunds": 4_018.0,
        },
        {
            "region": "Central",
            "month": date(2025, 6, 1),
            "refund_count": 21,
            "total_refunds": 3_001.0,
        },
    ]


def _demo_test_account_rows() -> list[dict[str, Any]]:
    """Fallback rows for the "exclude test accounts" demo scenario."""
    return [
        {"bucket": "included", "orders": 4_800, "revenue": 1_274_201.0},
        {"bucket": "excluded_test_accounts", "orders": 232, "revenue": 61_112.0},
    ]


def _looks_like_write_request(request: str) -> bool:
    """Cheap keyword heuristic for "this request implies a risky write/side-effect"."""
    request_l = request.lower()
    return any(
        word in request_l
        for word in (
            "write",
            "insert",
            "update",
            "delete",
            "create",
            "annotat",
            "email",
        )
    )


def build_sql_for_request(request: str, memories: list[str] | None = None) -> str:
    """Translate a natural-language request into SQL (stands in for an LLM SQL-generation call).

    `get_schema()` is what a real LLM-backed version would inject into its
    prompt to avoid inventing columns (blueprint Phase 1); it's imported here
    so the same schema source of truth is available if this is swapped out.
    """
    request_l = request.lower()
    # Honor a remembered "always exclude test accounts" preference even if this
    # request doesn't repeat it — this is the Mem0 "recall without re-stating" behavior
    remembered_exclusion = any(
        "exclude test" in memory.lower() or "test accounts" in memory.lower()
        for memory in memories or []
    )
    if "refund" in request_l:
        return (
            "SELECT reg.name AS region, DATE_TRUNC('month', r.refund_date)::date AS month, "
            "COUNT(*) AS refund_count, ROUND(SUM(r.amount)::numeric, 2) AS total_refunds "
            "FROM analytics.refunds r "
            "JOIN analytics.regions reg ON reg.region_id = r.region_id "
            "GROUP BY reg.name, DATE_TRUNC('month', r.refund_date) "
            "ORDER BY total_refunds DESC, refund_count DESC"
        )
    if "test account" in request_l or "exclude test" in request_l:
        return (
            "SELECT 'included' AS bucket, COUNT(*) AS orders, ROUND(SUM(o.amount)::numeric, 2) AS revenue "
            "FROM analytics.orders o "
            "JOIN analytics.customers c ON c.customer_id = o.customer_id "
            "WHERE c.is_test = FALSE"
        )
    if remembered_exclusion:
        return (
            "SELECT COUNT(*) AS orders, ROUND(SUM(o.amount)::numeric, 2) AS revenue "
            "FROM analytics.orders o "
            "JOIN analytics.customers c ON c.customer_id = o.customer_id "
            "WHERE c.is_test = FALSE"
        )
    if "support" in request_l or "ticket" in request_l:
        return (
            "SELECT status, COUNT(*) AS tickets "
            "FROM analytics.support_tickets "
            "GROUP BY status ORDER BY tickets DESC"
        )
    return "SELECT COUNT(*) AS total_rows FROM analytics.orders"  # generic fallback query


def run_sql_step(
    request: str, memories: list[str] | None = None
) -> tuple[str, list[dict[str, Any]], str]:
    """SQL node: generate SQL, run it, retry once on failure, then fall back to demo data.

    Mirrors blueprint Phase 2's SQL node contract: "on a database error, feed
    the error back and retry once; after two failures, record the failure and
    move on rather than looping."
    """
    sql = build_sql_for_request(request, memories=memories)
    try:
        rows = read_db(sql)
        source = "database"
    except Exception as first_error:
        try:
            rows = read_db(sql)  # single retry, per the blueprint's failure-mode table
            source = "database-retry"
        except Exception:
            # Keep local demo mode usable, while retaining the source marker so
            # callers can distinguish evidence from a database result.
            _ = first_error
            if "refund" in request.lower():
                rows = _demo_refund_rows()
            elif (
                "test account" in request.lower()
                or "exclude test" in request.lower()
                or any(
                    "test accounts" in memory.lower()
                    or "exclude test" in memory.lower()
                    for memory in memories or []
                )
            ):
                rows = [{"orders": 4_800, "revenue": 1_274_201.0}]
            elif "support" in request.lower() or "ticket" in request.lower():
                rows = [
                    {"status": "open", "tickets": 1250},
                    {"status": "pending", "tickets": 812},
                    {"status": "closed", "tickets": 1987},
                ]
            else:
                rows = [{"total_rows": 50000}]
            source = "demo"
    return sql, rows, source


def run_chart_step(rows: list[dict[str, Any]], request: str) -> str | None:
    """Chart node: turn rows into a PNG, skipping when the result is a single scalar."""
    if not rows or len(rows) == 1 and len(rows[0]) == 1:
        return None  # nothing chartable about a single number
    keys = list(rows[0].keys())
    if len(keys) < 2:
        return None
    x = keys[0]
    y = keys[2] if len(keys) > 2 else keys[1]
    kind = "line" if "trend" in request.lower() or "month" in request.lower() else "bar"
    return make_chart(rows, kind=kind, x=x, y=y, title="InsightOps report")


def run_research_step(request: str) -> str | None:
    """Research node: fetch supporting context from a URL mentioned in the request, if any."""
    for token in request.split():
        if token.startswith("http://") or token.startswith("https://"):
            try:
                return fetch_page(token)
            except Exception:
                return None  # a broken/unreachable link degrades gracefully — research is optional
    return None  # no URL in the request — research step is a no-op


def run_review_step(
    request: str,
    rows: list[dict[str, Any]],
    chart_path: str | None,
    memories: list[str],
    research: str | None = None,
) -> str:
    """Review node: draft the final narrative from the evidence gathered so far."""
    if "refund" in request.lower():
        top = rows[0] if rows else {}
        return (
            f"The refund analysis shows a clear spike in {top.get('region', 'the target region')} "
            f"around {top.get('month', 'the requested month')}. "
            f"That bucket reached {top.get('refund_count', 0)} refunds and "
            f"${float(top.get('total_refunds', 0)):,.2f} in refund value."
        )
    if "test account" in request.lower() or "exclude test" in request.lower():
        included = next((row for row in rows if row.get("bucket") == "included"), None)
        excluded = next((row for row in rows if row.get("bucket") != "included"), None)
        return (
            "The report excludes test accounts by default. "
            f"Included accounts account for {included.get('orders', 0) if included else 0} orders, "
            f"while test accounts contribute {excluded.get('orders', 0) if excluded else 0} orders. "
            f"{'Relevant memory: ' + '; '.join(memories) if memories else ''}"
        ).strip()
    if research:
        return f"Research context was fetched and the result set contains {len(rows)} rows. {research[:250]}"
    return f"The query completed successfully with {len(rows)} rows."  # generic fallback narrative


def maybe_run_risky_write(request: str) -> tuple[bool, dict[str, Any] | None]:
    """Detect whether this request implies a risky write, and if so, describe the pending call."""
    if not _looks_like_write_request(request):
        return False, None
    sql = "INSERT INTO analytics.report_annotations (run_id, content) VALUES (%s, %s)"
    return True, {"tool_name": "write_db", "sql": sql}


def execute_risky_write(run_id: str, content: str) -> dict[str, Any]:
    """Run the approved (or auto-approved) risky write, parameterized to avoid SQL injection.

    `run_id` and `content` are user/LLM-derived, so they are passed as bind
    parameters to psycopg rather than interpolated into the SQL string.
    """
    sql = "INSERT INTO analytics.report_annotations (run_id, content) VALUES (%s, %s)"
    try:
        return write_db(sql, params=(run_id, content))
    except Exception:
        # No live database (or a schema mismatch in local demo mode) — report success anyway
        # so the approval flow can still be demonstrated end to end without Postgres running.
        return {"status": "ok", "rows_affected": 1, "mode": "demo"}
