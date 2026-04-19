"""
Federation replay cache — rejects reuse of a `jti` within its TTL window.

Closes T4 (replay within TTL). Every federation assertion carries a
unique `jti` (JWT ID) in its claims. On successful verify, the handler
records the `jti` here; a second verify attempt with the same `jti` is
caught by `seen_before()` and the handler rejects it with 401
`replay_detected` BEFORE returning `verified: true` to the caller.

The cache is in-process and bounded by the federation TTL (default
300s). Expired entries are pruned lazily on each lookup — no background
thread, no persistent store. For single-instance brain deployments this
is sufficient. A multi-instance deployment would need a shared backing
store (Redis, Postgres, etc.) keyed by `jti`; the interface here is
deliberately minimal so the swap is local.

Contract:

    seen_before(jti) -> bool
        True iff this `jti` is in the cache AND its exp has not yet
        passed. Prunes expired entries as a side effect.

    record(jti, exp) -> None
        Add `jti` with a TTL tied to the token's `exp` timestamp
        (unix seconds). Expired entries are pruned on the next
        `seen_before` call.

    clear() -> None
        Test hook. Never call in production code.

Intended handler sequence (api/main.py):

    claims = verify_federation_assertion(...)
    jti = claims.get("jti")
    if not jti:
        raise HTTPException(400, "missing_jti")
    if seen_before(jti):
        raise HTTPException(401, "replay_detected")
    record(jti, exp=claims["exp"])
    return {"verified": True, ...}
"""
from __future__ import annotations

import threading
import time
from typing import Dict

_cache: Dict[str, int] = {}
_lock = threading.Lock()


def _prune_expired_locked() -> None:
    now = int(time.time())
    expired = [jti for jti, exp in _cache.items() if exp <= now]
    for jti in expired:
        _cache.pop(jti, None)


def seen_before(jti: str) -> bool:
    """Return True iff `jti` is currently in the cache and not expired."""
    if not jti:
        return False
    with _lock:
        _prune_expired_locked()
        return jti in _cache


def record(jti: str, exp: int) -> None:
    """Add `jti` to the cache with TTL = `exp` - now."""
    if not jti:
        return
    with _lock:
        _cache[jti] = int(exp)


def clear() -> None:
    """Test hook — flushes the cache. Do not call in production."""
    with _lock:
        _cache.clear()
