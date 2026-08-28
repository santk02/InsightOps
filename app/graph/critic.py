"""Draft scoring for the report workflow."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.config import get_settings


@dataclass
class CriticResult:
    score: float
    issues: list[str]


def _find_numbers(text: str) -> list[str]:
    return re.findall(r"\b\d+(?:\.\d+)?\b", text)


def score_draft(request: str, draft: str, rows: list[dict[str, Any]] | None, chart_path: str | None) -> CriticResult:
    issues: list[str] = []
    score = 0.45
    request_l = request.lower()
    draft_l = draft.lower()

    if rows:
        score += 0.2
    else:
        issues.append("No row data was included in the draft.")

    if "refund" in request_l and ("refund" in draft_l or "north" in draft_l):
        score += 0.15
    elif "refund" in request_l:
        issues.append("Refund request was not clearly addressed.")

    if "chart" in request_l or "graph" in request_l or "plot" in request_l or "trend" in request_l:
        if chart_path:
            score += 0.15
        else:
            issues.append("A chart was requested but no chart was produced.")

    if _find_numbers(draft):
        score += 0.1
    else:
        issues.append("The draft did not surface any numeric evidence.")

    score = min(score, 0.99)
    return CriticResult(score=score, issues=issues)


def should_revise(score: float, revisions: int) -> bool:
    settings = get_settings()
    return score < settings.critic_threshold and revisions < settings.max_revisions

