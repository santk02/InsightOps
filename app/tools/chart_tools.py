"""Chart generation tools."""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from app.config import get_settings


def _serialize_value(val: Any) -> Any:
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    return val


def make_chart(
    rows: list[dict[str, Any]],
    kind: str = "bar",
    x: str | None = None,
    y: str | None = None,
    title: str = "Chart",
) -> str:
    """Generate a chart PNG from query results."""
    if not rows:
        raise ValueError("Cannot chart empty result set")
    if len(rows) == 1 and len(rows[0]) == 1:
        raise ValueError("Single scalar result — skip chart")

    settings = get_settings()
    os.makedirs(settings.charts_dir, exist_ok=True)

    keys = list(rows[0].keys())
    x_col = x or keys[0]
    y_col = y or (keys[1] if len(keys) > 1 else keys[0])

    x_vals = [_serialize_value(r.get(x_col, "")) for r in rows[:50]]
    y_vals = [float(_serialize_value(r.get(y_col, 0)) or 0) for r in rows[:50]]

    fig, ax = plt.subplots(figsize=(10, 6))
    if kind == "line":
        ax.plot(x_vals, y_vals, marker="o")
    else:
        ax.bar(range(len(x_vals)), y_vals)
        ax.set_xticks(range(len(x_vals)))
        ax.set_xticklabels(x_vals, rotation=45, ha="right")

    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.set_title(title)
    fig.tight_layout()

    filename = f"{uuid.uuid4().hex[:12]}.png"
    path = os.path.join(settings.charts_dir, filename)
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return path
