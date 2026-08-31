"""Approval gate helpers.

Implements the blueprint's central safety claim: "the approval gate is
enforced in the graph, not in the system prompt." These helpers are pure,
side-effect-free lookups/builders — the engine (build.py) is what actually
suspends execution and waits on a human decision.
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.tools.registry import is_risky


def requires_approval(tool_name: str) -> bool:
    """True if the named tool is tagged "risky" in the registry and must be gated."""
    return is_risky(tool_name)


def build_pending_tool(tool_name: str, arguments: dict[str, Any], reason: str) -> dict[str, Any]:
    """Shape the payload written into state (and returned to the API) while awaiting approval."""
    return {
        "tool_name": tool_name,
        "arguments": arguments,
        "risk": "risky",
        "reason": reason,
    }


def approval_enabled() -> bool:
    """Master switch — when False, risky tools auto-run instead of pausing (useful for local demos)."""
    return get_settings().approvals_enabled
