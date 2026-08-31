"""Draft scoring for the report workflow.

Implements the blueprint's critic node (section 3, "Why a critic node?" and
section 8 Phase 2): a second pass that scores the draft against the original
request and flags concrete issues, so a wrong-but-confident answer doesn't
ship unexamined. This is a deterministic, rule-based stand-in for the
LLM-as-judge call described in the blueprint — the same scoring contract
(`CRITIC_PROMPT`'s JSON shape) applies if it's swapped for a real model call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.config import get_settings


@dataclass
class CriticResult:
    score: float  # 0.0-1.0 confidence that the draft fully and correctly answers the request
    issues: list[str]  # concrete, human-readable gaps found in the draft


def _find_numbers(text: str) -> list[str]:
    """Extract number-looking substrings — used as a proxy for "cites concrete evidence"."""
    return re.findall(r"\b\d+(?:\.\d+)?\b", text)


def score_draft(request: str, draft: str, rows: list[dict[str, Any]] | None, chart_path: str | None) -> CriticResult:
    """Score a draft 0.0-1.0 against the request, and list any issues found along the way."""
    issues: list[str] = []
    score = 0.45  # baseline — a draft with no supporting evidence starts below the threshold
    request_l = request.lower()
    draft_l = draft.lower()

    if rows:
        score += 0.2  # reward: query actually returned evidence
    else:
        issues.append("No row data was included in the draft.")

    if "refund" in request_l and ("refund" in draft_l or "north" in draft_l):
        score += 0.15  # reward: refund questions are addressed on-topic
    elif "refund" in request_l:
        issues.append("Refund request was not clearly addressed.")

    if "chart" in request_l or "graph" in request_l or "plot" in request_l or "trend" in request_l:
        if chart_path:
            score += 0.15  # reward: a chart was requested and one was produced
        else:
            issues.append("A chart was requested but no chart was produced.")

    if _find_numbers(draft):
        score += 0.1  # reward: the draft cites concrete numeric evidence
    else:
        issues.append("The draft did not surface any numeric evidence.")

    score = min(score, 0.99)  # never claim full (1.0) certainty
    return CriticResult(score=score, issues=issues)


def should_revise(score: float, revisions: int) -> bool:
    """True if the draft scored below threshold and the revision budget isn't exhausted yet."""
    settings = get_settings()
    return score < settings.critic_threshold and revisions < settings.max_revisions
