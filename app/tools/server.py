"""MCP server entrypoint for InsightOps tools.

Exposes the tool functions over the Model Context Protocol so an agent (or a
manual client, for the Phase 1 "call each tool directly" test) can discover
and invoke them without the caller hardcoding a tool registry. Permission
scoping still comes from app/tools/registry.py, consulted by the graph
before a risky tool is allowed to execute.
"""

from __future__ import annotations

from typing import Any

from app.tools.chart_tools import make_chart
from app.tools.db_tools import get_schema, read_db, write_db
from app.tools.web_tools import fetch_page, send_email

try:  # pragma: no cover - optional MCP runtime
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover
    FastMCP = None  # type: ignore[assignment]  # lets the module import even without the mcp package


def build_server() -> Any:
    """Construct the FastMCP server and register each InsightOps tool on it."""
    if FastMCP is None:
        raise RuntimeError("MCP runtime is not available in this environment")

    server = FastMCP("InsightOps")

    @server.tool()
    def read_db_tool(sql: str) -> list[dict[str, Any]]:
        return read_db(sql)  # safe — SELECT-only, read-only role

    @server.tool()
    def write_db_tool(sql: str) -> dict[str, Any]:
        return write_db(sql)  # risky — caller must have gone through the approval gate

    @server.tool()
    def get_schema_tool() -> str:
        return get_schema()  # safe — schema introspection only

    @server.tool()
    def make_chart_tool(
        rows: list[dict[str, Any]],
        kind: str = "bar",
        x: str | None = None,
        y: str | None = None,
        title: str = "Chart",
    ) -> str:
        return make_chart(rows, kind=kind, x=x, y=y, title=title)  # safe — local filesystem only

    @server.tool()
    def fetch_page_tool(url: str) -> str:
        return fetch_page(url)  # safe — outbound GET only

    @server.tool()
    def send_email_tool(to: str, subject: str, body: str) -> dict[str, str]:
        return send_email(to, subject, body)  # risky — external, irreversible side effect

    return server


def main() -> None:  # pragma: no cover - manual entrypoint
    """Run the MCP server over stdio (or its configured transport)."""
    server = build_server()
    server.run()
