# Architecture

InsightOps is organized around a small workflow engine that keeps the control
flow explicit.

## Core flow

1. The API receives a user request.
2. The engine builds a plan from the request.
3. The SQL step generates a query and tries to execute it through the
   read-only database helper.
4. The chart step turns tabular results into a PNG when the result set is
   chartable.
5. The review step turns the evidence into a narrative.
6. The critic scores the draft and can trigger a revision.
7. If the request implies a risky write, the engine pauses in an approval
   state before resuming.

## Safety boundary

- `read_db` only accepts `SELECT` / `WITH` statements.
- `write_db` is isolated behind the approval gate.
- The approval state is stored in the engine so the run can be resumed.
- Audit logging records every run and tool call, with file fallback when the
  database is not reachable.

## Local-first behavior

The implementation prefers local fallback paths for memory, audit logging, and
demo report data. That keeps the project usable in the workspace without
requiring a full cloud setup.

