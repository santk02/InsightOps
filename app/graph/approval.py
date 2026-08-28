"""Approval gate helpers."""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.tools.registry import is_risky


def requires_approval(tool_name: str) -> bool:
    return is_risky(tool_name)


def build_pending_tool(tool_name: str, arguments: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "arguments": arguments,
        "risk": "risky",
        "reason": reason,
    }


def approval_enabled() -> bool:
    return get_settings().approvals_enabled

