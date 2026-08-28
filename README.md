# InsightOps

InsightOps is a constrained multi-agent analytics workflow for answering
business questions from a database, generating charts, retaining lightweight
preferences, and pausing for approval before risky actions.

This repository currently ships a local-first MVP of the blueprint:

- FastAPI API with `/health`, `/v1/run`, `/v1/approve`, memory endpoints, and DLQ inspection
- Read-only and read-write database helpers
- A deterministic workflow engine that mirrors the supervisor / SQL / chart / review / critic structure
- File-backed memory and audit fallbacks when external services are unavailable
- Redis worker and MCP tool server entrypoints

## Quick start

1. Create a `.env` file from `.env.example`.
2. Start the containers with `docker compose up --build`.
3. Seed the database with `python scripts/seed_data.py` if you want the demo dataset.
4. Run a report with `POST /v1/run`.

## What is implemented

- Safe `read_db` SQL validation
- Schema introspection with a local fallback
- Chart creation with matplotlib
- Memory inspect / clear / delete APIs
- Audit logging with Postgres-or-file fallback
- Approval gating for risky write actions

## What remains external

- Live Mem0, Langfuse, LiteLLM, and full LangGraph checkpointing integrations can be enabled on top of this scaffold.
- The Redis worker and MCP server are wired as entrypoints, but they degrade gracefully when the backing service is absent.

