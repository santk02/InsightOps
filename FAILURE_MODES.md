# Failure Modes

## Invalid SQL

If query execution fails, the engine falls back to a deterministic demo result
set so the workflow can still complete in local mode.

## Approval pause

Risky actions stop in an awaiting-approval state instead of continuing
silently.

## Database unavailable

Audit logging, memory, and the report engine all have local fallback behavior.
The app remains usable even when Postgres is offline.

## Infinite loops

The workflow keeps a small fixed plan and does not recurse indefinitely.

