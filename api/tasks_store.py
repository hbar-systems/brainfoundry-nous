"""
api/tasks_store.py — the brain's task / reminder list.

Stored as JSON in the persistent runtime volume (/app/runtime/tasks.json — same
place settings + persona survive rebuilds). A task has optional `due` (ISO 8601);
the reminder loop in api/main.py pings Telegram when a due task comes up.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

TASKS_PATH = Path(os.getenv("BRAIN_RUNTIME_DIR") or "/app/runtime") / "tasks.json"
_LOCK = threading.Lock()


def _load() -> List[Dict[str, Any]]:
    if not TASKS_PATH.exists():
        return []
    try:
        data = json.loads(TASKS_PATH.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(tasks: List[Dict[str, Any]]) -> None:
    TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = TASKS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(tasks, indent=2))
    tmp.replace(TASKS_PATH)


def list_tasks(include_done: bool = False) -> List[Dict[str, Any]]:
    tasks = _load()
    if not include_done:
        tasks = [t for t in tasks if not t.get("done")]
    # Soonest due first; undated last; then newest.
    tasks.sort(key=lambda t: (t.get("due") is None, t.get("due") or "", t.get("created", "")))
    return tasks


def add(text: str, due: Optional[str] = None, created: Optional[str] = None) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("task text required")
    task = {
        "id": uuid.uuid4().hex[:12],
        "text": text,
        "due": (due or None),
        "done": False,
        "reminded": False,
        "created": created or "",
    }
    with _LOCK:
        tasks = _load()
        tasks.append(task)
        _save(tasks)
    return task


def complete(task_id: str, done: bool = True) -> bool:
    with _LOCK:
        tasks = _load()
        hit = False
        for t in tasks:
            if t.get("id") == task_id:
                t["done"] = done
                hit = True
        if hit:
            _save(tasks)
    return hit


def delete(task_id: str) -> bool:
    with _LOCK:
        tasks = _load()
        new = [t for t in tasks if t.get("id") != task_id]
        if len(new) != len(tasks):
            _save(new)
            return True
    return False


def _parse_due(due: str):
    """Parse an ISO-8601 due string to an aware UTC datetime, or None."""
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat((due or "").strip().replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None


def due_unreminded(now=None) -> List[Dict[str, Any]]:
    """Tasks whose due time has passed and that haven't been reminded yet.
    Compares as datetimes (NOT ISO strings — string compare is wrong across
    'Z' vs '+00:00' and non-UTC offsets)."""
    from datetime import datetime, timezone
    if now is None or isinstance(now, str):
        now = _parse_due(now) if isinstance(now, str) else None
        now = now or datetime.now(timezone.utc)
    out = []
    for t in _load():
        if t.get("done") or t.get("reminded") or not t.get("due"):
            continue
        due = _parse_due(t["due"])
        if due is not None and due <= now:
            out.append(t)
    return out


def mark_reminded(task_id: str) -> None:
    with _LOCK:
        tasks = _load()
        for t in tasks:
            if t.get("id") == task_id:
                t["reminded"] = True
        _save(tasks)
