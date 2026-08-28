"""Tool permission registry."""

from typing import Literal

RiskLevel = Literal["safe", "risky"]

TOOLS: dict[str, dict[str, str]] = {
    "read_db": {"risk": "safe", "scope": "analytics_ro"},
    "get_schema": {"risk": "safe", "scope": "analytics_ro"},
    "make_chart": {"risk": "safe", "scope": "local_fs"},
    "fetch_page": {"risk": "safe", "scope": "network_ro"},
    "write_db": {"risk": "risky", "scope": "analytics_rw"},
    "send_email": {"risk": "risky", "scope": "external_send"},
}


def get_tool_risk(tool_name: str) -> RiskLevel:
    tool = TOOLS.get(tool_name)
    if not tool:
        raise ValueError(f"Unknown tool: {tool_name}")
    return tool["risk"]  # type: ignore[return-value]


def is_risky(tool_name: str) -> bool:
    return get_tool_risk(tool_name) == "risky"
