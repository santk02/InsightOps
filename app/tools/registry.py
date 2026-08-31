"""Tool permission registry.

This is the single source of truth for which tools exist, what they are
allowed to touch (`scope`), and whether they can auto-run or must go through
the human-approval gate (`risk`). The approval logic (app/graph/approval.py)
consults this map rather than trusting a prompt to say a call is safe.
"""

from typing import Literal

RiskLevel = Literal["safe", "risky"]

# tool_name -> {risk, scope}. "risky" tools always require an explicit human approval.
TOOLS: dict[str, dict[str, str]] = {
    "read_db": {"risk": "safe", "scope": "analytics_ro"},      # SELECT-only, read-only DB role
    "get_schema": {"risk": "safe", "scope": "analytics_ro"},   # schema introspection, read-only
    "make_chart": {"risk": "safe", "scope": "local_fs"},       # writes a PNG to local disk only
    "fetch_page": {"risk": "safe", "scope": "network_ro"},     # outbound GET only, no side effects
    "write_db": {"risk": "risky", "scope": "analytics_rw"},    # mutates the database
    "send_email": {"risk": "risky", "scope": "external_send"}, # irreversible external side effect
}


def get_tool_risk(tool_name: str) -> RiskLevel:
    """Look up a tool's risk tag; raises for anything not in the registry."""
    tool = TOOLS.get(tool_name)
    if not tool:
        raise ValueError(f"Unknown tool: {tool_name}")
    return tool["risk"]  # type: ignore[return-value]


def is_risky(tool_name: str) -> bool:
    """True if this tool must be gated behind human approval before it runs."""
    return get_tool_risk(tool_name) == "risky"
