"""Dead-letter queue helpers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DeadLetterStore:
    path: Path | None = None

    def __post_init__(self) -> None:
        if self.path is None:
            base_dir = Path(os.getenv("INSIGHTOPS_DATA_DIR", Path.home() / ".insightops"))
            base_dir.mkdir(parents=True, exist_ok=True)
            self.path = base_dir / "dead_letters.jsonl"

    def append(self, run_id: str, payload: dict[str, Any], error: str, attempts: int) -> dict[str, Any]:
        assert self.path is not None
        record = {
            "id": self._next_id(),
            "run_id": run_id,
            "payload": payload,
            "error": error,
            "attempts": attempts,
            "created_at": _utcnow().isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str))
            handle.write("\n")
        return record

    def _next_id(self) -> int:
        records = self.list_all()
        return (records[-1]["id"] + 1) if records else 1

    def list_all(self) -> list[dict[str, Any]]:
        assert self.path is not None
        if not self.path.exists():
            return []
        items: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                items.append(json.loads(line))
        return items

    def get(self, item_id: int) -> dict[str, Any] | None:
        for item in self.list_all():
            if item.get("id") == item_id:
                return item
        return None


_DLQ: DeadLetterStore | None = None


def get_dead_letter_store() -> DeadLetterStore:
    global _DLQ
    if _DLQ is None:
        _DLQ = DeadLetterStore()
    return _DLQ

