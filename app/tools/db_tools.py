"""Database tools with read-only and read-write connections."""

from __future__ import annotations

import re
import time
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings

SELECT_ONLY_PATTERN = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE | re.DOTALL)
FORBIDDEN_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

_schema_cache: str | None = None


def _validate_select_only(sql: str) -> None:
    stripped = sql.strip().rstrip(";")
    if not SELECT_ONLY_PATTERN.match(stripped):
        raise PermissionError("read_db only accepts SELECT statements")
    if FORBIDDEN_PATTERN.search(stripped):
        raise PermissionError("read_db rejected forbidden SQL keyword")


def _wrap_with_limit(sql: str, limit: int = 1000) -> str:
    stripped = sql.strip().rstrip(";")
    if re.search(r"\bLIMIT\b", stripped, re.IGNORECASE):
        return stripped
    return f"SELECT * FROM ({stripped}) AS _limited LIMIT {limit}"


def read_db(sql: str) -> list[dict[str, Any]]:
    """Execute a read-only SELECT query."""
    settings = get_settings()
    _validate_select_only(sql)
    limited_sql = _wrap_with_limit(sql)

    start = time.perf_counter()
    with psycopg.connect(settings.database_ro_url, row_factory=dict_row) as conn:
        conn.execute("SET statement_timeout = '30s'")
        with conn.cursor() as cur:
            cur.execute(limited_sql)
            rows = cur.fetchall()
    elapsed = (time.perf_counter() - start) * 1000
    return [dict(row) for row in rows]


def write_db(sql: str) -> dict[str, Any]:
    """Execute a write query (risky — requires approval)."""
    settings = get_settings()
    stripped = sql.strip().rstrip(";")
    if re.match(r"^\s*SELECT\b", stripped, re.IGNORECASE):
        raise PermissionError("write_db does not accept SELECT — use read_db")

    with psycopg.connect(settings.database_rw_url) as conn:
        with conn.cursor() as cur:
            cur.execute(stripped)
            affected = cur.rowcount
        conn.commit()
    return {"status": "ok", "rows_affected": affected}


def get_schema() -> str:
    """Return analytics schema description for SQL agent prompts."""
    global _schema_cache
    if _schema_cache:
        return _schema_cache

    settings = get_settings()
    try:
        with psycopg.connect(settings.database_ro_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_name, column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'analytics'
                    ORDER BY table_name, ordinal_position
                    """
                )
                rows = cur.fetchall()
    except Exception:
        rows = [
            ("regions", "region_id", "integer"),
            ("regions", "name", "character varying"),
            ("customers", "customer_id", "integer"),
            ("customers", "name", "character varying"),
            ("customers", "email", "character varying"),
            ("customers", "region_id", "integer"),
            ("customers", "is_test", "boolean"),
            ("customers", "created_at", "timestamp without time zone"),
            ("orders", "order_id", "integer"),
            ("orders", "customer_id", "integer"),
            ("orders", "region_id", "integer"),
            ("orders", "amount", "numeric"),
            ("orders", "order_date", "date"),
            ("orders", "status", "character varying"),
            ("refunds", "refund_id", "integer"),
            ("refunds", "order_id", "integer"),
            ("refunds", "region_id", "integer"),
            ("refunds", "amount", "numeric"),
            ("refunds", "refund_date", "date"),
            ("refunds", "reason", "character varying"),
            ("support_tickets", "ticket_id", "integer"),
            ("support_tickets", "customer_id", "integer"),
            ("support_tickets", "subject", "character varying"),
            ("support_tickets", "body", "text"),
            ("support_tickets", "status", "character varying"),
            ("support_tickets", "created_at", "timestamp without time zone"),
        ]

    tables: dict[str, list[str]] = {}
    for table_name, column_name, data_type in rows:
        tables.setdefault(table_name, []).append(f"{column_name} ({data_type})")

    lines = ["Schema: analytics"]
    for table, cols in tables.items():
        lines.append(f"  {table}: {', '.join(cols)}")

    _schema_cache = "\n".join(lines)
    return _schema_cache


def clear_schema_cache() -> None:
    global _schema_cache
    _schema_cache = None
