"""Tests for the memory store's remember / recall / delete roundtrip."""

from __future__ import annotations

from app.memory.store import MemoryStore


def test_memory_store_roundtrip(tmp_path):
    """A remembered preference should be recallable, then deletable, then gone from recall."""
    store = MemoryStore(tmp_path / "memories.json")
    item = store.remember("alice", "always exclude test accounts")
    assert item["text"] == "always exclude test accounts"
    assert store.recall("alice", "test accounts")  # recall finds it via token overlap
    assert store.delete(item["id"]) is True
    assert store.recall("alice", "test accounts") == []  # gone after deletion — the "clear" contract
