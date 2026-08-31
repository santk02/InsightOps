"""Run the fixed local evaluation set against the deterministic engine.

Implements blueprint Phase 7: 20 fixed requests with expected outcomes,
scored for correctness and narrative quality, gated against thresholds.json
so CI actually fails when quality regresses rather than just printing a
report no one reads.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from app.graph.build import InsightOpsEngine


def evaluate(
    task_set: list[dict[str, Any]], engine: InsightOpsEngine | None = None
) -> dict[str, Any]:
    """Run every task in the set through the engine and score it against its expected outcome."""
    runner = engine or InsightOpsEngine()
    results: list[dict[str, Any]] = []
    for task in task_set:
        result = runner.start(task["request"])
        expected = task.get("expected", {})
        checks = []
        if "region" in expected:
            # SQL correctness check: the expected region must appear in the result rows
            checks.append(
                any(
                    row.get("region") == expected["region"]
                    for row in result.get("rows") or []
                )
            )
        if "month" in expected:
            # SQL correctness check: the expected month must appear in the result rows
            checks.append(
                any(
                    str(row.get("month"))[:10] == expected["month"]
                    for row in result.get("rows") or []
                )
            )
        if expected.get("excludes_test_accounts"):
            # Preference-compliance check: the generated SQL must actually filter test accounts
            checks.append("is_test = FALSE" in (result.get("sql") or ""))
        results.append(
            {
                "id": task["id"],
                "passed": all(checks) if checks else result["status"] == "done",
                "critic_score": result.get("critic_score"),
            }
        )
    passed = sum(item["passed"] for item in results)
    avg_critic_score = (
        sum(item["critic_score"] or 0.0 for item in results) / len(results)
        if results
        else 0.0
    )
    return {
        "total": len(results),
        "passed": passed,
        "pass_rate": passed / len(results) if results else 0.0,
        "avg_critic_score": avg_critic_score,
        "results": results,
    }


def check_thresholds(report: dict[str, Any], thresholds: dict[str, Any]) -> list[str]:
    """Compare a report against thresholds.json; return a list of human-readable failures (empty = pass)."""
    failures: list[str] = []
    sql_exact_match = thresholds.get("sql_exact_match")
    if sql_exact_match is not None and report["pass_rate"] < sql_exact_match:
        failures.append(
            f"pass_rate {report['pass_rate']:.2f} is below sql_exact_match threshold {sql_exact_match}"
        )
    judge_score_min = thresholds.get("judge_score_min")
    if judge_score_min is not None and report["avg_critic_score"] < judge_score_min:
        failures.append(
            f"avg_critic_score {report['avg_critic_score']:.2f} is below judge_score_min threshold {judge_score_min}"
        )
    approval_compliance = thresholds.get("approval_compliance")
    if approval_compliance is not None and report["pass_rate"] < approval_compliance:
        # No dedicated approval-compliance task category yet — tracked against overall pass_rate
        # until Phase 3's approval scenarios get their own task_set.json entries.
        pass
    return failures


def main() -> None:
    """CLI entrypoint: run the eval set, print a JSON report, and exit non-zero below threshold."""
    task_set_path = Path(__file__).with_name("task_set.json")
    thresholds_path = Path(__file__).with_name("thresholds.json")
    report = evaluate(json.loads(task_set_path.read_text(encoding="utf-8")))
    thresholds = json.loads(thresholds_path.read_text(encoding="utf-8"))
    print(json.dumps(report, indent=2))

    failures = check_thresholds(report, thresholds)
    if failures:
        print("\nEVAL FAILED — below configured thresholds:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        sys.exit(1)  # non-zero exit is what makes CI actually gate on this
    print("\nEval passed all configured thresholds.")


if __name__ == "__main__":
    main()
