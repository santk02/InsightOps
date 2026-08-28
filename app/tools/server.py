"""MCP server entrypoint for InsightOps tools."""

from __future__ import annotations

from typing import Any

from app.tools.chart_tools import make_chart
from app.tools.db_tools import get_schema, read_db, write_db
from app.tools.web_tools import fetch_page, send_email

try:  # pragma: no cover - optional MCP runtime
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover
    FastMCP = None  # type: ignore[assignment]


def build_server() -> Any:
    if FastMCP is None:
        raise RuntimeError("MCP runtime is not available in this environment")

    server = FastMCP("InsightOps")

    @server.tool()
    def read_db_tool(sql: str) -> list[dict[str, Any]]:
        return read_db(sql)

    @server.tool()
    def write_db_tool(sql: str) -> dict[str, Any]:
        return write_db(sql)

    @server.tool()
    def get_schema_tool() -> str:
        return get_schema()

    @server.tool()
    def make_chart_tool(
        rows: list[dict[str, Any]],
        kind: str = "bar",
        x: str | None = None,
        y: str | None = None,
        title: str = "Chart",
    ) -> str:
        return make_chart(rows, kind=kind, x=x, y=y, title=title)

    @server.tool()
    def fetch_page_tool(url: str) -> str:
        return fetch_page(url)

    @server.tool()
    def send_email_tool(to: str, subject: str, body: str) -> dict[str, str]:
        return send_email(to, subject, body)

    return server


def main() -> None:  # pragma: no cover - manual entrypoint
    server = build_server()
    server.run()
