"""cc_member: one member's names and ports on a shared box (multi-instance). Created 2026-10-19.

Imported by cc-bridge.py (same directory). Standard library only. The shell twin is
scripts/cc/member.sh; tests/test_multi_instance.py holds the two to the same numbers.
No member (CC_MEMBER unset): today's single brain, unit names and ports unchanged.
"""
from __future__ import annotations

import re

RESERVED = {"hbar", "cc", "hands", "root", "admin", "brain", "brains", "ollama", "caddy", "console", "www", "api", "test"}
OFFSETS = {"api": 0, "ui": 1, "nodeos": 2, "postgres": 3, "public_chat": 4, "terminal": 7, "bridge": 8}
SINGLE = {"api": 8010, "ui": 3010, "nodeos": 8001, "postgres": 54332, "public_chat": 3020, "terminal": 7681, "bridge": 7682}


def handle_ok(handle: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9]{1,15}", handle or "")) and handle not in RESERVED


def block_ok(n) -> bool:
    return bool(re.fullmatch(r"[1-9][0-9]?", str(n)))


def ports(n=None) -> dict:
    """Member n's port block; None means today's single brain."""
    if n is None or n == "":
        return dict(SINGLE)
    if not block_ok(n):
        raise ValueError(f"port block must be 1..99, got {n!r}")
    base = 8100 + 10 * int(n)
    return {k: base + off for k, off in OFFSETS.items()}


def unit(name: str, member: str = "") -> str:
    """A host unit's name for this member: cc-bridge -> cc-bridge-ada; unchanged with no member."""
    return f"{name}-{member}" if member else name
