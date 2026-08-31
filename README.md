# InsightOps

A constrained multi-agent analytics workflow that answers business questions
from a database, draws a chart, checks its own work, remembers your
preferences, and **pauses for human approval before doing anything
irreversible**.

> Design rule: constraints are the product. Anyone can chain LLM calls — the
> interesting engineering here is what stops the agent doing something
> stupid: permissions, retries, approval gates, loop limits, audit logs.
> See [`INSIGHTOPS_BLUEPRINT.md`](INSIGHTOPS_BLUEPRINT.md) for the full
> design rationale this repository implements.

---

## Table of Contents

- [Project Overview & Key Features](#project-overview--key-features)
- [Repository Architecture & Directory Structure](#repository-architecture--directory-structure)
- [Prerequisites & Environment Setup](#prerequisites--environment-setup)
- [Installation & Dependency Setup](#installation--dependency-setup)
- [Usage Instructions](#usage-instructions)
- [Environment Variables & Configuration](#environment-variables--configuration)
- [Evaluation & Red-Teaming](#evaluation--red-teaming)
- [Troubleshooting & Edge Cases](#troubleshooting--edge-cases)
- [Architecture Notes: Blueprint vs. This Codebase](#architecture-notes-blueprint-vs-this-codebase)

---

## Project Overview & Key Features

Ops and analytics teams answer the same questions every week — *"why did
refunds spike in the north region"*, *"which accounts churned and what did
support say"* — by hand-writing SQL, pasting results into a chart, and
summarizing it in a doc. InsightOps automates that loop: it plans the steps,
writes and runs the SQL itself, draws the chart, optionally pulls in
supporting web context, and produces a written summary — with an audit log
of every tool call, a human approval gate on anything that writes, and a
memory of how you like your reports.

| Feature | Where it lives |
|---|---|
| **Supervisor-routed pipeline** (sql → chart → research → review → critic) | `app/graph/supervisor.py`, `app/graph/build.py` |
| **Scoped, risk-tagged tools** (`read_db` safe, `write_db` risky, …) | `app/tools/registry.py`, `app/tools/*.py` |
| **SELECT-only enforcement at the code *and* database-role level** | `app/tools/db_tools.py`, `scripts/init_db.sql` |
| **Human approval gate** — risky tools pause the run until approved/denied | `app/graph/approval.py`, `POST /v1/approve` |
| **LLM-as-judge critic** with a bounded (max 2) revision loop | `app/graph/critic.py` |
| **Durable memory** — inspect / add / delete / clear a user's preferences | `app/memory/store.py`, `/v1/memories` |
| **Audit log** of every run and tool call, DB-backed with a file fallback | `app/observability/audit.py` |
| **Event queue + retries + dead-letter queue** | `app/events/worker.py`, `app/events/dlq.py`, `/v1/dlq` |
| **Cost-aware model routing** (simple vs. complex tiers) | `app/routing/model_router.py` |
| **Input/output safety rails** against prompt injection and secret leaks | `app/guardrails.py` |
| **Fixed evaluation set gated on thresholds** | `evaluation/` |
| **Red-team suite** exercising the live API, not a bare model | `redteam/promptfoo.yaml` |

**Guardrails that make this a *constrained* agent, not a runaway one:**
`iterations` (max 8) and `revisions` (max 2) are hard caps in state — the
agent never decides for itself whether to stop. Every risky tool call is
tagged in a registry, not inferred from a prompt, and enforced by an
`interrupt`-style pause in code.

---

## Repository Architecture & Directory Structure

```
insightops/
├── README.md                  # you are here
├── INSIGHTOPS_BLUEPRINT.md     # original design spec / interview prep
├── ARCHITECTURE.md             # how the engine's control flow works
├── FAILURE_MODES.md            # how each failure mode degrades
├── EVALUATION.md               # how to run/interpret the eval suite
├── LICENSE
├── .env.example                 # copy to .env and fill in
├── requirements.txt
├── docker-compose.yml           # postgres + redis + app + worker
├── Dockerfile
├── pytest.ini
│
├── .github/workflows/ci.yml     # lint → test → seed → eval, gated on thresholds
│
├── app/
│   ├── main.py                  # FastAPI app: /v1/run, /v1/approve, /v1/memories, /v1/dlq
│   ├── config.py                # typed Settings, loaded from .env
│   ├── models.py                # Pydantic request/response models
│   ├── guardrails.py            # input/output safety rails
│   │
│   ├── graph/
│   │   ├── state.py             # AgentState — the one typed dict everything flows through
│   │   ├── supervisor.py        # plan-building + routing decisions
│   │   ├── nodes.py             # sql / chart / research / review step implementations
│   │   ├── critic.py            # LLM-as-judge scoring + revision loop
│   │   ├── approval.py          # approval-gate helpers (registry lookups, payload shape)
│   │   └── build.py             # InsightOpsEngine — runs/resumes the whole pipeline
│   │
│   ├── tools/
│   │   ├── server.py            # MCP server exposing all tools
│   │   ├── registry.py          # tool → {risk, scope} permission map
│   │   ├── db_tools.py          # read_db (safe), write_db (risky), get_schema
│   │   ├── chart_tools.py       # matplotlib chart generation
│   │   └── web_tools.py         # fetch_page (safe), send_email (risky)
│   │
│   ├── memory/store.py          # remember / recall / list / delete / clear
│   ├── routing/model_router.py  # simple-vs-complex model tier selection
│   ├── events/
│   │   ├── worker.py            # Redis consumer, idempotency, retries
│   │   └── dlq.py                # dead-letter storage + replay
│   └── observability/
│       ├── tracing.py            # Langfuse/OTel span helper (no-op if disabled)
│       └── audit.py              # every run + tool call → Postgres (file fallback)
│
├── evaluation/
│   ├── task_set.json             # 20 fixed requests with expected outcomes
│   ├── run_eval.py               # scores the task set, exits non-zero below thresholds
│   └── thresholds.json           # sql_exact_match / judge_score_min / approval_compliance
│
├── redteam/promptfoo.yaml        # injection + approval-bypass cases against the live API
├── scripts/
│   ├── init_db.sql               # schema + audit tables + read-only/read-write DB roles
│   └── seed_data.py              # synthetic dataset with a planted refund anomaly
└── tests/                        # pytest suite
```

---

## Prerequisites & Environment Setup

- **Python 3.12** (the CI pipeline and Dockerfile both target this version)
- **Docker + Docker Compose** — the easiest way to get Postgres and Redis running
- *(Optional, for full functionality beyond the local-first fallbacks)*
  - An **Anthropic API key**, if you wire an LLM into the SQL/review/critic
    steps instead of the deterministic heuristics shipped here
  - A **Mem0 API key**, to swap the file-backed memory store for hosted Mem0
  - **Langfuse** credentials, to turn on real trace export

> **Local-first by design.** Every external dependency — the database, Mem0,
> Langfuse, LiteLLM's model calls — has a graceful local fallback (see
> [Architecture Notes](#architecture-notes-blueprint-vs-this-codebase)), so
> you can run the whole API and its test suite with **nothing but Python
> installed**. Docker/Postgres/Redis are needed for the full audit-log,
> DLQ-replay, and seeded-database experience.

---

## Installation & Dependency Setup

```bash
# 1. Clone and enter the repo
git clone <this-repo-url>
cd insightops

# 2. Create a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the environment template and fill in what you need
cp .env.example .env
```

### Run everything with Docker Compose (recommended)

```bash
docker compose up --build
```

This starts Postgres (with `scripts/init_db.sql` auto-applied), Redis, the
FastAPI app on `:8000`, and the Redis worker. Then seed the demo dataset:

```bash
docker compose exec app python scripts/seed_data.py
```

### Run without Docker (local-fallback mode)

```bash
uvicorn app.main:app --reload
```

With no `DATABASE_URL`/`REDIS_URL` reachable, `read_db`/`write_db` fall back
to demo data, memory falls back to a local JSON file, and audit logging
falls back to a local JSONL file — the API stays fully functional for
demoing the approval-gate and memory flows.

---

## Usage Instructions

### Health check

```bash
curl http://localhost:8000/health
# {"status": "ok", "env": "development"}
```

### Run a report

```bash
curl -X POST http://localhost:8000/v1/run \
  -H "Content-Type: application/json" \
  -d '{"request": "Why did refunds spike in the north region in June 2025?", "user_id": "alice"}'
```

```json
{
  "run_id": "b1f6...",
  "status": "done",
  "summary": "The refund analysis shows a clear spike in North around 2025-06-01. That bucket reached 850 refunds and $479,965.00 in refund value.",
  "sql": "SELECT reg.name AS region, ... ORDER BY total_refunds DESC, refund_count DESC",
  "rows": [ {"region": "North", "month": "2025-06-01", "refund_count": 850, "total_refunds": 479965.0}, ... ],
  "chart_path": "charts/3f8a1c9d2b41.png",
  "critic_score": 0.9,
  "approval_required": false,
  "revisions": 0,
  "iterations": 3
}
```

### The approval-pause demo (the best demo moment in the project)

A request that implies a write pauses instead of executing:

```bash
curl -X POST http://localhost:8000/v1/run \
  -H "Content-Type: application/json" \
  -d '{"request": "Write an annotation summarizing this report."}'
```

```json
{
  "run_id": "9a21...",
  "status": "awaiting_approval",
  "approval_required": true,
  "pending_tool": {
    "tool_name": "write_db",
    "arguments": {"sql": "INSERT INTO analytics.report_annotations ..."},
    "risk": "risky",
    "reason": "Potentially irreversible write action"
  }
}
```

Approve it (resumes and completes the run):

```bash
curl -X POST http://localhost:8000/v1/approve \
  -H "Content-Type: application/json" \
  -d '{"run_id": "9a21...", "approved": true, "approver": "alice@company.com"}'
```

Or deny it — the run still finishes gracefully, without the write:

```bash
curl -X POST http://localhost:8000/v1/approve \
  -H "Content-Type: application/json" \
  -d '{"run_id": "9a21...", "approved": false, "approver": "alice@company.com"}'
```

### Memory — inspect, add, delete, clear

```bash
# Teach it a standing preference
curl -X POST http://localhost:8000/v1/memories \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "text": "always exclude test accounts"}'

# Inspect what's remembered
curl "http://localhost:8000/v1/memories?user_id=alice"

# Delete one memory
curl -X DELETE http://localhost:8000/v1/memories/<memory_id>

# Clear everything for a user
curl -X DELETE "http://localhost:8000/v1/memories?user_id=alice"
```

Once stored, a future request like `"Summarize this month's orders"` will
silently apply the exclusion — the SQL node checks recalled memories even
when the request doesn't repeat the preference.

### Dead-letter queue

```bash
curl http://localhost:8000/v1/dlq                       # list failed jobs
curl -X POST http://localhost:8000/v1/dlq/1/replay       # retry one
```

### Running the event worker

```bash
python -m app.events.worker
```

### Running the MCP tool server directly

```bash
python -c "from app.tools.server import main; main()"
```

Useful for the Phase 1 security test: call each tool directly through an MCP
client with no agent involved, and confirm `read_db` rejects a `DELETE`.

---

## Environment Variables & Configuration

Copy `.env.example` to `.env` and adjust as needed. All settings have safe
local defaults (`app/config.py`), so an empty `.env` still runs.

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Full-privilege connection, used for audit logging | `postgresql://insightops:insightops@localhost:5432/insightops` |
| `DATABASE_RO_URL` | Read-only role — the *only* credential `read_db` uses | `...analytics_ro:analytics_ro_pass@...` |
| `DATABASE_RW_URL` | Read-write role — used only by the approval-gated `write_db` | `...analytics_rw:analytics_rw_pass@...` |
| `REDIS_URL` | Event queue / dead-letter worker backend | `redis://localhost:6379/0` |
| `ANTHROPIC_API_KEY` | Credential for LiteLLM-routed Claude calls | *(empty)* |
| `LITELLM_MODEL_COMPLEX` | "Complex" tier model id | `claude-sonnet-4-20250514` |
| `LITELLM_MODEL_SIMPLE` | "Simple" tier model id | `claude-3-5-haiku-20241022` |
| `ROUTING_ENABLED` | Master switch for cost-aware routing | `true` |
| `MEM0_API_KEY` / `MEM0_USER_ID` | Hosted Mem0 credentials (unset → local file store) | *(empty)* / `default` |
| `LANGFUSE_ENABLED` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | Tracing export | `false` / *(empty)* |
| `APP_ENV` | Deployment label surfaced on `/health` | `development` |
| `CHARTS_DIR` | Where generated chart PNGs are written | `charts` |
| `APPROVALS_ENABLED` | Master switch for the human-approval gate | `true` |
| `MAX_ITERATIONS` | Hard cap on plan-step iterations | `8` |
| `MAX_REVISIONS` | Hard cap on critic-triggered revisions | `2` |
| `CRITIC_THRESHOLD` | Minimum critic score to ship without another revision | `0.7` |

`INSIGHTOPS_DATA_DIR` (not in `.env.example`) overrides where the local
fallback stores (memory, audit log, dead-letter queue) write their files;
defaults to `~/.insightops/`.

---

## Evaluation & Red-Teaming

```bash
# Run the fixed 20-task evaluation set — exits non-zero if pass_rate or
# avg_critic_score falls below evaluation/thresholds.json
python -m evaluation.run_eval

# Run the red-team suite against a running API (start `uvicorn app.main:app` first)
npx promptfoo eval -c redteam/promptfoo.yaml
```

CI (`.github/workflows/ci.yml`) runs, in order: `ruff check` → `pytest` →
seed a throwaway Postgres instance → `evaluation/run_eval.py`, so a
regression in either code quality or report quality fails the build.

---

## Troubleshooting & Edge Cases

| Symptom | Likely cause | Fix |
|---|---|---|
| `read_db`/`write_db` calls raise a connection error | Postgres isn't running / `DATABASE_*_URL` is wrong | `docker compose up postgres`, or just keep going — the SQL node falls back to deterministic demo rows automatically |
| `/v1/run` returns generic `"total_rows"` data instead of the refund anomaly | Database hasn't been seeded | `python scripts/seed_data.py` (needs `DATABASE_URL` pointed at a real Postgres) |
| `pip install -r requirements.txt` fails with a dependency conflict | An unpinned/incompatible transitive version | The pinned versions in this repo are verified to resolve together (`httpx==0.27.2` specifically satisfies both `mcp` and `litellm`'s constraints) — if you've edited pins, re-check with `pip install --dry-run` |
| `POST /v1/approve` returns `404` | `run_id` doesn't match a currently-paused run | Approvals only work while the run is `awaiting_approval`; a completed or denied run can't be re-approved. Re-run `/v1/run` if you need a fresh pause |
| A request is rejected with `400` before it even starts | The input safety rail caught injection-style phrasing (e.g. "ignore previous instructions", "bypass approval") | This is by design — see `app/guardrails.py`. Rephrase the request |
| `make_chart` raises `"Cannot chart empty result set"` | The SQL step returned zero rows | Expected behavior — check the generated `sql` in the response for the actual query run |
| Charts aren't appearing on disk in Docker | `charts/` isn't mounted | `docker-compose.yml` mounts `./charts:/app/charts` for the `app` service already — confirm you're checking the host-side `./charts/` directory |
| The event worker never processes anything | Redis isn't reachable, or nothing has been enqueued via `QueueWorker.enqueue()` | The synchronous `/v1/run` path bypasses the queue entirely — the worker is only exercised when you explicitly enqueue jobs |
| `promptfoo eval` can't reach the provider | The API isn't running, or is on a different host/port | Start `uvicorn app.main:app --reload` first; update the provider `id` in `redteam/promptfoo.yaml` if you're not on `localhost:8000` |

---

## Architecture Notes: Blueprint vs. This Codebase

`INSIGHTOPS_BLUEPRINT.md` specifies a **LangGraph `StateGraph`** compiled
with a Postgres/SQLite checkpointer, live **Mem0**, live **Langfuse**
tracing, an **LLM-as-judge** critic backed by a real model call, and
**NeMo Guardrails** input/output rails. This codebase implements the same
external *contract* — the same API shape, the same approval-pause/resume
semantics, the same audit trail, the same critic-driven revision loop — with
dependency-free, deterministic implementations wherever a hosted service or
a live LLM call would otherwise be required:

| Blueprint piece | This codebase | Why |
|---|---|---|
| LangGraph `StateGraph` + `interrupt()` + checkpointer | `InsightOpsEngine` (`app/graph/build.py`): a single-threaded, dict-based state machine with an in-memory `_pending_runs` map standing in for the checkpointer | Runs and is fully testable with zero external services; the node functions (`app/graph/nodes.py`) are already shaped like graph nodes and are the natural place to wire in a real `StateGraph` later |
| LLM-generated SQL, injected with `get_schema()` | Keyword-routed SQL templates (`build_sql_for_request`) | Deterministic and instantly testable without an API key; `get_schema()` is already implemented and ready to inject into a prompt |
| LLM-as-judge critic | Rule-based `score_draft()` scoring the same rubric described in `CRITIC_PROMPT` | Same scoring contract (0.0–1.0 + issues list), no per-run LLM cost during development |
| Mem0 | File-backed `MemoryStore` (`app/memory/store.py`) with the exact same `remember/recall/list_all/delete/clear` API | Works with zero credentials; swap the implementation, not the callers |
| Langfuse + OpenTelemetry | No-op `trace_span()` context manager | Safe to leave wired in; becomes real tracing the moment `LANGFUSE_ENABLED=true` and the SDK call is added inside it |
| LiteLLM cost routing | `classify_complexity()` + two configured model tiers, selected without calling a model | Same routing *decision* is made and loggable; the actual model dispatch is one line away once `ANTHROPIC_API_KEY` is used |

**What's already fully real, not a stand-in:** the SELECT-only enforcement
(code regex *and* a genuinely-scoped Postgres role), the approval-pause
API contract, the audit log (Postgres-backed with file fallback), the
dead-letter queue and idempotent Redis worker, the input/output guardrail
regexes, and the eval-gate/CI wiring.

**If you're extending this toward the full blueprint**, the seams are:
`app/graph/nodes.py` for LLM-backed SQL/review generation, `app/graph/critic.py`
for a real judge call, `app/memory/store.py` for a Mem0-backed implementation
behind the same interface, and `app/observability/tracing.py` for Langfuse
export.
