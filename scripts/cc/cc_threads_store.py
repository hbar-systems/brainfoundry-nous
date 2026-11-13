"""The threads list's file, kept safe, and its recovery (2026-11-13).

Why: on 2026-11-13 the disk filled during an Update. threads.json was written in place, the write
came out short, the next load read broken JSON as an empty list, and the next save wrote a list of
one. Every older thread vanished from the dropdown while its transcript and its brain chat session
stayed whole. So:

  save    writes a temp file beside it and renames it over (a full disk leaves the old file whole),
          and keeps the last good list as threads.json.bak.
  load    falls back to the .bak when the file is missing or broken, instead of an empty list.
  recover adds back every brain chat session of the console (model_name "cc") the list lacks,
          with its transcript id (so continuing it keeps its context) when one matches. Threads
          idle for more than a week come back archived, so the open list stays short; "show
          archived" has them. Recovered entries carry "recovered": <date>.

Pure functions over paths and plain data; no network. The bridge calls the brain for the sessions.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path

KEEP = 200
ARCHIVE_AFTER_S = 7 * 24 * 3600


def _parse(path: Path):
    try:
        data = json.loads(path.read_text())
    except Exception:
        return None
    return data if isinstance(data, list) else None


def load(path: Path) -> list:
    data = _parse(path)
    if data is None:
        data = _parse(path.with_name(path.name + ".bak"))
    return data or []


def _write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save(path: Path, items: list) -> None:
    """Raises OSError when the disk refuses; the file on disk is then the previous one, whole."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    old = _parse(path)
    if old:
        _write_atomic(path.with_name(path.name + ".bak"), json.dumps(old, indent=1))
    _write_atomic(path, json.dumps(items[-KEEP:], indent=1))


# ---- recovery ----

def _norm(s: str) -> str:
    return " ".join(str(s or "").split())


def _when(s) -> float | None:
    if not s:
        return None
    try:
        from datetime import datetime, timezone
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.timestamp()
    except Exception:
        return None


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


_MSG = re.compile(r"<message>\s*(.*?)\s*(?:</message>|$)", re.S)


def _first_prompt(path: Path, max_lines: int = 40) -> tuple[str, float | None]:
    """The first user text of a transcript (inside <message> when wrapped) and its time."""
    try:
        with open(path, errors="replace") as f:
            for _ in range(max_lines):
                line = f.readline(4_000_000)
                if not line:
                    break
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("type") != "user":
                    continue
                c = (d.get("message") or {}).get("content")
                if isinstance(c, list):
                    c = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
                if not isinstance(c, str) or not c.strip():
                    continue
                m = _MSG.search(c)
                return _norm(m.group(1) if m else c), _when(d.get("timestamp"))
    except OSError:
        pass
    return "", None


def transcript_index(projects: Path | None) -> list[dict]:
    out = []
    if not projects or not projects.is_dir():
        return out
    for p in projects.glob("*.jsonl"):
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        text, t0 = _first_prompt(p)
        if text:
            out.append({"id": p.stem, "text": text, "start": t0, "mtime": mtime})
    return out


def _match(title: str, created: float | None, index: list[dict]) -> dict | None:
    want = _norm(title)
    if want.startswith("CC:"):
        want = want[3:].strip()
    if len(want) < 4:
        return None
    hits = [x for x in index if x["text"].startswith(want)
            and (created is None or x["start"] is None or x["start"] >= created - 300)]
    return max(hits, key=lambda x: x["mtime"]) if hits else None


def recover(items: list, sessions: list, projects: Path | None, now: float | None = None,
            index: list[dict] | None = None) -> tuple[list, int]:
    """Items plus every console session they lack. Returns (items, how many were added)."""
    now = now or time.time()
    have = {x.get("brain") for x in items if isinstance(x, dict)}
    todo = [s for s in sessions if isinstance(s, dict) and s.get("model_name") == "cc"
            and s.get("session_id") and s["session_id"] not in have]
    if not todo:
        return items, 0
    index = transcript_index(projects) if index is None else index
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    added = []
    for s in todo:
        created = _when(s.get("created_at"))
        hit = _match(s.get("title") or "", created, index)
        last = max([t for t in (created, hit["mtime"] if hit else None) if t], default=now)
        e = {"claude": hit["id"] if hit else None, "brain": s["session_id"],
             "title": _norm(s.get("title") or "")[:80] or "CC thread",
             "started": _iso(created or last), "last": _iso(last), "via": "recovered", "recovered": day}
        if now - last > ARCHIVE_AFTER_S:
            e["archived"] = True
        added.append(e)
    merged = sorted(added + [x for x in items if isinstance(x, dict)], key=lambda x: str(x.get("last") or ""))
    return merged[-KEEP:], len(added)
