"""
api/onboarding/trial_reasoner.py — cost/rate-capped SHARED reasoner for the
first-run onboarding of a fresh, keyless brain.

WHY THIS EXISTS
A brand-new brain has no BYOK cloud key, and the local 1b/3b is too weak for the
sharp reflections the "become-you" wow depends on. We do NOT make a cold owner
paste a key before the payoff. Instead the operator funds a SHARED key, used
only for the first session, behind hard caps so a stranger can never burn it.

SECURITY CONTRACT (get this wrong and it bills the operator)
  - The trial key is a SEPARATE dedicated client built from TRIAL_REASONER_API_KEY.
    It is NEVER the brain's own ANTHROPIC_API_KEY and is NEVER registered in
    api/providers.py — so no normal /chat turn on any brain can ever spend it.
  - With TRIAL_REASONER_API_KEY unset (the state of every already-provisioned
    brain after this template change) the whole feature is OFF: is_available()
    is False and every entry point no-ops. Zero behaviour change.
  - Every call is metered fail-closed: a HARD per-session token cap, a per-IP/day
    token cap, a per-IP/day distinct-session cap, and an optional brain-wide
    daily kill-ceiling. Counters are reserved BEFORE the call (reserve-then-
    reconcile) so concurrent turns cannot collectively overshoot a cap. If the
    counter backend is configured but unreachable, calls REFUSE rather than
    proceed unmetered.
  - Every call (allowed or refused) appends one audit line; the source IP is
    hashed, never stored raw.

Modelled on the shapes already in the repo: api/kernel/rate_limiter.py
(Redis, fail-closed) and api/tools/budget.py (sidecar JSON counter).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

# ── Configuration (read lazily so settings/env changes at runtime take effect) ─
DEFAULT_MODEL = "claude-haiku-4-5"


def _env(name: str, default: str) -> str:
    """Read an env var, treating UNSET *and* empty-string as 'use default'.

    docker-compose wires these as `${NAME:-}`, which sets an EMPTY STRING in the
    container when the operator hasn't overridden them in .env. Plain
    os.getenv(name, default) would then return "" (the key IS set) — and
    int("") would crash every trial call. Falling back on empty makes the
    compose `${NAME:-}` pattern safe and the documented defaults authoritative."""
    v = os.getenv(name)
    return v if (v is not None and v.strip() != "") else default


def _int_env(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except (TypeError, ValueError):
        return default


def _model() -> str:
    return _env("TRIAL_REASONER_MODEL", DEFAULT_MODEL)


def _session_token_cap() -> int:
    return _int_env("TRIAL_SESSION_TOKEN_CAP", 40000)


def _ip_daily_token_cap() -> int:
    return _int_env("TRIAL_IP_DAILY_TOKEN_CAP", 150000)


def _ip_daily_session_cap() -> int:
    return _int_env("TRIAL_IP_DAILY_SESSION_CAP", 5)


def _global_daily_token_cap() -> int:
    # 0 = disabled. A brain-wide kill-ceiling across all sessions, defence
    # against a distributed-IP attack that stays under the per-IP cap.
    return _int_env("TRIAL_GLOBAL_DAILY_TOKEN_CAP", 0)


def _audit_dir() -> Path:
    return Path(_env("TRIAL_AUDIT_DIR", "/app/runtime/audit/trial_reasoner"))


def _file_budget_path() -> Path:
    return Path(_env("TRIAL_BUDGET_PATH", "/app/runtime/trial_budget.json"))


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Dedicated trial client — built lazily, kept out of api/providers.py ────────
_client_obj = None
_client_built = False


def _client():
    """The dedicated AsyncAnthropic client for the trial key, or None.

    Built once, lazily. Distinct from every client in api/providers.py so a
    normal chat turn can never reach the trial key.
    """
    global _client_obj, _client_built
    if _client_built:
        return _client_obj
    _client_built = True
    key = os.getenv("TRIAL_REASONER_API_KEY", "").strip()
    if not key:
        _client_obj = None
        return None
    try:
        import anthropic as _ant
        _client_obj = _ant.AsyncAnthropic(api_key=key)
    except Exception as e:  # SDK missing / bad key shape — feature stays OFF
        print(f"[trial_reasoner] client init failed: {e}", flush=True)
        _client_obj = None
    return _client_obj


def reset_client_cache() -> None:
    """Drop the cached client so a key change is picked up. Mainly for tests."""
    global _client_obj, _client_built
    _client_obj = None
    _client_built = False


def is_available() -> bool:
    """True if a trial key is configured (caps are checked per-call, not here)."""
    return _client() is not None


# ── Counter backend: Redis primary (fail-closed), JSON-file fallback for dev ──
class _Backend:
    """Atomic counters for the caps. Redis when REDIS_URL is set (production,
    fail-closed); a small locked JSON sidecar otherwise (local dev only).

    Methods return ``None`` to signal a hard backend failure that the caller
    must treat as fail-closed (refuse). They never raise.
    """

    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "")
        self._client = None
        self._lock = threading.Lock()

    # -- Redis ----------------------------------------------------------------
    def _redis(self):
        if self._client is not None:
            return self._client
        if not self.redis_url:
            return None
        import redis
        self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    @property
    def uses_redis(self) -> bool:
        return bool(self.redis_url)

    # -- File fallback --------------------------------------------------------
    def _file_load(self) -> dict:
        p = _file_budget_path()
        try:
            return json.loads(p.read_text()) if p.exists() else {}
        except Exception:
            return {}

    def _file_save(self, data: dict) -> None:
        p = _file_budget_path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(data))
            tmp.replace(p)
        except Exception as e:
            print(f"[trial_reasoner] file budget save failed: {e}", flush=True)

    @staticmethod
    def _prune_file(data: dict) -> dict:
        """Keep the file small: drop counters for past UTC days and stale
        sessions (anything not stamped today)."""
        today = _today()
        counters = {k: v for k, v in data.get("counters", {}).items()
                    if (":" not in k) or k.endswith(today) or "sess:" in k}
        # Sessions self-expire after their day; drop ones last touched before today.
        sess_day = data.get("sess_day", {})
        live_sess = {k for k, d in sess_day.items() if d == today}
        counters = {k: v for k, v in counters.items()
                    if not k.startswith("sess:") or k.split("sess:", 1)[1] in live_sess}
        sets = {k: v for k, v in data.get("sets", {}).items() if k.endswith(today)}
        sess_day = {k: d for k, d in sess_day.items() if d == today}
        return {"counters": counters, "sets": sets, "sess_day": sess_day}

    # -- Public atomic ops ----------------------------------------------------
    def incrby(self, key: str, amount: int, ttl: int, *, session: Optional[str] = None) -> Optional[int]:
        """Atomically add ``amount`` to ``key``; return the new value (or None
        on a hard backend failure → caller fails closed)."""
        if self.uses_redis:
            try:
                r = self._redis()
                if r is None:
                    return None
                val = r.incrby(key, amount)
                if val == amount:  # first touch
                    r.expire(key, ttl)
                return int(val)
            except Exception:
                return None  # configured-but-unreachable → fail closed
        # file mode
        with self._lock:
            data = self._prune_file(self._file_load())
            counters = data.setdefault("counters", {})
            counters[key] = int(counters.get(key, 0)) + amount
            if session is not None:
                data.setdefault("sess_day", {})[session] = _today()
            self._file_save(data)
            return counters[key]

    def get(self, key: str) -> Optional[int]:
        if self.uses_redis:
            try:
                r = self._redis()
                if r is None:
                    return None
                v = r.get(key)
                return int(v) if v is not None else 0
            except Exception:
                return None
        with self._lock:
            data = self._prune_file(self._file_load())
            return int(data.get("counters", {}).get(key, 0))

    def sadd_card(self, key: str, member: str, ttl: int) -> Optional[Tuple[int, bool]]:
        """Add ``member`` to set ``key``; return (cardinality, added_now) or
        None on backend failure."""
        if self.uses_redis:
            try:
                r = self._redis()
                if r is None:
                    return None
                added = r.sadd(key, member)
                if r.ttl(key) < 0:
                    r.expire(key, ttl)
                return int(r.scard(key)), bool(added)
            except Exception:
                return None
        with self._lock:
            data = self._prune_file(self._file_load())
            sets = data.setdefault("sets", {})
            members = set(sets.get(key, []))
            added = member not in members
            members.add(member)
            sets[key] = sorted(members)
            self._file_save(data)
            return len(members), added

    def srem(self, key: str, member: str) -> None:
        if self.uses_redis:
            try:
                r = self._redis()
                if r is not None:
                    r.srem(key, member)
            except Exception:
                pass
            return
        with self._lock:
            data = self._prune_file(self._file_load())
            sets = data.setdefault("sets", {})
            members = set(sets.get(key, []))
            members.discard(member)
            sets[key] = sorted(members)
            self._file_save(data)


_backend = _Backend()

_DAY_TTL = 90000      # 25h — daily keys self-evict
_SESSION_TTL = 86400  # 24h — a trial session


def _sess_key(session_id: str) -> str:
    return f"trial:sess:{session_id}"


def _ip_tok_key(ip: str) -> str:
    return f"trial:ip:{ip}:{_today()}"


def _ip_set_key(ip: str) -> str:
    return f"trial:ipsess:{ip}:{_today()}"


def _global_key() -> str:
    return f"trial:global:{_today()}"


# ── Reservation (reserve-then-reconcile, fail-closed) ─────────────────────────
class Reservation:
    __slots__ = ("ok", "reason", "amount", "session_remaining")

    def __init__(self, ok: bool, reason: Optional[str], amount: int, session_remaining: int):
        self.ok = ok
        self.reason = reason
        self.amount = amount
        self.session_remaining = session_remaining


def _reserve(session_id: str, ip: str, amount: int) -> Reservation:
    """Optimistically debit ``amount`` tokens against every cap BEFORE the
    model call. Each debit is an atomic incr-then-check-and-refund, so two
    concurrent turns can never both pass a check and then both spend.

    Returns a Reservation; ``ok=False`` with a reason means refuse and DO NOT
    call the model. ``amount`` is recorded so the caller can reconcile.
    """
    sess_cap = _session_token_cap()
    ip_cap = _ip_daily_token_cap()
    ip_sess_cap = _ip_daily_session_cap()
    global_cap = _global_daily_token_cap()

    # 1) distinct-session-per-IP cap (cheap, and bounds the blast radius first).
    res = _backend.sadd_card(_ip_set_key(ip), session_id, _DAY_TTL)
    if res is None:
        return Reservation(False, "backend_unavailable", 0, 0)
    card, added_now = res
    if ip_sess_cap > 0 and card > ip_sess_cap and added_now:
        _backend.srem(_ip_set_key(ip), session_id)  # undo — this session never ran
        return Reservation(False, "ip_session_cap", 0, 0)

    # 2) per-session token cap.
    new_sess = _backend.incrby(_sess_key(session_id), amount, _SESSION_TTL, session=session_id)
    if new_sess is None:
        return Reservation(False, "backend_unavailable", 0, 0)
    if new_sess > sess_cap:
        _backend.incrby(_sess_key(session_id), -amount, _SESSION_TTL, session=session_id)
        used = max(0, new_sess - amount)
        return Reservation(False, "session_cap", 0, max(0, sess_cap - used))

    # 3) per-IP/day token cap.
    new_ip = _backend.incrby(_ip_tok_key(ip), amount, _DAY_TTL)
    if new_ip is None or new_ip > ip_cap:
        _backend.incrby(_sess_key(session_id), -amount, _SESSION_TTL, session=session_id)
        if new_ip is not None:
            _backend.incrby(_ip_tok_key(ip), -amount, _DAY_TTL)
        reason = "backend_unavailable" if new_ip is None else "ip_cap"
        return Reservation(False, reason, amount, max(0, sess_cap - max(0, new_sess - amount)))

    # 4) optional brain-wide daily kill-ceiling.
    if global_cap > 0:
        new_g = _backend.incrby(_global_key(), amount, _DAY_TTL)
        if new_g is None or new_g > global_cap:
            _backend.incrby(_sess_key(session_id), -amount, _SESSION_TTL, session=session_id)
            _backend.incrby(_ip_tok_key(ip), -amount, _DAY_TTL)
            if new_g is not None:
                _backend.incrby(_global_key(), -amount, _DAY_TTL)
            reason = "backend_unavailable" if new_g is None else "global_cap"
            return Reservation(False, reason, amount, max(0, sess_cap - max(0, new_sess - amount)))

    return Reservation(True, None, amount, max(0, sess_cap - new_sess))


def _reconcile(session_id: str, ip: str, reserved: int, actual: int) -> int:
    """Adjust every counter by (actual - reserved) once real usage is known.
    A negative delta refunds the over-reservation. Returns session_remaining."""
    delta = actual - reserved
    if delta != 0:
        _backend.incrby(_sess_key(session_id), delta, _SESSION_TTL, session=session_id)
        _backend.incrby(_ip_tok_key(ip), delta, _DAY_TTL)
        if _global_daily_token_cap() > 0:
            _backend.incrby(_global_key(), delta, _DAY_TTL)
    used = _backend.get(_sess_key(session_id)) or 0
    return max(0, _session_token_cap() - used)


# ── Audit ─────────────────────────────────────────────────────────────────────
def _hash_ip(ip: str) -> str:
    return hashlib.sha256(("trial-salt:" + (ip or "")).encode()).hexdigest()[:16]


def _audit(record: dict) -> None:
    try:
        d = _audit_dir()
        d.mkdir(parents=True, exist_ok=True)
        with open(d / f"{_today()}.jsonl", "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        print(f"[trial_reasoner] audit skipped: {e}", flush=True)


def _estimate_input_tokens(messages: list, system: Optional[str]) -> int:
    """Cheap pre-call estimate (~4 chars/token) so the reservation covers input
    as well as the reserved output. Reconciled to exact usage after the call."""
    chars = len(system or "")
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            chars += len(c)
    return max(1, chars // 4)


# ── The metered call ──────────────────────────────────────────────────────────
async def complete(
    messages: list,
    *,
    session_id: str,
    ip: str,
    max_tokens: int,
    system: Optional[str] = None,
    kind: str = "answer",
) -> dict:
    """Run one trial-reasoner completion under all caps, fail-closed.

    Returns ``{"ok": True, "text", "session_remaining", "input_tokens",
    "output_tokens"}`` on success, or ``{"ok": False, "reason",
    "session_remaining"}`` when unavailable or capped — never billing past a cap.
    """
    client = _client()
    if client is None:
        return {"ok": False, "reason": "trial_unavailable", "session_remaining": 0}

    session_id = (session_id or "no-session").strip() or "no-session"
    ip = (ip or "0.0.0.0").strip() or "0.0.0.0"

    input_est = _estimate_input_tokens(messages, system)
    reserve_amt = max_tokens + input_est
    res = _reserve(session_id, ip, reserve_amt)
    if not res.ok:
        _audit({
            "ts": datetime.now(timezone.utc).isoformat(), "kind": kind,
            "session_id": session_id, "ip_hash": _hash_ip(ip), "model": _model(),
            "refused": res.reason, "session_remaining": res.session_remaining,
        })
        return {"ok": False, "reason": res.reason, "session_remaining": res.session_remaining}

    try:
        # Sanitize to {role, content} only — UI assistant messages carry extra
        # fields (sources, webSearch, …) that the Anthropic API rejects.
        user_msgs = [
            {"role": m.get("role"), "content": m.get("content")}
            for m in messages
            if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
            and m.get("content").strip()
        ]
        # Anthropic requires the first message to be role "user". Drop any
        # leading assistant turns (e.g. a UI-seeded opener) defensively.
        while user_msgs and user_msgs[0].get("role") == "assistant":
            user_msgs.pop(0)
        if not user_msgs:
            sr = _reconcile(session_id, ip, reserve_amt, 0)  # refund — nothing sent
            return {"ok": False, "reason": "empty_conversation", "session_remaining": sr}
        kwargs = {"system": system} if system else {}
        resp = await client.messages.create(
            model=_model(), max_tokens=max_tokens, messages=user_msgs, **kwargs)
        text = resp.content[0].text if resp.content else ""
        in_tok = int(getattr(resp.usage, "input_tokens", 0) or 0)
        out_tok = int(getattr(resp.usage, "output_tokens", 0) or 0)
        actual = in_tok + out_tok
        session_remaining = _reconcile(session_id, ip, reserve_amt, actual)
        _audit({
            "ts": datetime.now(timezone.utc).isoformat(), "kind": kind,
            "session_id": session_id, "ip_hash": _hash_ip(ip), "model": _model(),
            "input_tokens": in_tok, "output_tokens": out_tok,
            "session_remaining": session_remaining,
        })
        return {
            "ok": True, "text": text, "session_remaining": session_remaining,
            "input_tokens": in_tok, "output_tokens": out_tok,
        }
    except Exception as e:
        # Provider error: keep the reservation debited (conservative — a flaky
        # provider must not let the next call think budget is free) and refuse.
        used = _backend.get(_sess_key(session_id)) or 0
        session_remaining = max(0, _session_token_cap() - used)
        _audit({
            "ts": datetime.now(timezone.utc).isoformat(), "kind": kind,
            "session_id": session_id, "ip_hash": _hash_ip(ip), "model": _model(),
            "refused": "provider_error", "error": str(e)[:200],
            "session_remaining": session_remaining,
        })
        print(f"[trial_reasoner] provider error: {e}", flush=True)
        return {"ok": False, "reason": "provider_error", "session_remaining": session_remaining}


def status(session_id: str, ip: str) -> dict:
    """Non-mutating read of the trial budget for /onboarding/status. Reports
    available=False if the key is unset OR the caps are already spent."""
    if _client() is None:
        return {"available": False, "session_remaining": 0}
    session_id = (session_id or "no-session").strip() or "no-session"
    ip = (ip or "0.0.0.0").strip() or "0.0.0.0"
    sess_used = _backend.get(_sess_key(session_id))
    ip_used = _backend.get(_ip_tok_key(ip))
    if sess_used is None or ip_used is None:
        return {"available": False, "session_remaining": 0}  # backend down → fail closed
    sess_remaining = max(0, _session_token_cap() - sess_used)
    ip_remaining = max(0, _ip_daily_token_cap() - ip_used)
    return {
        "available": sess_remaining > 0 and ip_remaining > 0,
        "session_remaining": sess_remaining,
        "ip_remaining": ip_remaining,
    }


# ── Thin wrappers used by the endpoints (same metered path, different budgets) ─
async def complete_for_answer(messages, *, session_id, ip, system=None, max_tokens=1024):
    return await complete(messages, session_id=session_id, ip=ip,
                          max_tokens=max_tokens, system=system, kind="answer")


async def complete_for_extraction(messages, *, session_id, ip, system=None, max_tokens=400):
    return await complete(messages, session_id=session_id, ip=ip,
                          max_tokens=max_tokens, system=system, kind="extraction")
