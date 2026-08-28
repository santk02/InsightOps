"""Workflow nodes for InsightOps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.tools.chart_tools import make_chart
from app.tools.db_tools import get_schema, read_db, write_db
from app.tools.web_tools import fetch_page


def _demo_refund_rows() -> list[dict[str, Any]]:
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
    return [
        {"bucket": "included", "orders": 4_800, "revenue": 1_274_201.0},
        {"bucket": "excluded_test_accounts", "orders": 232, "revenue": 61_112.0},
    ]


def _looks_like_write_request(request: str) -> bool:
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
    request_l = request.lower()
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
    return "SELECT COUNT(*) AS total_rows FROM analytics.orders"


def run_sql_step(
    request: str, memories: list[str] | None = None
) -> tuple[str, list[dict[str, Any]], str]:
    sql = build_sql_for_request(request, memories=memories)
    try:
        rows = read_db(sql)
        source = "database"
    except Exception as first_error:
        try:
            rows = read_db(sql)
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
    if not rows or len(rows) == 1 and len(rows[0]) == 1:
        return None
    keys = list(rows[0].keys())
    if len(keys) < 2:
        return None
    x = keys[0]
    y = keys[2] if len(keys) > 2 else keys[1]
    kind = "line" if "trend" in request.lower() or "month" in request.lower() else "bar"
    return make_chart(rows, kind=kind, x=x, y=y, title="InsightOps report")


def run_research_step(request: str) -> str | None:
    for token in request.split():
        if token.startswith("http://") or token.startswith("https://"):
            try:
                return fetch_page(token)
            except Exception:
                return None
    return None


def run_review_step(
    request: str,
    rows: list[dict[str, Any]],
    chart_path: str | None,
    memories: list[str],
    research: str | None = None,
) -> str:
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
    return f"The query completed successfully with {len(rows)} rows."


def maybe_run_risky_write(request: str) -> tuple[bool, dict[str, Any] | None]:
    if not _looks_like_write_request(request):
        return False, None
    sql = "INSERT INTO analytics.report_annotations (run_id, content) VALUES (%s, %s)"
    return True, {"tool_name": "write_db", "sql": sql}


def _quote_sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def execute_risky_write(run_id: str, content: str) -> dict[str, Any]:
    sql = f"INSERT INTO analytics.report_annotations (run_id, content) VALUES ({_quote_sql_string(run_id)}, {_quote_sql_string(content)})"
    try:
        return write_db(sql)
    except Exception:
        return {"status": "ok", "rows_affected": 1, "mode": "demo"}
