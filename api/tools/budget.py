"""
api/tools/budget.py — per-tool monthly call caps.

A hard ceiling so a loop (or a future autonomous model) can't drain a paid API
quota or run up a bill. Counts are kept per calendar month (UTC) in a small
sidecar JSON under /app/runtime so they persist across rebuilds and reset on
their own when the month rolls over.

Caps are read from settings_store (operator-tunable). The counter file holds
only usage; the cap is policy, kept with the rest of the brain's settings.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

BUDGET_PATH = Path(os.getenv("TOOL_BUDGET_PATH", "/app/runtime/tool_budget.json"))
_LOCK = threading.Lock()


def _month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _load() -> Dict[str, Dict[str, int]]:
    try:
        return json.loads(BUDGET_PATH.read_text()) if BUDGET_PATH.exists() else {}
    except Exception:
        return {}


def _save(data: Dict[str, Dict[str, int]]) -> None:
    try:
        BUDGET_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = BUDGET_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(BUDGET_PATH)
    except Exception:
        pass


def cap(tool: str) -> int:
    """Monthly cap for a tool (or composite key), from settings/env.

    Composite keys let one budget module serve per-instance caps without a new
    store: `brain_call:<peer_id>` is the per-peer outbound federation cap (one
    ceiling per peer brain), tunable via FEDERATION_OUTBOUND_MONTHLY_CAP.
    """
    from api import settings_store
    if tool == "web_search":
        return settings_store.get_web_search_budget()
    if tool.startswith("brain_call:"):
        # Per-peer outbound federation call ceiling (calendar month, UTC).
        return int(os.getenv("FEDERATION_OUTBOUND_MONTHLY_CAP", "500"))
    # Unknown tools get a safe default until they declare their own cap.
    return 1000


def usage(tool: str, month: str | None = None) -> int:
    month = month or _month()
    return int(_load().get(tool, {}).get(month, 0))


def under_cap(tool: str) -> bool:
    return usage(tool) < cap(tool)


def record(tool: str) -> None:
    """Increment this month's counter for `tool`."""
    month = _month()
    with _LOCK:
        data = _load()
        per_tool = data.setdefault(tool, {})
        per_tool[month] = int(per_tool.get(month, 0)) + 1
        # Keep the file small: drop months older than the current one.
        for m in list(per_tool.keys()):
            if m != month:
                per_tool.pop(m, None)
        _save(data)
