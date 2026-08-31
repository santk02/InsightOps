# Evaluation

The blueprint describes a fixed task set, SQL correctness checks, and
judge-based summary scoring, gated in CI so a regression fails the build.
`evaluation/run_eval.py` implements exactly that against the local engine.

## Running it

```bash
python -m evaluation.run_eval
```

This runs all 20 tasks in `evaluation/task_set.json`, prints a JSON report
(`pass_rate`, `avg_critic_score`, per-task pass/fail), and **exits non-zero**
if either falls below the numbers in `evaluation/thresholds.json`. CI runs
this exact command after seeding a throwaway database, so a quality
regression fails the pipeline the same way a broken test would.

## Other local checks

1. `pytest` — unit/integration tests
2. `POST /v1/run` for a refund anomaly question — should surface the North/June 2025 spike
3. `POST /v1/run` for a write request, then `POST /v1/approve` — the approval-pause demo
4. `npx promptfoo eval -c redteam/promptfoo.yaml` (with the API running) — injection/approval-bypass red-team suite

