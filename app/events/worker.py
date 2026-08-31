"""Redis-backed worker loop.

The worker keeps the blueprint's queue/dead-letter shape, but it gracefully
degrades if Redis is not available so the project can still be exercised in
local development.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from redis import Redis

from app.events.dlq import get_dead_letter_store
from app.graph.build import get_engine


def _fingerprint(payload: dict[str, Any]) -> str:
    """Stable hash of a payload's contents — the idempotency key for request de-duplication."""
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return sha256(blob).hexdigest()


@dataclass
class QueueWorker:
    redis_url: str
    queue_name: str = "insightops:runs"  # Redis list used as the work queue
    cache_ttl_seconds: int = 3600  # how long a completed result stays cached for idempotent replay
    max_attempts: int = 3  # retries before a job is pushed to the dead-letter queue

    def __post_init__(self) -> None:
        """Connect to Redis and grab a handle to the dead-letter store."""
        self._redis = Redis.from_url(self.redis_url, decode_responses=True)
        self._dlq = get_dead_letter_store()

    def process_once(self) -> dict[str, Any] | None:
        """Pop one job off the queue and run it; returns None if nothing was waiting."""
        item = self._redis.brpop(self.queue_name, timeout=1)  # blocking pop with a 1s poll interval
        if item is None:
            return None
        _, payload_raw = item
        payload = json.loads(payload_raw)
        engine = get_engine()
        attempts = int(payload.get("attempts", 0)) + 1
        try:
            if payload.get("type") == "run":
                result = engine.start(
                    payload["request"], user_id=payload.get("user_id", "default")
                )
            elif payload.get("type") == "approve":
                result = engine.approve(
                    payload["run_id"],
                    payload["approved"],
                    payload.get("approver", "human"),
                )
            else:
                raise ValueError(f"Unknown payload type: {payload.get('type')}")
            # Cache the result under its idempotency key so a duplicate enqueue within
            # cache_ttl_seconds returns the cached run instead of executing it again
            result_key = payload.get("_idempotency_key")
            if result_key:
                self._redis.setex(
                    f"insightops:result:{result_key}",
                    self.cache_ttl_seconds,
                    json.dumps(result, default=str),
                )
            return result
        except Exception as exc:  # pragma: no cover - depends on Redis/DB failures
            if attempts < self.max_attempts:
                # Re-enqueue with an incremented attempt counter — exponential backoff would
                # be added here in a production worker; kept simple for the local demo
                retry_payload = dict(payload, attempts=attempts)
                self._redis.rpush(
                    self.queue_name, json.dumps(retry_payload, default=str)
                )
            else:
                # Retry budget exhausted — park the job (and the error) in the dead-letter queue
                self._dlq.append(
                    payload.get("run_id", "unknown"),
                    payload,
                    str(exc),
                    attempts=attempts,
                )
            raise

    def enqueue(self, payload: dict[str, Any]) -> str:
        """Add a job to the queue, deduping identical in-flight/recent requests by content hash."""
        fingerprint = _fingerprint(payload)
        cache_key = f"insightops:dedupe:{fingerprint}"
        result = self._redis.get(f"insightops:result:{fingerprint}")
        if result:
            return result  # identical request already completed recently — skip re-running it
        if self._redis.set(cache_key, fingerprint, ex=self.cache_ttl_seconds, nx=True):
            # NX ensures only the first caller with this fingerprint actually enqueues the job
            queued_payload = dict(payload, _idempotency_key=fingerprint, attempts=0)
            self._redis.lpush(self.queue_name, json.dumps(queued_payload, default=str))
        return fingerprint


def run_worker_forever() -> None:
    """Entrypoint for `python -m app.events.worker` — polls the queue until the process is killed."""
    worker = QueueWorker(redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    while True:
        try:
            worker.process_once()
        except Exception:
            time.sleep(2)  # brief backoff before retrying the loop after an unexpected error
