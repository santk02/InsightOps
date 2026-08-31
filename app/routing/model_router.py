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


# Keywords that signal a step needs real reasoning (analysis, comparison, anomaly detection)
# rather than simple lookup/formatting — these route to the more capable/expensive model tier
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
    """Classify a request as "simple" or "complex" from keyword hints and length."""
    tokens = {token for token in re.split(r"[^a-z0-9]+", request.lower()) if token}
    if len(tokens & _COMPLEX_HINTS) >= 1 or len(request) > 140:
        return "complex"  # any complexity keyword, or a long/detailed request, routes to the strong tier
    return "simple"


def select_model(request: str, step_name: str | None = None) -> str:
    """Pick the LiteLLM model id to use for this request, honoring the routing_enabled switch."""
    settings = get_settings()
    complexity = classify_complexity(request)
    if settings.routing_enabled and complexity == "simple":
        return settings.litellm_model_simple  # cheap tier — cuts token spend on easy steps
    return settings.litellm_model_complex  # default / complex tier


@dataclass
class ModelRoutingDecision:
    model: str  # the selected model id
    complexity: Complexity  # the classification that produced it, for logging/cost analysis


def route_request(request: str, step_name: str | None = None) -> ModelRoutingDecision:
    """Return both the routing decision and the classification behind it, for audit/cost logging."""
    return ModelRoutingDecision(model=select_model(request, step_name=step_name), complexity=classify_complexity(request))
