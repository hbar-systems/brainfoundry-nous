"""The private library guard (DEMO-3, 2026-11-25): audio another artist made, kept on this box for a demo and for
asking that artist, never leaves through a release door before the artist's yes.

The library itself is written by the world's tool (hbar.world scripts/orfeo_library.py): one folder per track with
a sidecar, and an index.json beside them:

    {"files": {"<sha256>": {"video_id": ..., "title": ..., "artist": ..., "state": "fetched|demo made|asked|yes|no",
                            "cleared": false, "contact": "artist@...", "what": "fetched track|demo over it"}}}

The bridge's release doors (/send-file, /orfeo/post) ask refusal() before anything else. A file inside the library
folder is judged by its own sidecar; a file elsewhere by its sha256 against the index (a byte copy is the same
file). A brain with no library (no folder) has nothing to protect and refuses nothing. Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _read(p: Path) -> dict:
    try:
        d = json.loads(p.read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def refusal(lib_dir, path=None, sha256: str | None = None) -> str | None:
    """One plain sentence when the file may not leave, else None."""
    if not lib_dir:
        return None
    lib = Path(lib_dir)
    if not lib.is_dir():
        return None
    hit = None
    if path is not None:
        try:
            p = Path(path).resolve()
            rel = p.relative_to(lib.resolve())
        except (OSError, ValueError):
            rel = None
        if rel is not None and rel.parts:
            d = _read(lib / rel.parts[0] / "track.json")
            hit = d or {"video_id": rel.parts[0], "cleared": False, "state": "unknown"}
    if hit is None:
        files = (_read(lib / "index.json").get("files") or {})
        if not files:
            return None
        if sha256 is None and path is not None:
            try:
                sha256 = _sha256(Path(path))
            except OSError:
                return None
        hit = files.get(str(sha256 or "").lower())
    if not hit or hit.get("cleared"):
        return None
    return (f"\"{hit.get('title') or hit.get('video_id')}\" by {hit.get('artist') or 'another artist'} is private library "
            f"audio (state: {hit.get('state')}); it is for his demo and for asking that artist, and goes nowhere else "
            f"until the artist says yes")
