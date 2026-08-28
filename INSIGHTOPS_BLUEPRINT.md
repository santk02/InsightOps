# InsightOps — Build Blueprint

> A constrained multi-agent system that answers business questions from a
> database, checks its own work, remembers your preferences, and asks
> permission before doing anything irreversible.

**Design rule: constraints are the product.** Anyone can chain LLM calls.
The interesting engineering is what stops the agent doing something stupid —
permissions, retries, approval gates, loop limits, audit logs.

---

## 0. The One-Paragraph Pitch

Ops and analytics teams answer the same questions every week — "why did
refunds spike in the north region", "which accounts churned and what did
support say" — by hand-writing SQL, pasting results into a chart, and
summarising it in a doc. That is roughly two hours per recurring report.
InsightOps is a LangGraph agent that plans the steps, writes and runs the SQL
itself, draws the chart, pulls in supporting context, and produces the summary
in about ten minutes — with an audit log of every tool call, a human approval
gate on anything that writes, and a memory of how you like your reports.

---

## 1. What You Are Proving

| Dimension | How this project proves it |
|---|---|
| Product sense | Named user (ops analyst), named workflow, stated time saved |
| System design | Explicit state graph, not an opaque loop; why supervisor over swarm |
| Reliability | Retries, dead-letter queue, loop limits, approval gates, rollback |
| Evaluation | LLM-as-judge on a fixed task set + SQL correctness tests |
| Technical depth | You can explain the state graph, MCP tool scoping, memory extraction |
| Business value | ~2 hrs → ~10 min per report; ~60% token cost reduction from routing |

---

## 2. Architecture (Simple Version)

```
        User request
             │
             ▼
   ┌──────────────────────────────────┐
   │  SUPERVISOR NODE (LangGraph)     │
   │  reads state, decides next step  │
   └──┬────────┬────────┬─────────┬───┘
      │        │        │         │
      ▼        ▼        ▼         ▼
  ┌───────┐┌───────┐┌────────┐┌────────┐
  │ SQL   ││ Chart ││Research││ Code   │
  │ agent ││ agent ││ agent  ││ review │
  └───┬───┘└───┬───┘└───┬────┘└───┬────┘
      │        │        │         │
      └────────┴───┬────┴─────────┘
                   ▼
        ┌──────────────────────┐
        │  MCP TOOL REGISTRY   │  scoped permissions
        │  read_db  (safe)     │  ← auto-run
        │  run_chart(safe)     │  ← auto-run
        │  web_fetch(safe)     │  ← auto-run
        │  write_db (RISKY)    │  ← NEEDS APPROVAL
        │  send_mail(RISKY)    │  ← NEEDS APPROVAL
        └──────────┬───────────┘
                   │
        ┌──────────▼───────────┐
        │  APPROVAL GATE       │  interrupt() → human says yes/no
        └──────────┬───────────┘
                   ▼
        ┌──────────────────────┐
        │  CRITIC NODE         │  LLM-as-judge scores the draft
        │  score < 0.7 → retry │  max 2 revisions, then ship as-is
        └──────────┬───────────┘
                   ▼
              Final report
                   │
      ┌────────────┴────────────┐
      ▼                         ▼
  Mem0 (preferences)      Audit log (Postgres)
```

---

## 3. Why Each Piece Exists (interview answers)

**Why LangGraph rather than a plain while-loop?** Because a state graph is
inspectable. Every node transition is a checkpoint I can replay, pause and
resume. That is what makes the human-approval gate possible at all — the
graph literally suspends mid-execution and waits.

**Why a supervisor instead of agents talking to each other freely?** A swarm
is unpredictable and hard to debug. A supervisor gives one place where routing
decisions happen, one place to log them, and a hard iteration cap. Predictable
beats clever when you are accountable for the output.

**Why MCP for tools?** MCP standardises tool discovery, so the agent can list
what is available at runtime instead of me hardcoding a registry. It also
gives a clean place to attach permission scopes — each tool is tagged `safe`
or `risky`, and risky ones cannot execute without an interrupt.

