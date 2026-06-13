"""
api/tools/federation_audit.py — append-only cross-brain audit trail.

The tool-dispatch audit (`api/tools/audit.py`) records what the *model* reached
for; this records what crossed the *federation boundary* in either direction —
who called this brain, and who this brain called. Required for commercial use:
the operator must be able to answer "which peers talked to my brain, and what
did mine ask of theirs?" without grepping container logs (the gap the
2026-06-13 smoke test hit: `grep federation.log` → nothing).

One JSON line per federation event. Mirrors audit.py's shape and contract:
the log lives under /app/runtime (volume-mounted, survives rebuilds) and
logging is best-effort — a brain that can't write its line still answers.

Record fields (per the federation-MVP spec):
    ts            UTC ISO-8601 (stamped here)
    direction     "in"  — a peer called THIS brain's /v1/federation/query
                  "out" — this brain called a peer via brain_call
    peer_brain_id the other brain (verified issuer / target; "anonymous" when
                  an inbound caller presented no verifiable assertion)
    query_summary first ~200 chars of the question
    documents_used number of corpus chunks the answering brain drew on
    answer_len    length of the answer text (chars)
    verified      bool — inbound: assertion verified against a pinned pubkey;
                  outbound: this brain signed the call with its federation key
    trust         "peer" | "anonymous"
    outcome       short status — "ok" | "rate_limited" | "budget_exceeded" |
                  "no_answer" | "error:<reason>"
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

FEDERATION_AUDIT_PATH = Path(
    os.getenv("FEDERATION_AUDIT_PATH", "/app/runtime/federation_audit.jsonl")
)
_LOCK = threading.Lock()


def log(entry: Dict[str, Any]) -> None:
    """Append one federation event. `ts` is stamped here in UTC ISO-8601."""
    record = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
    try:
        with _LOCK:
            FEDERATION_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with FEDERATION_AUDIT_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Never let an audit failure break the federation path.
        pass


def record_event(
    *,
    direction: str,
    peer_brain_id: str,
    query: str = "",
    documents_used: Optional[int] = None,
    answer_len: Optional[int] = None,
    verified: bool = False,
    trust: Optional[str] = None,
    outcome: str = "ok",
) -> None:
    """Typed convenience wrapper so call sites don't hand-assemble the dict."""
    entry: Dict[str, Any] = {
        "direction": direction,
        "peer_brain_id": peer_brain_id or "anonymous",
        "query_summary": (query or "")[:200],
        "verified": bool(verified),
        "trust": trust or ("peer" if verified else "anonymous"),
        "outcome": outcome,
    }
    if documents_used is not None:
        entry["documents_used"] = int(documents_used)
    if answer_len is not None:
        entry["answer_len"] = int(answer_len)
    log(entry)


def tail(n: int = 50) -> List[Dict[str, Any]]:
    """Return the most recent `n` federation events (newest last), for the UI."""
    try:
        if not FEDERATION_AUDIT_PATH.exists():
            return []
        with _LOCK:
            lines = FEDERATION_AUDIT_PATH.read_text(encoding="utf-8").splitlines()
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
