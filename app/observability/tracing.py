"""Lightweight tracing helpers.

The production blueprint mentions Langfuse and OpenTelemetry. This module keeps
the interface small and safe: if tracing is not configured, it simply acts as a
no-op context manager so the rest of the application does not have to care.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from app.config import get_settings


@dataclass
class TraceSpan:
    name: str
    attributes: dict[str, Any]


@contextmanager
def trace_span(name: str, **attributes: Any) -> Iterator[TraceSpan]:
    settings = get_settings()
    span = TraceSpan(name=name, attributes=attributes)
    if not settings.langfuse_enabled:
        yield span
        return
    # The real Langfuse/OpenTelemetry wiring can be attached here when the
    # deployment has credentials. In local mode this remains a clean no-op.
    yield span

