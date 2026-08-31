"""FastAPI application entry point.

Exposes the blueprint's HTTP surface: run/approve for the report workflow,
memory inspect/edit/clear, and dead-letter-queue inspection/replay.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.events.dlq import get_dead_letter_store
from app.graph.build import get_engine
from app.guardrails import sanitize_output, validate_request
from app.memory.store import get_memory_store
from app.models import (
    ApproveRequest,
    DeadLetterRecord,
    MemoryCreateRequest,
    MemoryRecord,
    RunRequest,
    RunResponse,
)

# Load configuration and construct the process-wide singletons once at import time
settings = get_settings()
engine = get_engine()
memory_store = get_memory_store()
dlq_store = get_dead_letter_store()

app = FastAPI(
    title="InsightOps",
    description="Constrained multi-agent analytics system",
    version="0.1.0",
)

# Permissive CORS for local/demo use — tighten this before any real deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe — also reports which environment this instance is running in."""
    return {"status": "ok", "env": settings.app_env}


@app.post("/v1/run", response_model=RunResponse)
def run_report(payload: RunRequest) -> RunResponse:
    """Kick off a new report run; may return `awaiting_approval` if a risky tool is implied."""
    try:
        validate_request(payload.request)  # input safety rail — rejects injection/bypass attempts
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = engine.start(payload.request, user_id=payload.user_id)
    result["summary"] = sanitize_output(result.get("summary"))  # output rail — scrub secrets
    return RunResponse(**result)


@app.post("/v1/approve", response_model=RunResponse)
def approve_run(payload: ApproveRequest) -> RunResponse:
    """Resume a paused run with a human approve/deny decision."""
    try:
        result = engine.approve(payload.run_id, payload.approved, payload.approver)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RunResponse(**result)


@app.get("/v1/memories", response_model=list[MemoryRecord])
def list_memories(user_id: str = "default") -> list[MemoryRecord]:
    """List everything remembered for a given user — the "inspect" half of inspect/edit/clear."""
    return [
        MemoryRecord.model_validate(item) for item in memory_store.list_all(user_id)
    ]


@app.post("/v1/memories", response_model=MemoryRecord)
def create_memory(payload: MemoryCreateRequest) -> MemoryRecord:
    """Explicitly store a preference/fact (distinct from the engine's automatic capture)."""
    record = memory_store.remember(payload.user_id, payload.text)
    return MemoryRecord.model_validate(record)


@app.delete("/v1/memories/{memory_id}")
def delete_memory(memory_id: str) -> dict[str, bool]:
    """Delete a single memory by id — the "edit" half of inspect/edit/clear."""
    return {"deleted": memory_store.delete(memory_id)}


@app.delete("/v1/memories")
def clear_memories(user_id: str = "default") -> dict[str, int]:
    """Wipe all memories for a user — the "clear" half of inspect/edit/clear."""
    return {"deleted": memory_store.clear(user_id)}


@app.get("/v1/dlq", response_model=list[DeadLetterRecord])
def list_dead_letters() -> list[DeadLetterRecord]:
    """Inspect jobs that exhausted their retries and landed in the dead-letter queue."""
    return [DeadLetterRecord.model_validate(item) for item in dlq_store.list_all()]


@app.post("/v1/dlq/{item_id}/replay", response_model=RunResponse)
def replay_dead_letter(item_id: int) -> RunResponse:
    """Re-attempt a dead-lettered job by replaying its original run/approve payload."""
    item = dlq_store.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Dead letter not found")
    payload = item["payload"]
    if payload.get("type") == "run":
        return RunResponse(
            **engine.start(
                payload["request"], user_id=payload.get("user_id", "default")
            )
        )
    if payload.get("type") == "approve":
        return RunResponse(
            **engine.approve(
                payload["run_id"], payload["approved"], payload.get("approver", "human")
            )
        )
    raise HTTPException(status_code=400, detail="Unsupported dead letter payload")