**Why Mem0 rather than stuffing chat history into the prompt?** Replaying a
full transcript every turn is expensive and gets worse over time. Mem0 extracts
durable facts — "prefers weekly not monthly buckets", "always exclude test
accounts" — and injects only those. Cost stays flat as history grows, and the
user can inspect and delete what is stored, which matters for trust.

**Why a critic node?** Self-consistency is cheap insurance. A second LLM pass
scoring the draft against the original request catches obvious failures — the
answer ignored half the question, the chart doesn't match the numbers. Cap the
revisions at two so it cannot loop forever.

**Why cost-aware routing?** Most sub-tasks are easy. Classifying intent or
formatting a table does not need the largest model. Routing by task complexity
cut token spend around 60% with no measurable quality drop on my eval set.

---

## 4. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Orchestration | LangGraph | Explicit state graph, checkpoints, `interrupt()` |
| Tool protocol | MCP (Python SDK) | Standard tool discovery + a natural permission boundary |
| Model routing | LiteLLM | Complexity-based routing, retries, fallbacks, cost tracking |
| Models | Claude (`claude-sonnet-4-6`) for planning; a smaller/cheaper model for simple steps | The routing story needs at least two tiers |
| Memory | Mem0 | Fact extraction instead of transcript replay |
| Database | PostgreSQL 16 | The analytics data *and* the audit log |
| Queue | Redis | Event triggers, retries, dead-letter queue |
| Charts | matplotlib | Boring, reliable, no JS build step |
| Guardrails | NeMo Guardrails | Input/output rails on the tool boundary |
| Red-teaming | Promptfoo | Injection resilience test suite |
| Tracing | Langfuse + OpenTelemetry | Full multi-step trace tree |
| API | FastAPI | Same as your other repos — consistency is a signal |
| Containers | Docker Compose | One command |

---

## 5. Repository Structure

```
insightops/
├── README.md
├── ARCHITECTURE.md
├── FAILURE_MODES.md
├── EVALUATION.md
├── LICENSE
├── .env.example
├── requirements.txt
├── docker-compose.yml       # postgres + redis + langfuse
├── Dockerfile
│
├── .github/workflows/ci.yml
│
├── app/
│   ├── main.py              # FastAPI: POST /v1/run, POST /v1/approve
│   ├── config.py
│   ├── models.py
│   │
│   ├── graph/
│   │   ├── state.py         # the AgentState TypedDict — read this first
│   │   ├── supervisor.py    # routing node
│   │   ├── nodes.py         # sql / chart / research / review nodes
│   │   ├── critic.py        # LLM-as-judge + revision loop
│   │   ├── approval.py      # interrupt() gate for risky tools
│   │   └── build.py         # assembles and compiles the graph
│   │
│   ├── tools/
│   │   ├── server.py        # MCP server exposing the tools
│   │   ├── registry.py      # tool → {scope, risk} mapping
│   │   ├── db_tools.py      # read_db (safe), write_db (risky)
│   │   ├── chart_tools.py
│   │   └── web_tools.py
│   │
│   ├── memory/
│   │   └── store.py         # Mem0 wrapper + inspect/edit/clear API
│   │
│   ├── routing/
│   │   └── model_router.py  # complexity → model tier
│   │
│   ├── events/
│   │   ├── worker.py        # Redis consumer, idempotency, retries
│   │   └── dlq.py           # dead-letter handling
│   │
│   └── observability/
│       ├── tracing.py
│       └── audit.py         # every tool call → Postgres
│
├── evaluation/
│   ├── task_set.json        # 20 fixed requests + expected outcomes
│   ├── run_eval.py          # judge scores + SQL correctness
│   └── thresholds.json
│
├── redteam/
│   └── promptfoo.yaml       # injection + jailbreak cases
│
├── scripts/
│   ├── init_db.sql
│   └── seed_data.py         # synthetic sales/support dataset
│
├── tests/
└── docs/images/
```

