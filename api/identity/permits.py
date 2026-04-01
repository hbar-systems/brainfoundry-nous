import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Literal

PermitType = Literal[
    "MEMORY_WRITE",
    "MEMORY_READ",
    "CONNECTOR_READ",
    "CONNECTOR_WRITE",
    "EXEC",
    "NET_READ",
]



# Canonical permit type allowlist (fail-closed)
PERMIT_TYPE_ALLOWLIST = {
    "MEMORY_WRITE",
    "MEMORY_READ",
    "CONNECTOR_READ",
    "CONNECTOR_WRITE",
    "EXEC",
    "NET_READ",
}

def normalize_permit_type(value: Any) -> Optional[str]:
    """
    Normalize user-provided permit type to canonical uppercase string.
    Fail-closed: returns None if invalid/unknown.
    """
    if not isinstance(value, str):
        return None
    v = value.strip().upper()
    if v in PERMIT_TYPE_ALLOWLIST:
        return v
    return None
@dataclass(frozen=True)
class Permit:
    """
    Minimal permit primitive (v0.16).

    - typed
    - time-bound (exp)
    - aud-bound to client_id
    - sub-bound to operator_id
    - scope/constraints are type-specific and enforced by the kernel
    """
    v: int
    typ: PermitType
    iss: str
    sub: str              # operator_id
    aud: str              # client_id
    iat: int
    exp: int
    reason: str
    constraints: Dict[str, Any]

    def is_expired(self, now: Optional[int] = None) -> bool:
        now = int(now if now is not None else time.time())
        return now >= int(self.exp)


def now_ts() -> int:
    return int(time.time())


def build_permit(
    *,
    permit_type: PermitType,
    operator_id: str,
    client_id: str,
    ttl_seconds: int,
    reason: str,
    constraints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Returns a dict claims payload; signing/verification lives in identity/core.py
    (same token format as assertion).
    """
    now = now_ts()
    return {
        "iss": "hbar-brain",
        "sub": operator_id,
        "aud": client_id,
        "iat": now,
        "exp": now + int(ttl_seconds),
        "reason": reason,
        "constraints": constraints or {},
        "typ": permit_type,
        "v": 1,
    }
