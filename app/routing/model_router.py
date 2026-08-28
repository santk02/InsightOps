"""Heuristic model router.

The blueprint uses LiteLLM routing. This keeps the same decision boundary but
routes locally using keywords so the project works even without API keys.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.config import get_settings

Complexity = Literal["simple", "complex"]


_COMPLEX_HINTS = {
    "analyze",
    "compare",
    "correlate",
    "trend",
    "anomaly",
    "why",
    "churn",
    "refund",
    "support",
    "multi",
    "revenue",
    "forecast",
}


def classify_complexity(request: str) -> Complexity:
    tokens = {token for token in re.split(r"[^a-z0-9]+", request.lower()) if token}
    if len(tokens & _COMPLEX_HINTS) >= 1 or len(request) > 140:
        return "complex"
    return "simple"


def select_model(request: str, step_name: str | None = None) -> str:
    settings = get_settings()
    complexity = classify_complexity(request)
    if settings.routing_enabled and complexity == "simple":
        return settings.litellm_model_simple
    return settings.litellm_model_complex


@dataclass
class ModelRoutingDecision:
    model: str
    complexity: Complexity


def route_request(request: str, step_name: str | None = None) -> ModelRoutingDecision:
    return ModelRoutingDecision(model=select_model(request, step_name=step_name), complexity=classify_complexity(request))

