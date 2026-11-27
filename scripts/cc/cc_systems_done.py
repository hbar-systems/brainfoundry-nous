"""What each system already finished (SYSTEMS-PAGES-1 "Folio", 2026-11-27). Read only.

hbar 2026-11-27: "I want to see the updates already made for the system so that I don't repeat myself". The owner's
world keeps a done box (ops/steward/done.tsv: one row per finished piece of work) and files each row under a system
with its own words (scripts/systems_done.py in the world; the filing words stay there, never in this template). It
writes the console's copy every ten minutes:

  <out>/board/systems-done.json   {built, days, source, counts: {system: n}, systems: {system: [{ts, what, state,
                                   job, thread, link, repo}, newest first]}}

GET /cc/systems/done                     -> {ok, built, days, counts}                       (no system: the counts)
GET /cc/systems/done?system=<id>&n=<N>   -> {ok, built, days, system, count, rows: [N newest]}   (N 1..60, default 3)

`state` is the world's plain word: "pushed", "waits for push" or "waits for Update". `link` is a path in the world (a
report when the row has one); the page opens it in the Files pane. A world without the file answers ok with nothing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

MAX_N = 60
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
STATES = ("pushed", "waits for push", "waits for Update")
_CACHE: dict = {}


def load(path: Path | str | None) -> dict | None:
    """The JSON, read again only when its mtime moves; None when absent or not a JSON object."""
    if not path:
        return None
    p = Path(path)
    try:
        mt = p.stat().st_mtime
    except OSError:
        return None
    if _CACHE.get("path") == str(p) and _CACHE.get("mtime") == mt:
        return _CACHE.get("data")
    try:
        d = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    d = d if isinstance(d, dict) else None
    _CACHE.update(path=str(p), mtime=mt, data=d)
    return d


def _row(r) -> dict | None:
    if not isinstance(r, dict) or not str(r.get("what") or "").strip():
        return None
    th = str(r.get("thread") or "")
    st = str(r.get("state") or "")
    return {"ts": str(r.get("ts") or "")[:20], "what": str(r.get("what"))[:300],
            "state": st if st in STATES else "pushed", "job": str(r.get("job") or "")[:60],
            "thread": th if re.fullmatch(r"[0-9a-f-]{36}", th) else "",
            "link": str(r.get("link") or "")[:400], "repo": str(r.get("repo") or "")[:200]}


def view(doc: dict | None, system: str | None = None, n=None) -> tuple[int, dict]:
    """(status, body) of GET /cc/systems/done. Pure."""
    d = doc if isinstance(doc, dict) else {}
    head = {"ok": True, "built": d.get("built"), "days": d.get("days")}
    if not system:
        counts = d.get("counts") if isinstance(d.get("counts"), dict) else {}
        return 200, {**head, "counts": {str(k): int(v) for k, v in counts.items() if isinstance(v, int)}}
    sid = str(system)
    if not ID_RE.match(sid):
        return 400, {"ok": False, "error": "no such system"}
    try:
        k = max(1, min(MAX_N, int(n if n not in (None, "") else 3)))
    except (TypeError, ValueError):
        k = 3
    rows = (d.get("systems") or {}).get(sid) if isinstance(d.get("systems"), dict) else None
    rows = [x for x in (_row(r) for r in (rows if isinstance(rows, list) else [])) if x]
    rows.sort(key=lambda r: r["ts"], reverse=True)
    counts = d.get("counts") if isinstance(d.get("counts"), dict) else {}
    count = counts.get(sid) if isinstance(counts.get(sid), int) else len(rows)
    return 200, {**head, "system": sid, "count": count, "rows": rows[:k]}
