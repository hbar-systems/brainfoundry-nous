"""
api/quarantine_audit.py — append-only log of operator quarantine decisions.

The write-lane injection gate (cognitive-OS gap #3) quarantines a high-severity
automated write: stored with its provenance but excluded from retrieval until an
operator reviews it. The *review decision* — release (and at which trust tier) or
hard-delete — is exactly the kind of action that needs a record: it is a human
overriding a security hold, and the operator must later be able to answer "what
did I let back in, and what did I destroy?"

Same shape and contract as api/tools/federation_audit.py: one JSON line per
event, under /app/runtime (volume-mounted, survives rebuilds), best-effort
(a failed audit write never blocks the decision).

Record fields:
    ts             UTC ISO-8601 (stamped here)
    action         "release" | "delete"
    document_name  the quarantined document acted on
    chunks         number of chunks affected
    new_tier       release: "untrusted" | "semantic"; delete: null
    injection_risk the scan band that quarantined it (for context)
    actor          who decided — "operator" (these endpoints are operator-authed)
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

QUARANTINE_AUDIT_PATH = Path(
    os.getenv("QUARANTINE_AUDIT_PATH", "/app/runtime/quarantine_audit.jsonl")
)
_LOCK = threading.Lock()


def log(entry: Dict[str, Any]) -> None:
    """Append one quarantine-decision event. `ts` is stamped here in UTC."""
    record = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
    try:
        with _LOCK:
            QUARANTINE_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with QUARANTINE_AUDIT_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Never let an audit failure break the operator's decision.
        pass


def record_decision(
    *,
    action: str,
    document_name: str,
    chunks: int,
    new_tier: Optional[str] = None,
    injection_risk: Optional[str] = None,
    actor: str = "operator",
) -> None:
    """Typed wrapper so call sites don't hand-assemble the dict."""
    entry: Dict[str, Any] = {
        "action": action,
        "document_name": document_name,
        "chunks": int(chunks),
        "new_tier": new_tier,
        "injection_risk": injection_risk,
        "actor": actor,
    }
    log(entry)


def tail(n: int = 50) -> List[Dict[str, Any]]:
    """Return the most recent `n` quarantine decisions (newest last), for the UI."""
    try:
        if not QUARANTINE_AUDIT_PATH.exists():
            return []
        with _LOCK:
            lines = QUARANTINE_AUDIT_PATH.read_text(encoding="utf-8").splitlines()
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
