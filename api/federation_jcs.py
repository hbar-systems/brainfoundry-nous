"""federation_jcs.py — Created 2026-06-21

Brain-side JCS canonicalizer + ED25519 signer for the hbar.social relay
(PROTOCOL_CONTRACT v0.5). Byte-identical to the relay's JS canonicalizer
(`hbar.social/repos/site/lib/protocol.ts` `canonicalize`).

CRITICAL — why this is NOT federation_dm.py's `_canonical()`:
  The relay canonicalizes with JS `JSON.stringify(sortDeep(x))` (JCS / RFC 8785).
  Python `json.dumps(sort_keys=True)` disagrees with JS on:
    1. integer-valued floats:  authorship 1.0 -> Python "1.0", JS "1"
    2. non-ASCII:              ensure_ascii=True -> "ä", JS emits raw "ä"
  authorship=1.0 (pure brain) and German text are the COMMON case, so naive
  json.dumps fails on the very first real post. Use THIS module for any payload
  signed for the relay.

Source of truth / proof harness:
  hbar.social/repos/site/scripts/brain_jcs.py  (this is a faithful vendor of it)
  hbar.social/repos/site/scripts/proof_canon.py (round-trips through the relay
  verify path; proves byte-identity to lib/protocol.ts).
"""
from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _es_number(n: float | int) -> str:
    """Serialize a number the way ECMAScript String(Number)/JSON.stringify does.

    Covers the v0.5 schema's numeric fields: `ts` (integer seconds) and
    `authorship` (0.0-1.0). Integer-valued numbers collapse to integer form
    ("1", "0", "1750000000"); non-integers use Python's shortest round-trip
    repr, which matches V8 for the small decimals authorship uses (0.1, 0.5,
    0.7, ...). Exponent-notation magnitudes are out of domain for v0.5.
    """
    if isinstance(n, bool):  # bool is an int subclass — must reject first
        raise TypeError("bool is not a JSON number")
    if isinstance(n, int):
        return str(n)
    if n != n or n in (float("inf"), float("-inf")):
        raise ValueError("NaN/Infinity are not valid JSON")
    if n.is_integer():
        return str(int(n))  # 1.0 -> "1" (the federation_dm.py landmine)
    return repr(n)


def _emit(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _es_number(value)
    if isinstance(value, str):
        # json.dumps escaping (controls, ", \) matches JS JSON.stringify;
        # ensure_ascii=False keeps non-ASCII raw, matching JS.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_emit(v) for v in value) + "]"
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda kv: kv[0])
        return "{" + ",".join(
            json.dumps(k, ensure_ascii=False) + ":" + _emit(v) for k, v in items
        ) + "}"
    raise TypeError(f"unserializable type: {type(value).__name__}")


def canonicalize(value: Any) -> bytes:
    """RFC 8785 / JCS-style canonical JSON, byte-identical to lib/protocol.ts."""
    return _emit(value).encode("utf-8")


def signing_bytes(payload: dict) -> bytes:
    """Canonical bytes of the payload with `signature` stripped (§3.1)."""
    return canonicalize({k: v for k, v in payload.items() if k != "signature"})


def sign_payload(payload: dict, private_key_b64url: str) -> dict:
    """Sign an unsigned v0.5 payload, return it with `signature` inserted.

    private_key_b64url: base64url (padding optional) of the raw 32-byte ED25519
    seed, matching how brains store BRAIN_PRIVATE_KEY.
    """
    seed = base64.urlsafe_b64decode(private_key_b64url + "=" * (-len(private_key_b64url) % 4))
    sk = Ed25519PrivateKey.from_private_bytes(seed)
    sig = sk.sign(signing_bytes(payload))
    sig_b64url = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return {**payload, "signature": sig_b64url}
