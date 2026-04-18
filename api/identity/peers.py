"""
Federation peer registry — pinned trust anchors for cross-brain assertions.

Loads `known_peers.toml` (sibling to this file, or the path in the
`BRAIN_KNOWN_PEERS_PATH` env var for test overrides) and exposes lookup
by endpoint URL. Returning None from `find_peer_by_endpoint` means the
caller should reject the incoming assertion with a 403 — this is the
fail-closed control that prevents issuer impersonation (T1 in the
federation threat model).

The registry is the authoritative source for a peer's `brain_id` and
`public_key`. The `/identity` endpoint on the peer's own brain is NOT
trusted for these values; registry entries are set deliberately by the
operator, out-of-band, when federation is established.

Registry format (TOML):

    [[peer]]
    brain_id   = "yury"
    endpoint   = "https://yury.brainfoundry.ai"
    public_key = "_NyMlZbmJGg4JHRslXrUz6fbgTFYzWwbbuzOwwMQk5o"
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

_DEFAULT_PEERS_PATH = Path(__file__).parent / "known_peers.toml"


def _peers_path() -> Path:
    override = os.getenv("BRAIN_KNOWN_PEERS_PATH")
    return Path(override) if override else _DEFAULT_PEERS_PATH


def load_peers() -> List[Dict[str, Any]]:
    """
    Return the list of registered peers. Empty list on missing or
    malformed file (fail-closed: no peers → federation denied).
    """
    path = _peers_path()
    if not path.exists():
        return []
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return []
    peers = data.get("peer", [])
    return [p for p in peers if _valid_peer(p)]


def _valid_peer(p: Any) -> bool:
    return (
        isinstance(p, dict)
        and isinstance(p.get("brain_id"), str) and p["brain_id"]
        and isinstance(p.get("endpoint"), str) and p["endpoint"]
        and isinstance(p.get("public_key"), str) and p["public_key"]
    )


def find_peer_by_endpoint(endpoint: str) -> Optional[Dict[str, Any]]:
    """
    Look up a peer by endpoint URL. Returns the peer dict (with
    `brain_id`, `endpoint`, `public_key`) or None if not registered.
    Trailing slashes are normalized.
    """
    if not endpoint:
        return None
    normalized = endpoint.rstrip("/")
    for peer in load_peers():
        if peer["endpoint"].rstrip("/") == normalized:
            return peer
    return None
