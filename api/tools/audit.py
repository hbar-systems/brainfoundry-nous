"""
api/tools/audit.py — append-only audit trail for every tool dispatch.

Required for commercial use: the brain must be able to answer "where did this
claim come from, and what did my brain reach out and do?" Every dispatch — even
a refused or failed one — lands here as one JSON line. The log lives under
/app/runtime (volume-mounted) so it survives container rebuilds, and is
surfaced read-only in the brain UI.

Best-effort by contract: logging must never raise into the dispatch path. A
brain that can't write its audit line still answers; it just loses that line.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

AUDIT_PATH = Path(os.getenv("TOOL_AUDIT_PATH", "/app/runtime/tool_audit.jsonl"))
_LOCK = threading.Lock()


def log(entry: Dict[str, Any]) -> None:
    """Append one audit record. `ts` is stamped here in UTC ISO-8601."""
    record = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
    try:
        with _LOCK:
            AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Never let an audit failure break the tool call.
        pass


def tail(n: int = 50) -> List[Dict[str, Any]]:
    """Return the most recent `n` audit records (newest last), for the UI."""
    try:
        if not AUDIT_PATH.exists():
            return []
        with _LOCK:
            lines = AUDIT_PATH.read_text(encoding="utf-8").splitlines()
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
