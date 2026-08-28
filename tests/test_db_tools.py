from __future__ import annotations

import pytest

from app.tools.db_tools import _validate_select_only, write_db


def test_read_db_validation_rejects_delete():
    with pytest.raises(PermissionError):
        _validate_select_only("DELETE FROM analytics.orders")


def test_write_db_rejects_select():
    with pytest.raises(PermissionError):
        write_db("SELECT * FROM analytics.orders")

