"""Database tools with read-only and read-write connections.

Security note (blueprint section 3, "Why MCP for tools?" / Phase 1): the
SELECT-only restriction on `read_db` is enforced here in code — and, more
importantly, by connecting through a database ROLE that only has SELECT
grants (see scripts/init_db.sql). Never rely on the prompt alone to keep an
agent from running a destructive statement.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings

# A statement must start with SELECT or WITH (for CTEs) to be considered read-only
SELECT_ONLY_PATTERN = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE | re.DOTALL)
# Any of these keywords appearing anywhere in the statement is an automatic reject,
# even if the statement technically starts with SELECT (e.g. a smuggled second statement)
FORBIDDEN_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

# Cached schema description so repeated calls don't re-hit the database every time
_schema_cache: str | None = None


def _validate_select_only(sql: str) -> None:
    """Reject anything that isn't a plain SELECT/WITH, or that hides a write keyword."""
    stripped = sql.strip().rstrip(";")
    if not SELECT_ONLY_PATTERN.match(stripped):
        raise PermissionError("read_db only accepts SELECT statements")
    if FORBIDDEN_PATTERN.search(stripped):
        raise PermissionError("read_db rejected forbidden SQL keyword")


def _wrap_with_limit(sql: str, limit: int = 1000) -> str:
    """Force a row cap by wrapping the query in an outer SELECT ... LIMIT, unless one exists."""
    stripped = sql.strip().rstrip(";")
    if re.search(r"\bLIMIT\b", stripped, re.IGNORECASE):
        return stripped
    return f"SELECT * FROM ({stripped}) AS _limited LIMIT {limit}"


def read_db(sql: str) -> list[dict[str, Any]]:
    """Execute a read-only SELECT query via the analytics_ro role, capped at 1000 rows."""
    settings = get_settings()
    _validate_select_only(sql)  # code-level guard...
    limited_sql = _wrap_with_limit(sql)

    # ...backed by the database-level guard: this connection string is the read-only role,
    # so even a SQL statement that slipped past validation would be rejected by Postgres itself
    with psycopg.connect(settings.database_ro_url, row_factory=dict_row) as conn:
        conn.execute("SET statement_timeout = '30s'")  # bound how long a bad query can run
        with conn.cursor() as cur:
            cur.execute(limited_sql)
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def write_db(sql: str, params: Sequence[Any] | None = None) -> dict[str, Any]:
    """Execute a write query via the analytics_rw role. RISKY — must go through the approval gate.

    Prefer passing `params` for any user- or LLM-derived values so psycopg
    parameterizes them, rather than interpolating them into `sql` yourself.
    """
    settings = get_settings()
    stripped = sql.strip().rstrip(";")
    if re.match(r"^\s*SELECT\b", stripped, re.IGNORECASE):
        raise PermissionError("write_db does not accept SELECT — use read_db")

    with psycopg.connect(settings.database_rw_url) as conn:
        with conn.cursor() as cur:
            cur.execute(stripped, params)  # psycopg parameter-binds `params`; never string-format values in
            affected = cur.rowcount
        conn.commit()
    return {"status": "ok", "rows_affected": affected}


def get_schema() -> str:
    """Return a human-readable analytics schema description for SQL-generation prompts."""
    global _schema_cache
    if _schema_cache:
        return _schema_cache  # served from cache after the first successful lookup

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
        # No live database (e.g. local dev without Docker running) — fall back to the
        # schema baked into scripts/init_db.sql so prompts still get accurate column names
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
    """Drop the cached schema string, forcing the next get_schema() call to re-query."""
    global _schema_cache
    _schema_cache = None
