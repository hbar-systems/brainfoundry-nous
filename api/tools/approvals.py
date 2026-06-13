"""
api/tools/approvals.py — per-call operator approval gate for RED-tier tools.

This is brain_command's PROPOSE → CONFIRM applied to *tool execution* instead of
memory writes — deliberately the same shape, not a parallel governance channel
(`api/main.py` brain_command flow, `api/kernel` permits). A RED tool is the line
between a brain that can read and one that can act, so each RED call pauses for
an exact, single-use, operator-minted approval before anything leaves the brain.

The contract (security lives here):

  PROPOSE   dispatch() hits a RED tool with no token → `propose()` records the
            exact (tool, canonicalized args) and returns a proposal the chat UI
            renders as an Approve / Reject card. Nothing has run.
  APPROVE   operator approves → `approve()` mints a single-use `approval_token`
            bound to sha256(tool + canonical args), with a short TTL (~300s).
  EXECUTE   dispatch() re-runs the SAME (tool, args) with the token →
            `verify_and_consume()` checks the hash matches, the token is
            unexpired and unused, marks it used, and only then the tool runs.
  REJECT    operator rejects → `reject()` discards the proposal; nothing runs.

Every non-execute outcome is fail-closed: a missing, expired, mismatched, or
reused token is refused (the brain's pre-existing posture for RED). Approval for
"message the owner X" can neither be replayed nor bent to "message Eve Y" — the
args hash and the one-shot flag see to that.

Egress-guard seam: `approve()` is the single chokepoint where outbound RED args
become real before execution. The planned egress guard (scan args for
private-scope / secret content — ops/ideas.md) slots in at the call site there;
this module just keeps that point clean and singular.

Durability: the store is a small JSON file under /app/runtime (volume-mounted,
survives container rebuilds), same convention as tool_audit / budget. Path is
env-overridable (TOOL_APPROVALS_PATH) so tests never touch the live file.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

APPROVALS_PATH = Path(os.getenv("TOOL_APPROVALS_PATH", "/app/runtime/tool_approvals.json"))
TTL_SECONDS = 300  # token lifetime after the operator approves; also caps how long a proposal is offerable

# IMPORTANT — the one-shot guarantee assumes a SINGLE-WORKER server.
# approve() and verify_and_consume() are synchronous and hold _LOCK with no
# await inside it, so within one process the read-check-burn of a token is
# atomic and a replay can never both pass. The brain runs single-worker uvicorn
# (no --workers), so this holds. If anyone later scales to `--workers N` /
# gunicorn / multiple processes, this in-process lock + JSON file is NO LONGER
# atomic across workers — two workers could both burn the same token. Before
# scaling out, move the store to an atomic backend (an OS file lock around the
# read-modify-write, or a Postgres row with `UPDATE ... WHERE token_used=false`).
_LOCK = threading.RLock()


# ── arg canonicalization + binding hash ──────────────────────────────────────
def canonical_args(args: Optional[Dict[str, Any]]) -> str:
    """Stable JSON for (args) so the same call always hashes the same. Sorted
    keys + tight separators: argument ORDER and whitespace can't change the
    binding, but any value change does."""
    return json.dumps(args or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def binding_hash(tool_name: str, args: Optional[Dict[str, Any]]) -> str:
    """The scope a token is bound to: this exact tool, these exact args. The
    tool name is folded in so a token for one tool can never satisfy another."""
    return hashlib.sha256(f"{tool_name}\n{canonical_args(args)}".encode("utf-8")).hexdigest()


# ── store (best-effort, locked) ──────────────────────────────────────────────
def _load() -> Dict[str, Any]:
    try:
        if APPROVALS_PATH.exists():
            return json.loads(APPROVALS_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


def _save(store: Dict[str, Any]) -> None:
    APPROVALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    APPROVALS_PATH.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _age_seconds(iso: str) -> float:
    try:
        t = datetime.fromisoformat(iso)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (_now() - t).total_seconds()
    except Exception:
        return float("inf")  # unparseable timestamp → treat as expired (fail closed)


def _public(rec: Dict[str, Any]) -> Dict[str, Any]:
    """The card view handed to the UI/model — preview, never the live token."""
    return {
        "proposal_id": rec["proposal_id"],
        "tool": rec["tool"],
        "preview": rec.get("preview", {}),
        "status": rec.get("status", "proposed"),
        "ttl_seconds": TTL_SECONDS,
        "created_at": rec.get("created_at"),
    }


# ── PROPOSE ───────────────────────────────────────────────────────────────────
def propose(tool_name: str, args: Optional[Dict[str, Any]], *,
            preview: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Record a pending RED call and return the Approve/Reject card data. Nothing
    executes here — the operator must approve before a token exists at all."""
    with _LOCK:
        store = _load()
        proposal_id = "PROP-" + secrets.token_hex(8)
        rec = {
            "proposal_id": proposal_id,
            "tool": tool_name,
            "args": args or {},                       # full args: needed to execute on approve
            "binding_hash": binding_hash(tool_name, args),
            "preview": preview or {},                 # trimmed args for the card
            "status": "proposed",
            "created_at": _now().isoformat(),
            "approval_token": None,
            "token_used": False,
        }
        store[proposal_id] = rec
        _save(store)
        return _public(rec)


