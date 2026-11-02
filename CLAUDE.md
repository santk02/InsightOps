# InsightOps

Constrained multi-agent analytics service: takes a natural-language business question, writes and runs SQL against Postgres, optionally charts it, has a critic score the draft, and **pauses for human approval before any risky (write/send) tool runs**. Spec: `INSIGHTOPS_BLUEPRINT.md`. Human-facing docs: `README.md`, `ARCHITECTURE.md`, `FAILURE_MODES.md`, `EVALUATION.md`.

## Tech stack

Python 3.12 · FastAPI + Uvicorn · Pydantic v2 / pydantic-settings · psycopg 3 · Redis · matplotlib · httpx · MCP (`mcp.server.fastmcp`) · pytest · ruff · Docker Compose (Postgres 16 + Redis 7). Dependencies are pinned in `requirements.txt`.

## Commands

Run from the repo root (imports use the `app.` package path, so cwd matters).

```bash
pip install -r requirements.txt            # install (use a Python 3.12 venv)
cp .env.example .env                       # config; every setting has a local default

uvicorn app.main:app --reload              # run the API on :8000
docker compose up --build                  # postgres + redis + app + worker
docker compose exec app python scripts/seed_data.py   # seed the demo dataset (planted North/June 2025 refund spike)
python -m app.events.worker                # Redis queue worker

pytest -q                                  # all tests (no DB/Redis/network needed)
pytest tests/test_engine.py -q             # one file
ruff check .                               # lint (no config file; ruff defaults)
python -m evaluation.run_eval              # 20-task eval; exits 1 if below evaluation/thresholds.json
```

Run the eval with `-m` from the repo root. `python evaluation/run_eval.py` fails with `ModuleNotFoundError: app`.

Lint with the **pinned** ruff (`ruff==0.8.4` in `requirements.txt`; use `python -m ruff check .` if a newer global `ruff` shadows it). Newer ruff versions enable extra default rules (e.g. `BLE001`, `UP035`) that the repo does not follow and CI does not enforce; don't "fix" those.

CI (`.github/workflows/ci.yml`) runs: `ruff check .` → `pytest -q` → `psql ... -f scripts/init_db.sql` + `scripts/seed_data.py` → `python -m evaluation.run_eval`. Make all four pass before pushing. The red-team suite (`npx promptfoo eval -c redteam/promptfoo.yaml`) needs a running API and is not in CI.

## Architecture (read before changing the engine)

- `app/main.py` — FastAPI routes; builds module-level singletons (`get_engine()`, `get_memory_store()`, `get_dead_letter_store()`) at import time.
- `app/graph/build.py` — `InsightOpsEngine`: a **deterministic, synchronous state machine, not a LangGraph `StateGraph`**. Pipeline: recall memories → plan → (risky? pause) → sql → chart → research → review → critic/revise loop. Paused runs live in the in-memory `_pending_runs` dict. `approve()` re-runs the whole pipeline rather than resuming from a checkpoint.
- `app/graph/nodes.py` — step implementations (`run_sql_step`, `run_chart_step`, ...). SQL is keyword-templated, not LLM-generated.
- `app/graph/{supervisor,critic,approval,state}.py` — plan building, rule-based critic, approval helpers, `AgentState` TypedDict. `supervisor.route_next` is currently unused.
- `app/tools/` — `registry.py` is the single risk/scope map (`safe` vs `risky`); `db_tools.py` has `read_db` (read-only role) and `write_db` (rw role); `server.py` exposes them over MCP.
- `app/memory/store.py`, `app/events/dlq.py`, `app/observability/audit.py` — file-backed (`~/.insightops/`, override with `INSIGHTOPS_DATA_DIR`) stand-ins for Mem0 / the `dead_letters` table / Postgres audit, with the same interfaces.
- `app/guardrails.py` — regex input/output rails applied in `main.py`.
- `app/config.py` — `Settings` via `get_settings()` (lru-cached; env is read once per process).

## Safety invariants — do not weaken

- `read_db` must stay SELECT/WITH-only: keep both the regex validator **and** the `DATABASE_RO_URL` read-only role. Never rely on a prompt.
- Risky tools (`write_db`, `send_email`) must go through the approval gate. Enforce it in code, not in prompt text.
- Pass user/LLM-derived values to `write_db` via `params=(...)`; never interpolate them into the SQL string.
- Keep the hard caps: `max_iterations` (8) and `max_revisions` (2) in `config.py`.
- Every tool call is recorded via `audit.log_tool_call` (including approver and denials).

## Gotchas

- **Silent fallbacks mask failures.** `run_sql_step`, `execute_risky_write`, `get_schema`, and the audit logger swallow DB errors and fall back to demo data or a JSONL file. A green test or eval run does **not** prove Postgres works. Check `source` in tool results (`database` / `database-retry` / `demo`).
- Tests use `DummyAudit` and a `tmp_path` `MemoryStore`; follow that pattern so tests never touch `~/.insightops/` or a database.
- `.env` is gitignored; edit `.env.example` when adding a setting, and add the field to `Settings` with a default.
- `charts/` and `*.png` are gitignored output.

## Code style

Match the existing code; there is no formatter config.

- Every module starts with `from __future__ import annotations` (after the module docstring) and uses full type hints with modern syntax (`list[str]`, `str | None`).
- Module docstring explains the module's role and any blueprint deviation. Public classes and functions get a one-line docstring.
- **Single-line inline `#` comments** on non-obvious lines and logic blocks, explaining *why*. This was an explicit project requirement; keep it on new code.
- Naming: `snake_case` functions/variables/modules, `PascalCase` classes, `UPPER_SNAKE` constants, `_leading_underscore` for module-private helpers and singletons (`_ENGINE`, `_schema_cache`).
- Singletons are exposed through `get_*()` factory functions; config through `get_settings()`.
- Models: Pydantic `BaseModel` for API shapes (`app/models.py`), `@dataclass` for internal services, `TypedDict` for graph state.
- HTTP errors: `HTTPException` with a specific status (400 guardrail rejection, 404 unknown run/DLQ item), raised `from exc`.
- Imports ordered stdlib → third-party → `app.*`. `ruff check .` must pass clean; remove unused imports and variables rather than suppressing.

## Tests

`tests/` uses pytest (`asyncio_mode = auto`, files `test_*.py`). New behavior needs a test that runs with no external services. For anything touching the approval flow, assert both the paused state (`status == "awaiting_approval"`, `pending_tool` set) and the resumed state.
