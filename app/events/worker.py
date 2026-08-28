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
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return sha256(blob).hexdigest()


@dataclass
class QueueWorker:
    redis_url: str
    queue_name: str = "insightops:runs"
    cache_ttl_seconds: int = 3600
    max_attempts: int = 3

    def __post_init__(self) -> None:
        self._redis = Redis.from_url(self.redis_url, decode_responses=True)
        self._dlq = get_dead_letter_store()

    def process_once(self) -> dict[str, Any] | None:
        item = self._redis.brpop(self.queue_name, timeout=1)
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
                retry_payload = dict(payload, attempts=attempts)
                self._redis.rpush(
                    self.queue_name, json.dumps(retry_payload, default=str)
                )
            else:
                self._dlq.append(
                    payload.get("run_id", "unknown"),
                    payload,
                    str(exc),
                    attempts=attempts,
                )
            raise

    def enqueue(self, payload: dict[str, Any]) -> str:
        fingerprint = _fingerprint(payload)
        cache_key = f"insightops:dedupe:{fingerprint}"
        result = self._redis.get(f"insightops:result:{fingerprint}")
        if result:
            return result
        if self._redis.set(cache_key, fingerprint, ex=self.cache_ttl_seconds, nx=True):
            queued_payload = dict(payload, _idempotency_key=fingerprint, attempts=0)
            self._redis.lpush(self.queue_name, json.dumps(queued_payload, default=str))
        return fingerprint


def run_worker_forever() -> None:
    worker = QueueWorker(redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    while True:
        try:
            worker.process_once()
        except Exception:
            time.sleep(2)