def get(proposal_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        return _load().get(proposal_id)


def list_pending() -> List[Dict[str, Any]]:
    """Proposals still awaiting a decision and not yet expired (operator review)."""
    with _LOCK:
        store = _load()
    out = []
    for rec in store.values():
        if rec.get("status") == "proposed" and _age_seconds(rec.get("created_at", "")) <= TTL_SECONDS:
            out.append(_public(rec))
    return out


# ── APPROVE (mint the single-use, args-bound token) ──────────────────────────
def approve(proposal_id: str) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    """Operator approves a proposal. Mints a one-shot `approval_token` scoped to
    the proposal's (tool, args) hash and returns (token, record, error). The
    record carries the exact tool + args the caller must re-dispatch — execution
    runs against THOSE, never against anything the model re-supplies."""
    with _LOCK:
        store = _load()
        rec = store.get(proposal_id)
        if rec is None:
            return None, None, "unknown_proposal"
        if rec.get("status") != "proposed":
            return None, None, f"already_{rec.get('status')}"
        if _age_seconds(rec.get("created_at", "")) > TTL_SECONDS:
            rec["status"] = "expired"
            _save(store)
            return None, None, "expired"
        token = "APPR-" + secrets.token_hex(16)
        rec["approval_token"] = token
        rec["status"] = "approved"
        rec["token_used"] = False
        rec["approved_at"] = _now().isoformat()
        _save(store)
        return token, dict(rec), None


# ── REJECT ────────────────────────────────────────────────────────────────────
def reject(proposal_id: str) -> Tuple[bool, Optional[str]]:
    with _LOCK:
        store = _load()
        rec = store.get(proposal_id)
        if rec is None:
            return False, "unknown_proposal"
        if rec.get("status") not in ("proposed", "approved"):
            return False, f"already_{rec.get('status')}"
        rec["status"] = "rejected"
        rec["rejected_at"] = _now().isoformat()
        rec["approval_token"] = None  # any minted token is dead on reject
        _save(store)
        return True, None


# ── VERIFY + CONSUME (the gate dispatch() runs at execute time) ──────────────
def verify_and_consume(tool_name: str, args: Optional[Dict[str, Any]], token: str
                       ) -> Tuple[bool, str]:
    """Fail-closed check, run inside dispatch() when a RED call arrives WITH a
    token. Passes only if the token exists, was minted for THIS exact (tool,
    args), is unexpired, and has not been used. On success the token is burned
    (one-shot) so a replay of the same approved call is refused. Returns
    (ok, reason); reason is the audit/refusal label on failure."""
    if not token:
        return False, "missing"
    with _LOCK:
        store = _load()
        rec = next((r for r in store.values() if r.get("approval_token") == token), None)
        if rec is None:
            return False, "unknown"
        if rec.get("token_used"):
            return False, "reused"
        if rec.get("status") != "approved":
            return False, "not_approved"
        if _age_seconds(rec.get("approved_at", "")) > TTL_SECONDS:
            rec["status"] = "expired"
            _save(store)
            return False, "expired"
        if rec.get("binding_hash") != binding_hash(tool_name, args):
            return False, "args_mismatch"
        rec["token_used"] = True
        rec["status"] = "executed"
        rec["executed_at"] = _now().isoformat()
        _save(store)
        return True, "ok"
