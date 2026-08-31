"""Durable memory store.

The blueprint calls for Mem0, but local development needs something that works
without external credentials. This module provides a simple file-backed memory
store with the same inspect/edit/clear shape, and it can be swapped for a Mem0
backend later without changing the API.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> datetime:
    """Timezone-aware current time — every stored record's created_at uses this."""
    return datetime.now(timezone.utc)


def _tokenize(text: str) -> set[str]:
    """Lowercase, split on non-alphanumerics — the cheap bag-of-words used for recall scoring."""
    return {token for token in re.split(r"[^a-z0-9]+", text.lower()) if token}


@dataclass
class MemoryStore:
    path: Path | None = None  # JSON file backing this store; defaults to ~/.insightops/memories.json
    _items: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        """Resolve the default storage path (env-overridable) and load existing memories."""
        if self.path is None:
            base_dir = Path(
                os.getenv("INSIGHTOPS_DATA_DIR", Path.home() / ".insightops")
            )
            base_dir.mkdir(parents=True, exist_ok=True)
            self.path = base_dir / "memories.json"
        self._load()

    def _load(self) -> None:
        """Read the backing file into memory; start empty if it's missing or corrupt."""
        assert self.path is not None
        if not self.path.exists():
            self._items = []
            return
        try:
            self._items = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self._items = []  # corrupt/partial file — fail safe rather than crash the app

    def _save(self) -> None:
        """Persist the current in-memory list back to disk."""
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._items, indent=2, default=str), encoding="utf-8"
        )

    def remember(
        self, user_id: str, text: str, metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Store a new memory record for a user and persist it immediately."""
        record = {
            "id": uuid.uuid4().hex,
            "user_id": user_id,
            "text": text.strip(),
            "created_at": _utcnow().isoformat(),
            "metadata": metadata or {},
        }
        self._items.append(record)
        self._save()
        return record

    def remember_preference(self, user_id: str, text: str) -> dict[str, Any] | None:
        """Persist only explicit preference statements from a user request."""
        normalized = text.strip()
        lowered = normalized.lower()
        # Only capture requests that read like a durable preference, not every question asked
        markers = (
            "always ",
            "prefer ",
            "please remember",
            "my preference",
            "never ",
            "exclude ",
        )
        if not normalized or not any(marker in lowered for marker in markers):
            return None
        return self.remember(user_id, normalized, metadata={"kind": "preference"})

    def recall(self, user_id: str, query: str, limit: int = 5) -> list[str]:
        """Return up to `limit` memory texts for this user, ranked by token overlap with the query."""
        query_tokens = _tokenize(query)
        scored: list[tuple[int, dict[str, Any]]] = []
        for item in self._items:
            if item.get("user_id") != user_id:
                continue  # never leak one user's memories into another user's recall
            text_tokens = _tokenize(item.get("text", ""))
            score = len(query_tokens & text_tokens)  # simple overlap score — no embeddings needed
            if score or not query_tokens:
                scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1].get("created_at", "")))  # best match, then oldest first
        return [item["text"] for _, item in scored[:limit]]

    def list_all(self, user_id: str | None = None) -> list[dict[str, Any]]:
        """List every stored memory, optionally filtered to one user — the "inspect" API."""
        if user_id is None:
            return list(self._items)
        return [item for item in self._items if item.get("user_id") == user_id]

    def delete(self, memory_id: str) -> bool:
        """Remove a single memory by id; returns whether anything was actually deleted."""
        before = len(self._items)
        self._items = [item for item in self._items if item.get("id") != memory_id]
        changed = len(self._items) != before
        if changed:
            self._save()
        return changed

    def clear(self, user_id: str) -> int:
        """Remove every memory for a user; returns how many were deleted."""
        before = len(self._items)
        self._items = [item for item in self._items if item.get("user_id") != user_id]
        deleted = before - len(self._items)
        if deleted:
            self._save()
        return deleted


_DEFAULT_STORE: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    """Return a process-wide singleton memory store instance."""
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = MemoryStore()
    return _DEFAULT_STORE
