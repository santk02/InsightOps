"""Input and output safety rails for the public API boundary.

These are lightweight regex rails that stand in for the blueprint's NeMo
Guardrails input/output rail pair: reject obvious prompt-injection attempts
before they ever reach the engine, and scrub connection strings/secrets out
of anything that gets echoed back to a user.
"""

from __future__ import annotations

import re

# Phrases that indicate an attempt to override instructions or bypass the approval gate
_INJECTION_PATTERNS = (
    r"ignore\s+(?:all\s+)?previous instructions",
    r"bypass\s+(?:the\s+)?approval",
    r"skip\s+(?:the\s+)?approval",
    r"reveal\s+(?:the\s+)?system prompt",
)
# Matches Postgres connection strings and "password=" / "api_key:" style secrets
_SECRET_PATTERN = re.compile(
    r"(?:postgres(?:ql)?://|(?:password|api[_ -]?key)\s*[:=])[^\s]+", re.IGNORECASE
)


def validate_request(request: str) -> None:
    """Input rail: raise if the request looks like a prompt-injection/approval-bypass attempt."""
    lowered = request.lower()
    if any(re.search(pattern, lowered) for pattern in _INJECTION_PATTERNS):
        raise ValueError("Request rejected by the input safety rail")


def sanitize_output(text: str | None) -> str | None:
    """Output rail: redact any connection strings or credential-shaped substrings."""
    if text is None:
        return None
    return _SECRET_PATTERN.sub("[redacted]", text)
