"""Run the fixed local evaluation set against the deterministic engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.graph.build import InsightOpsEngine


def evaluate(
    task_set: list[dict[str, Any]], engine: InsightOpsEngine | None = None
) -> dict[str, Any]:
    runner = engine or InsightOpsEngine()
    results: list[dict[str, Any]] = []
    for task in task_set:
        result = runner.start(task["request"])
        expected = task.get("expected", {})
        checks = []
        if "region" in expected:
            checks.append(
                any(
                    row.get("region") == expected["region"]
                    for row in result.get("rows") or []
                )
            )
        if "month" in expected:
            checks.append(
                any(
                    str(row.get("month"))[:10] == expected["month"]
                    for row in result.get("rows") or []
                )
            )
        if expected.get("excludes_test_accounts"):
            checks.append("is_test = FALSE" in (result.get("sql") or ""))
        results.append(
            {
                "id": task["id"],
                "passed": all(checks) if checks else result["status"] == "done",
                "critic_score": result.get("critic_score"),
            }
        )
    passed = sum(item["passed"] for item in results)
    return {
        "total": len(results),
        "passed": passed,
        "pass_rate": passed / len(results) if results else 0.0,
        "results": results,
    }


def main() -> None:
    path = Path(__file__).with_name("task_set.json")
    report = evaluate(json.loads(path.read_text(encoding="utf-8")))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
