from __future__ import annotations

from app.memory.store import MemoryStore


def test_memory_store_roundtrip(tmp_path):
    store = MemoryStore(tmp_path / "memories.json")
    item = store.remember("alice", "always exclude test accounts")
    assert item["text"] == "always exclude test accounts"
    assert store.recall("alice", "test accounts")
    assert store.delete(item["id"]) is True
    assert store.recall("alice", "test accounts") == []

