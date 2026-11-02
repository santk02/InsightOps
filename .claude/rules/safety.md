---
paths:
  - "app/tools/**"
  - "app/graph/**"
  - "app/guardrails.py"
  - "scripts/init_db.sql"
---

# Safety boundary rules

These modules carry the project's core claim: the agent cannot do anything irreversible without a human saying yes. Treat any change here as security-sensitive.

## SQL access

- `read_db` keeps **two** independent guards. Never remove either one:
  1. `_validate_select_only()`: must start with `SELECT`/`WITH`, and no write/DDL keyword (`INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE`) may appear anywhere in the statement.
  2. Connect only through `settings.database_ro_url` (the `analytics_ro` role, which `scripts/init_db.sql` grants `SELECT` only).
- `read_db` must keep the `statement_timeout` and the 1000-row `_wrap_with_limit` cap.
- `write_db` connects only through `settings.database_rw_url`. Pass every value derived from a user or the LLM as `params=(...)`; never build SQL with f-strings, `%` formatting, or manual quote-escaping.
- If you add tables, also add the grants for both roles in `init_db.sql`. Don't give `analytics_ro` anything beyond `SELECT`.

## Tool registry and approval gate

- Every tool must have an entry in `app/tools/registry.py` `TOOLS` with a `risk` (`safe` | `risky`) and a `scope`. An unregistered tool raises `ValueError` by design.
- Anything with an external or irreversible side effect is `risky`. Don't downgrade a tool to `safe` to make a test or demo pass.
- A risky tool must never execute on the first pass of a run while `approvals_enabled` is true. The engine must set `status = "awaiting_approval"`, store `pending_tool`, park the run in `_pending_runs`, and return.
- Denial is a normal outcome, not an error. The run must still finish with `status = "done"` and log `status="denied"` with the approver's identity.
- Enforce the gate in code. Never move the check into a prompt string.

## Audit

- Every tool execution, pause, approval and denial goes through `audit.log_tool_call(...)` with `risk`, `arguments` and `approved_by` (None for safe tools).
- Audit failures must never break a run (keep the file fallback), but don't silently drop the event either.

## Loop limits

- Keep `max_iterations` (8) and `max_revisions` (2) as the termination guarantee. Any new loop in the engine must be bounded by one of them.

## Guardrails

- `validate_request` (input) and `sanitize_output` (output) run in `app/main.py`. A new endpoint that accepts free text or returns a summary must call them too.
- When a new red-team case is needed, add it to `redteam/promptfoo.yaml` alongside the rail change.