---

## 6. The State Object

Everything flows through one typed dict. Keep it small — if you cannot
explain every field, the graph is too complicated.

```python
# app/graph/state.py
from typing import Annotated, Literal, TypedDict
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]   # conversation so far
    request: str                              # the original user ask
    plan: list[str]                           # steps the supervisor decided
    step_index: int                           # where we are in the plan
    sql: str | None                           # last generated SQL
    rows: list[dict] | None                   # query result
    chart_path: str | None
    draft: str | None                         # candidate answer
    critic_score: float | None
    revisions: int                            # hard cap at 2
    pending_tool: dict | None                 # risky call awaiting approval
    approved: bool | None
    memories: list[str]                       # injected from Mem0
    iterations: int                           # hard cap at 8 — loop guard
```

**Interview line:** "`iterations` and `revisions` are the two fields that stop
this being a runaway agent. Every graph needs a termination guarantee, and
mine is explicit rather than hoping the model decides to stop."

---

## 7. Data Model (audit log — this is the compliance story)

```sql
CREATE TABLE IF NOT EXISTS runs (
    run_id      VARCHAR(36) PRIMARY KEY,
    user_id     VARCHAR(255),
    request     TEXT,
    status      VARCHAR(20),        -- running | awaiting_approval | done | failed
    started_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at    TIMESTAMP,
    total_cost  FLOAT,
    total_ms    FLOAT
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id            SERIAL PRIMARY KEY,
    run_id        VARCHAR(36) REFERENCES runs(run_id),
    step_index    INTEGER,
    tool_name     VARCHAR(80),
    risk          VARCHAR(10),      -- safe | risky
    arguments     JSONB,
    result_summary TEXT,
    approved_by   VARCHAR(255),     -- null for safe tools
    status        VARCHAR(20),      -- ok | retried | failed | denied
    attempts      INTEGER DEFAULT 1,
    latency_ms    FLOAT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dead_letters (
    id          SERIAL PRIMARY KEY,
    run_id      VARCHAR(36),
    payload     JSONB,
    error       TEXT,
    attempts    INTEGER,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 8. Build Plan

### Phase 0 — Environment + seed data (1 day)

1. Standard scaffold: venv, folders, `.gitignore`, `.env.example`, pinned
   `requirements.txt`, `docker-compose.yml` with Postgres + Redis.
2. `scripts/seed_data.py` — generate a synthetic but realistic dataset:
   ~50k rows of orders, customers, regions, support tickets, refunds, over
   24 months, with a deliberate anomaly planted (a refund spike in one region
   in one month). You need a *known* answer to evaluate against.
3. FastAPI health endpoint + first passing test. Commit.

### Phase 1 — Tools as an MCP server (2–3 days)

**`tools/db_tools.py`**
- `read_db(sql: str) -> list[dict]` — **read-only connection role**, statement
  timeout, row limit of 1000, and a hard reject on anything that is not a
  SELECT. Do not rely on the prompt to prevent a DROP TABLE; rely on the
  database user's permissions.
- `write_db(sql: str)` — exists specifically so you have a genuinely risky
  tool to gate.
- `get_schema() -> str` — table and column names, injected into the SQL
  agent's prompt so it does not invent columns.

**`tools/chart_tools.py`** — `make_chart(rows, kind, x, y) -> path`, matplotlib,
saves a PNG.

**`tools/web_tools.py`** — `fetch_page(url) -> markdown` for supporting context.

**`tools/registry.py`** — the permission map:

```python
TOOLS = {
    "read_db":    {"risk": "safe",  "scope": "analytics_ro"},
    "get_schema": {"risk": "safe",  "scope": "analytics_ro"},
    "make_chart": {"risk": "safe",  "scope": "local_fs"},
    "fetch_page": {"risk": "safe",  "scope": "network_ro"},
    "write_db":   {"risk": "risky", "scope": "analytics_rw"},
    "send_email": {"risk": "risky", "scope": "external_send"},
}
```

**`tools/server.py`** — expose all of it over MCP.

**Test:** call each tool directly through the MCP client, with no agent
involved. Confirm `read_db` rejects a DELETE. That test is the security story.

### Phase 2 — The graph (3–4 days)

**Supervisor node:** given `request`, `plan` and `step_index`, decide the next
node. Return one of `sql | chart | research | review | critic | done`.
Increment `iterations`; if it exceeds 8, force `done` and mark the run
`failed` — the agent does not get to decide whether to stop.

**SQL node:** inject `get_schema()`, generate SQL, call `read_db`. On a
database error, feed the error back and retry once. After two failures, record
the failure in state and move on rather than looping.

**Chart node:** turn `rows` into a PNG. Skip if the result is a single number.

**Research node:** `fetch_page` for supporting external context. Optional per
run.

**Review node:** drafts the final summary from `rows`, `chart_path` and
`memories`.

**Critic node** (`critic.py`):

```python
CRITIC_PROMPT = """Score this draft answer against the original request, 0.0-1.0.

Check: (1) does it answer everything asked? (2) is every number traceable to
the query result? (3) is the chart consistent with the numbers?

Return JSON only: {"score": float, "issues": [str]}"""
```

If `score < 0.7` and `revisions < 2`, send `issues` back to the review node.
Otherwise ship and record the score. Always log the score even when it passes.

**`build.py`** — wire the nodes, compile with a checkpointer (Postgres or
SQLite) so runs can be suspended and resumed.

**Test:** run the report request end to end with approvals disabled. It should
find the planted refund anomaly.

### Phase 3 — Approval gate (2 days)

Before executing any tool with `risk == "risky"`, the graph calls LangGraph's
`interrupt()`, writes `pending_tool` into state, sets the run status to
`awaiting_approval`, and stops.

- `POST /v1/approve {run_id, approved: bool, approver: str}` resumes the graph
  from the checkpoint.
- Denial is not an error: the tool result becomes "denied by user" and the
  agent must continue without it.
- Every approval and denial is written to `tool_calls.approved_by`.

**Test:** ask for something that requires `write_db`. Confirm the run pauses,
that nothing was written, then approve and confirm it completes. Then run it
again and deny — confirm the database is unchanged and the run still finishes
gracefully.

**This is the single best demo moment in the project.** Show the pause.

### Phase 4 — Memory (2 days)

- `memory/store.py` wraps Mem0: `remember(user_id, text)`,
  `recall(user_id, query) -> list[str]`, `list_all`, `delete(memory_id)`,
  `clear(user_id)`.
- Inject recalled facts into the supervisor and review prompts.
- Expose `GET /v1/memories`, `DELETE /v1/memories/{id}`, `DELETE /v1/memories`.

**Test:** tell it "always exclude test accounts", run a report, then start a
fresh session and confirm the exclusion is applied without being repeated.
Then delete the memory and confirm the behaviour reverts. That
inspect-edit-clear loop is a user-trust feature, and interviewers notice it.

### Phase 5 — Events, retries, dead letters (2 days)

- `events/worker.py`: consume run requests from a Redis queue so reports can be
  triggered by a webhook or a schedule, not just a synchronous API call.
- Idempotency: hash the request payload; if the same key completed in the last
  hour, return the cached run instead of re-running.
- Retry with exponential backoff, max 3 attempts.
- After the final failure, push to `dead_letters` with the error and payload.
- `GET /v1/dlq` to inspect, `POST /v1/dlq/{id}/replay` to retry.

**Test:** kill Postgres mid-run. Confirm retries happen, then the job lands in
the DLQ, then replay it successfully after bringing the database back.

### Phase 6 — Cost routing + guardrails (2 days)

**`routing/model_router.py`** — classify each step as simple or complex, route
simple steps to the cheaper model tier through LiteLLM. Log the model used and
cost per step.

Then **measure it**: run the eval set with routing off and on. Record total
cost both ways and the judge score both ways. If quality dropped, say so —
"60% cheaper, 2 points lower on the judge score" is a more credible claim than
a free lunch.

**NeMo Guardrails** — input rail (reject obvious prompt injection and
off-scope requests) and output rail (no raw SQL errors or connection strings
in user-facing text).

**Promptfoo** (`redteam/promptfoo.yaml`) — cases that try to make the agent
run a DELETE, exfiltrate the schema, or skip the approval gate. Run in CI.

### Phase 7 — Eval + observability + ship (3 days)

- `evaluation/task_set.json`: 20 fixed requests with expected outcomes —
  for SQL tasks, the correct numeric answer; for summaries, a rubric.
- `run_eval.py`: SQL correctness (exact match on the number) + judge score for
  narrative quality + cost per run + approval-gate compliance rate.
- CI: lint → tests → seed a throwaway DB → run eval → fail below thresholds →
  run Promptfoo.
- Langfuse traces with a span per node, so the whole graph traversal is
  visible as a tree.
- README, ARCHITECTURE, FAILURE_MODES, EVALUATION, demo GIF showing the
  approval pause.

---

## 9. Known Failure Modes

| Failure | Trigger | Detection | Degradation |
|---|---|---|---|
| Invalid SQL | Model invents a column | Database error | Feed error back, retry once, then report failure honestly |
| Infinite planning loop | Ambiguous request | `iterations > 8` | Force stop, return partial results and what it was stuck on |
| Wrong-but-valid SQL | Subtly wrong join | Critic node + eval set | Show the SQL in the output so a human can check it |
| Approval bypass attempt | Prompt injection in data | Promptfoo suite | Gate is enforced in code, not the prompt — cannot be talked around |
| Stale memory | Preference changed | User inspects memory | Inspect/edit/clear API |
| Tool timeout | Slow query | Statement timeout | Retry, then DLQ |
| Cheap model too weak | Complex step misrouted | Judge score by tier | Fall back to the stronger model on low score |

**The one to say out loud:** "The approval gate is enforced in the graph, not
in the system prompt. Anything enforced only by a prompt can be talked out of
by a prompt."

---

## 10. Success Criteria

- [ ] Seeded database with a known planted anomaly
- [ ] All tools callable over MCP with scopes and risk tags
- [ ] `read_db` rejects non-SELECT statements at the database-permission level
- [ ] Graph completes a full report end to end
- [ ] Risky tool triggers a real pause; approve and deny paths both work
- [ ] Mem0 preferences persist across sessions and can be inspected and cleared
- [ ] Retries and dead-letter queue demonstrated by killing a dependency
- [ ] Cost routing measured with before/after numbers, including any quality cost
- [ ] Promptfoo red-team suite passing in CI
- [ ] Audit log shows every tool call, argument and approver
- [ ] Langfuse trace tree for a full run
- [ ] All four docs written, demo GIF shows the approval pause

---

## 11. Interview Prep

**Why multi-agent instead of one big prompt?**
"Separation of concerns and separation of *permissions*. The SQL node only
ever gets read access. Splitting them means a failure in one node is
recoverable and traceable, not a mystery inside one giant call."

**How do you stop it running away?**
"Two hard caps in state — 8 iterations and 2 revisions — plus a supervisor
that owns all routing. The agent does not get to decide whether to stop."

**How do you handle destructive actions?**
"Every tool is tagged safe or risky in the registry. Risky ones hit
`interrupt()`, the graph checkpoints and suspends, and it only resumes on an
explicit approve call that gets written to the audit log with the approver's
identity. Denial is a normal path, not an error."

**How do you know the answers are right?**
"Twenty fixed tasks with known numeric answers for the SQL path, an
LLM-as-judge rubric for the narrative, and both run in CI. The SQL is shown in
the output so a human can verify the reasoning, not just the number."

**What did the cost routing actually cost you?**
Give the honest trade-off from your measurements. A candidate who reports a
small quality dip is far more believable than one who reports none.
