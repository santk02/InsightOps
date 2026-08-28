"""Input and output safety rails for the public API boundary."""

from __future__ import annotations

import re

_INJECTION_PATTERNS = (
    r"ignore\s+(?:all\s+)?previous instructions",
    r"bypass\s+(?:the\s+)?approval",
    r"skip\s+(?:the\s+)?approval",
    r"reveal\s+(?:the\s+)?system prompt",
)
_SECRET_PATTERN = re.compile(
    r"(?:postgres(?:ql)?://|(?:password|api[_ -]?key)\s*[:=])[^\s]+", re.IGNORECASE
)


def validate_request(request: str) -> None:
    lowered = request.lower()
    if any(re.search(pattern, lowered) for pattern in _INJECTION_PATTERNS):
        raise ValueError("Request rejected by the input safety rail")


def sanitize_output(text: str | None) -> str | None:
    if text is None:
        return None
    return _SECRET_PATTERN.sub("[redacted]", text)
