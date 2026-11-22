"""The owner's dashboard: a knowledge map from their world, plus one row of live state (DASH-1, 2026-11-22).

hbar 2026-11-22: the stock /dashboard ("Console brain-node localhost") rebuilt as his own: what he studied,
structured and ordered, each topic linking to the repos and notes he has on it, with one row of live state
(threads running, jobs, pushes waiting).

The map is the OWNER'S data, never this template's: <world>/ops/dashboard/knowledge.json

    {"title": "...", "line": "...",
     "groups": [{"id", "name", "line",
                 "topics": [{"id", "name", "line", "weak": "...", "points": ["..."],
                             "links": [{"label": "...", "path": "ops/..."} | {"label": "...", "url": "https://..."}]}]}]}

A brain whose world has no such file gets {"map": null} and the page falls back to the stock dashboard.
Everything here only reads. A link's `path` is relative to the world and must stay inside it (resolved, no
escape through .. or a symlink); the answer says whether it exists and whether it is a folder, and gives the
console route that opens it (/files?path=<absolute>). A `url` must be https. Sizes are capped so a huge or
hostile file cannot grow the answer.

pushes(world) reads the steward's queue (<world>/ops/steward/queue.md, "### <repo> (<branch>): N commit(s)
ahead; leak check: <result>") as the pushes waiting for the owner's word.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import quote

MAP_REL = ("ops", "dashboard", "knowledge.json")
QUEUE_REL = ("ops", "steward", "queue.md")
MAX_BYTES = 400_000
MAX_GROUPS, MAX_TOPICS, MAX_POINTS, MAX_LINKS = 16, 16, 8, 8
ID_RE = re.compile(r"[^a-z0-9._-]+")
QUEUE_RE = re.compile(r"^### (.+?) \(([^)]*)\): (\d+) commit\(s\) ahead; leak check: (.*)$")

_cache: dict = {}


def _s(v, n: int) -> str:
    return " ".join(str(v).split())[:n] if isinstance(v, (str, int, float)) and not isinstance(v, bool) else ""


def _id(v, fallback: str) -> str:
    return ID_RE.sub("-", _s(v, 64).lower()).strip("-") or fallback


def _link(world: Path, raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    label = _s(raw.get("label"), 60)
    url = _s(raw.get("url"), 400)
    if url:
        return {"label": label or url, "url": url} if url.startswith("https://") else None
    rel = _s(raw.get("path"), 400)
    if not rel or rel.startswith(("/", "~")):
        return None
    root = os.path.realpath(world)
    full = os.path.realpath(os.path.join(root, rel))
    if full != root and not full.startswith(root + os.sep):
        return None
    exists = os.path.exists(full)
    return {"label": label or rel, "path": rel, "exists": exists, "dir": exists and os.path.isdir(full),
            "href": "/files?path=" + quote(full, safe="")}


def _topic(world: Path, raw, n: int) -> dict | None:
    if not isinstance(raw, dict) or not _s(raw.get("name"), 80):
        return None
    points = [p for p in (_s(x, 200) for x in (raw.get("points") if isinstance(raw.get("points"), list) else [])) if p]
    links = [k for k in (_link(world, x) for x in (raw.get("links") if isinstance(raw.get("links"), list) else [])) if k]
    return {"id": _id(raw.get("id"), f"t{n}"), "name": _s(raw.get("name"), 80), "line": _s(raw.get("line"), 200),
            "weak": _s(raw.get("weak"), 240), "points": points[:MAX_POINTS], "links": links[:MAX_LINKS]}


def build_map(world, raw) -> dict | None:
    """The owner's file as the page reads it: cleaned, capped, links resolved. None when it holds no group."""
    if not isinstance(raw, dict) or not isinstance(raw.get("groups"), list):
        return None
    world = Path(world)
    groups = []
    for gi, g in enumerate(raw["groups"][:MAX_GROUPS]):
        if not isinstance(g, dict) or not _s(g.get("name"), 80):
            continue
        topics = [t for t in (_topic(world, x, ti) for ti, x in
                              enumerate((g.get("topics") if isinstance(g.get("topics"), list) else [])[:MAX_TOPICS])) if t]
        groups.append({"id": _id(g.get("id"), f"g{gi}"), "name": _s(g.get("name"), 80), "line": _s(g.get("line"), 200),
                       "topics": topics})
    if not groups:
        return None
    return {"title": _s(raw.get("title"), 80), "line": _s(raw.get("line"), 240), "groups": groups}


def load_map(world) -> dict | None:
    """<world>/ops/dashboard/knowledge.json, re-read when the file changes. None: no world, no file, not a map."""
    if not world:
        return None
    path = Path(world).joinpath(*MAP_REL)
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_mtime_ns, st.st_size)
    if _cache.get("key") != key:
        built = None
        if st.st_size <= MAX_BYTES:
            try:
                built = build_map(world, json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                built = None
        _cache.update(key=key, raw=built)
    return _cache.get("raw")


def pushes(world) -> list:
    """The repos waiting for the owner's push word, from the steward's queue: [{repo, branch, ahead, leak, clean}]."""
    if not world:
        return []
    try:
        text = Path(world).joinpath(*QUEUE_REL).read_text(encoding="utf-8", errors="replace")[:MAX_BYTES]
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        m = QUEUE_RE.match(line.strip())
        if m and int(m.group(3)) > 0:
            leak = _s(m.group(4), 80)
            out.append({"repo": _s(m.group(1), 120), "branch": _s(m.group(2), 60), "ahead": int(m.group(3)),
                        "leak": leak, "clean": leak.lower() == "clean"})
    return out[:40]


def view(world, threads: list, jobs: list) -> dict:
    """What GET /cc/dashboard answers. `threads`: [{id, title}] answering now; `jobs`: the bridge's job
    records (only those not ended are shown)."""
    running = [{"id": _s(j.get("id"), 40), "title": _s(j.get("title"), 120) or _s(j.get("id"), 40),
                "thread": _s(j.get("thread"), 64)}
               for j in jobs if isinstance(j, dict) and j.get("ended") is None]
    ths = [{"id": _s(t.get("id"), 64), "title": _s(t.get("title"), 120) or "a thread"}
           for t in threads if isinstance(t, dict) and t.get("id")]
    return {"map": load_map(world), "world": bool(world),
            "live": {"threads": ths[:40], "jobs": running[:40], "pushes": pushes(world)}}
