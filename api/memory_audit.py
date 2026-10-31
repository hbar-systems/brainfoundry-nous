"""
api/memory_audit.py — append-only log of removals from the brain's memory.

The revert drill (D75, 2026-10-25) found that a bad ingest can be undone
(trash, then empty trash) but the undo leaves no record: once the trash is
emptied, the chunks and their proposal_id are gone and nothing says what was
removed, when, or how many. Autonomy over ingest does not widen until it does.
This log is that record.

Same shape and contract as api/quarantine_audit.py: one JSON line per event,
under /app/runtime (volume-mounted, survives rebuilds), best-effort (a failed
audit write never blocks the action).

Record fields:
    ts             UTC ISO-8601 (stamped here)
    action         "trash" | "restore" | "empty_trash" | "forget" | "fact_delete"
                   | "reingest_prune" (a re-ingest dropped chunks the new version
                   no longer has) | "vault_prune" (a vault file was deleted)
                   Quarantine release/delete keep their own log (quarantine_audit).
    document_name  the document acted on (null for empty_trash)
    chunks         number of chunks affected
    documents      empty_trash only: [{"name", "chunks"}] of what was destroyed
    before         trash only: the ?before= cut-off when a re-ingest retired an
                   older version (null for a plain trash)
    actor          "operator" (these paths are operator-authed)
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

MEMORY_AUDIT_PATH = Path(
    os.getenv("MEMORY_AUDIT_PATH", "/app/runtime/memory_audit.jsonl")
)
_LOCK = threading.Lock()

ACTIONS = ("trash", "restore", "empty_trash", "forget", "fact_delete",
           "reingest_prune", "vault_prune")


def log(entry: Dict[str, Any]) -> None:
    """Append one removal event. `ts` is stamped here in UTC."""
    record = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
    try:
        with _LOCK:
            MEMORY_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with MEMORY_AUDIT_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Never let an audit failure break the operator's action.
        pass


def record(
    *,
    action: str,
    document_name: Optional[str],
    chunks: int,
    documents: Optional[List[Dict[str, Any]]] = None,
    before: Optional[str] = None,
    actor: str = "operator",
) -> None:
    """Typed wrapper so call sites don't hand-assemble the dict."""
    entry: Dict[str, Any] = {
        "action": action,
        "document_name": document_name,
        "chunks": int(chunks),
        "actor": actor,
    }
    if documents is not None:
        entry["documents"] = [
            {"name": d.get("name"), "chunks": int(d.get("chunks") or 0)} for d in documents
        ]
    if before is not None:
        entry["before"] = before
    log(entry)


def tail(n: int = 50) -> List[Dict[str, Any]]:
    """Return the most recent `n` removal events (newest last), for the UI."""
    try:
        if not MEMORY_AUDIT_PATH.exists():
            return []
        with _LOCK:
            lines = MEMORY_AUDIT_PATH.read_text(encoding="utf-8").splitlines()
        out: List[Dict[str, Any]] = []
        for line in lines[-n:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception:
        return []
