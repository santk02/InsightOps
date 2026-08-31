"""Tests for the SQL safety boundary — the security story Phase 1 asks for."""

from __future__ import annotations

import pytest

from app.tools.db_tools import _validate_select_only, write_db


def test_read_db_validation_rejects_delete():
    """read_db's validator must reject anything that isn't a SELECT/WITH."""
    with pytest.raises(PermissionError):
        _validate_select_only("DELETE FROM analytics.orders")


def test_write_db_rejects_select():
    """write_db must refuse SELECT statements — callers should use read_db instead."""
    with pytest.raises(PermissionError):
        write_db("SELECT * FROM analytics.orders")
