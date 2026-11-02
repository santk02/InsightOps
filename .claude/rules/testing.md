---
paths:
  - "tests/**"
  - "evaluation/**"
---

# Testing rules

## Running

- `pytest -q` from the repo root. Config is in `pytest.ini` (`testpaths = tests`, `asyncio_mode = auto`).
- The eval runs as `python -m evaluation.run_eval` (run from the repo root with `-m`). It exits 1 when `pass_rate` or `avg_critic_score` falls below `evaluation/thresholds.json`.

## Isolation: tests must need no external services

- Construct the engine with fakes instead of the singletons:
  `InsightOpsEngine(audit=DummyAudit(), memory=MemoryStore(tmp_path / "memories.json"))`.
- Give `MemoryStore`, `DeadLetterStore` and `AuditLogger` an explicit path under pytest's `tmp_path` so tests never write to `~/.insightops/`.
- Don't open network connections; `fetch_page` and the DB tools must not be hit for real in unit tests. The DB layer falls back to demo rows when Postgres is unreachable; don't depend on that accidentally. Assert on `source` if the distinction matters.
- `tests/test_health.py` imports `app.main`, which builds singletons at import time. Keep `app.main` importable with no services running.

## What to test

- Safety changes need a direct test of the guard itself, not only an end-to-end run. For example, `_validate_select_only` rejects `DELETE`, and `write_db` rejects `SELECT`.
- Approval-flow changes must cover all three paths: paused (`awaiting_approval`, `pending_tool` set, nothing written), approved (`done`, `approved is True`), and denied (`done`, run still completes).
- Memory changes cover remember → recall → delete → recall returns `[]`.
- For an engine-output bug, add or extend a task in `evaluation/task_set.json` with an `expected` block, as well as a unit test.

## Style

- Plain `assert`, `pytest.raises` for errors, one behavior per test, and a one-line docstring saying what the test proves.
- Name tests `test_<subject>_<expected_behavior>`, e.g. `test_write_request_pauses_for_approval`.
