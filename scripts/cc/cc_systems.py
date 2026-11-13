"""The systems board's data and its standing threads (BOARD-3, 2026-11-12).

hbar 2026-11-12: "I SHOULD BE ABLE TO WRITE AND SEND RIGHT THERE AND THEN (SAY OR SPEAK IT)". The console page
/systems shows one tile per system of the owner's world; each tile has one composer that sends into that
system's ONE standing thread. This module is pure apart from the files it is handed:

  ThreadMap      system -> thread id, kept in the bridge's state dir (systems-threads.json), written atomically
                 (tmp + os.replace) under a process lock and an flock, so a thread is created once on the first
                 send and reused forever after. A seed map (the static board's out/board/threads.json) is adopted
                 read-only for a system the map does not know yet.
  board(...)     the tile data: registry/systems.json plus world, self and unfiled; per system the jobs, open
                 court items (ops/inbox/rulings.tsv), chopped thoughts (ops/chop/<date>.json, 7 days) and next
                 candidates (ops/next.tsv). At rest a tile shows its name and one number (things moving now); open,
                 up to seven lines of at most eight words with one link each; the rest grouped by kind
                 (ideas, decisions, questions, tasks, jobs, notes) with counts, ranked by importance then date.
                 No line links a raw .json file.

Filing: a thought carries its own system (the chopper's); a court item, a job and a next row are filed by an
explicit system field, then by the repo path (systems/<id>/), then by a registry id named in the text, then by an
optional owner file (<world>/ops/board/filing.json: {"tags": {"TAG": "system"}, "keywords": [["word", "system"]]}),
else "world". The owner's filing words stay in the owner's world, never in this template.

BOARD-4 (2026-11-13, hbar: "ON SINGLE PAGE I SEE EACH SYSTEM AND I CAN DISCUSS IN THE CHAT IN A SYSTEM WHILE SEEING
ALL THE SYSTEMS WHATS GOING ON AND FUNCTIONING"): each tile also carries four numbers, `counts` {running, done_today,
tasks, next}, and the lines behind each, `detail` {running, done_today, tasks, next: {count, lines}}. Running and done
today are live, from the bridge's own job list (running = started and not ended; done today = ended on today's UTC
date). When the owner's static board has been built (out/board/board.json, scripts/board.py in the owner's world, read
here as data), its court items, thoughts and next rows are the tiles' source and its `job_system` map files a job the
way the static board does; without it the world's files are read as above. A job neither places is filed by the
brief its command reads (ops/jobs/briefs/<name>.md: the first registry id the brief names), then as above.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

try:
    import fcntl
except ImportError:  # pragma: no cover - not on the box
    fcntl = None

LINES = 7
WORDS = 8
NOW_HOURS = 24
THOUGHT_DAYS = 7
GROUPS = ("ideas", "decisions", "questions", "tasks", "jobs", "notes")
THOUGHT_GROUP = {"idea": "ideas", "decision": "decisions", "question": "questions", "task-for-him": "tasks"}
EXTRA = (("world", "Across systems: the box, the console, the way of working."),
         ("self", "The owner's own state: the day, health, feelings."),
         ("unfiled", "What the chopper could not place."))
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
THREAD_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27,}$")


# ---------------------------------------------------------------- the thread map ----

class ThreadMap:
    """One standing thread per system. `resolve(system, create)` returns (thread, created): the mapped id when
    there is one (never a second thread), else the seed's (when `exists` says the thread is on the box), else
    `create(system)` once, under the lock, persisted before the lock is let go."""

    def __init__(self, path: Path, seed: Path | None = None):
        self.path = Path(path)
        self.seed = Path(seed) if seed else None
        self.lock = threading.Lock()

    def load(self) -> dict:
        try:
            d = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        s = d.get("systems") if isinstance(d, dict) else None
        return {k: v for k, v in (s or {}).items() if isinstance(v, dict) and v.get("thread")}

    def get(self, system: str) -> str | None:
        return (self.load().get(system) or {}).get("thread")

    def threads(self) -> dict:
        return {k: v["thread"] for k, v in self.load().items()}

    def _save(self, systems: dict) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps({"version": 1, "about": "system -> standing thread (cc_systems.ThreadMap); "
                                   "an entry is never replaced by the bridge", "systems": systems}, indent=1))
        os.replace(tmp, self.path)

    @contextlib.contextmanager
    def _locked(self):
        with self.lock:
            fh = None
            if fcntl is not None:
                self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                fh = open(self.path.with_name(self.path.name + ".lock"), "a")
                fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fh is not None:
                    fcntl.flock(fh, fcntl.LOCK_UN)
                    fh.close()

    def _seeded(self, system: str) -> str | None:
        if not self.seed:
            return None
        try:
            d = json.loads(self.seed.read_text())
        except (OSError, ValueError):
            return None
        t = d.get(system) if isinstance(d, dict) else None
        return t if isinstance(t, str) and THREAD_RE.match(t) else None

    def resolve(self, system: str, create, exists=None, keep=None) -> tuple[str | None, bool]:
        """`create(system)` -> thread id or None; `exists(thread)` -> bool; `keep(system, entry)` is called with the
        map entry when the thread is found (the bridge re-registers a thread its list has dropped) and may return
        the fields to keep beside it (title, seat ids), saved when they changed."""
        with self._locked():
            systems = self.load()
            ent = systems.get(system)
            if ent:
                kept = keep(system, ent) if keep else None
                if kept is not None and kept != (ent.get("keep") or {}):
                    systems[system] = {**ent, "keep": kept}
                    self._save(systems)
                return ent["thread"], False
            seeded = self._seeded(system)
            if seeded and (exists is None or exists(seeded)):
                systems[system] = {"thread": seeded, "created": _now(), "via": "seed"}
                self._save(systems)
                return seeded, False
            tid = create(system)
            if not tid:
                return None, False
            systems[system] = {"thread": tid, "created": _now(), "via": "bridge"}
            self._save(systems)
            return tid, True


    def refresh(self, keep) -> None:
        """`keep(system, entry)` for every entry, one save when any kept fields changed (the board's poll)."""
        with self._locked():
            systems = self.load()
            changed = False
            for sid, ent in systems.items():
                kept = keep(sid, ent)
                if kept is not None and kept != (ent.get("keep") or {}):
                    systems[sid] = {**ent, "keep": kept}
                    changed = True
            if changed:
                self._save(systems)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------- sources ----

def _clean(s, n=None) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if n is None or len(s) <= n else s[: n - 1].rstrip() + "..."


def phrase(text, n: int = WORDS) -> str:
    """A plain phrase of at most n words: no leading job tag, no quotes, no trailing punctuation."""
    s = _clean(text)
    s = re.sub(r"^CC:\s*", "", s)
    s = re.sub(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\s*", "", s)
    s = re.sub(r"[\"“”]", "", s).lstrip(" :,;-")
    w = s.split()
    out = " ".join(w[:n]).rstrip(" ,;:.-(")
    return out + ("..." if len(w) > n else "")


def read_tsv(path) -> list[dict]:
    rows, head = [], None
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return rows
    for ln in lines:
        if not ln.strip() or ln.startswith("#"):
            continue
        cells = ln.split("\t")
        if head is None:
            head = cells
            continue
        rows.append(dict(zip(head, cells + [""] * (len(head) - len(cells)))))
    return rows


def load_systems(world: Path) -> list[dict]:
    try:
        d = json.loads((world / "registry" / "systems.json").read_text())
    except (OSError, ValueError):
        d = {}
    out = [{"id": str(s["id"]), "status": s.get("status", ""), "description": _clean(s.get("description"), 200)}
           for s in d.get("systems", []) if isinstance(s, dict) and s.get("id")]
    have = {s["id"] for s in out}
    out += [{"id": i, "status": "active", "description": d0} for i, d0 in EXTRA if i not in have]
    return out


def known_ids(world: Path) -> set:
    return {s["id"] for s in load_systems(world)}


def load_filing(world: Path) -> dict:
    try:
        d = json.loads((world / "ops" / "board" / "filing.json").read_text())
    except (OSError, ValueError):
        return {"tags": {}, "keywords": []}
    tags = {str(k): str(v) for k, v in (d.get("tags") or {}).items()}
    kws = [(str(p[0]).lower(), str(p[1])) for p in (d.get("keywords") or []) if isinstance(p, (list, tuple)) and len(p) == 2]
    return {"tags": tags, "keywords": kws}


def _tag(title) -> str:
    m = re.match(r"\s*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)", title or "")
    return m.group(1) if m else ""


def _family(tag: str) -> str:
    return re.sub(r"-\d+$", "", tag)


def system_for(text: str, known: set, filing: dict, explicit: str = "", repo: str = "") -> str:
    if explicit and explicit in known:
        return explicit
    m = re.match(r"(?:/home/hands/world/)?systems/([^/]+)/", repo or "")
    if m and m.group(1) in known:
        return m.group(1)
    tag = _family(_tag(text))
    if tag and filing["tags"].get(tag) in known:
        return filing["tags"][tag]
    low = (text or "").lower()
    for sid in sorted(known, key=len, reverse=True):
        if sid not in ("world", "self", "unfiled") and re.search(r"(?<![\w.])" + re.escape(sid.lower()) + r"(?![\w])", low):
            return sid
    for word, sid in filing["keywords"]:
        if sid in known and re.search(r"\b" + re.escape(word), low):
            return sid
    return "world"


def _recent(ts: str, hours: float, now: datetime) -> bool:
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t > now - timedelta(hours=hours)


def _talk(thread: str) -> str:
    return "/talk?thread=" + quote(thread)


def _files(path: str) -> str:
    return "/files?path=" + quote(str(path))


def _line(text, href, group, importance, ts, run=False) -> dict:
    href = str(href or "")
    if re.search(r"\.json(?:$|[?#])", href.split("?path=")[-1]):
        href = ""   # never a raw json file: the line keeps its words, the link goes
    return {"text": phrase(text), "href": href, "group": group, "importance": int(importance or 0), "ts": ts or "", "run": bool(run)}


def named_first(text: str, known: set) -> str | None:
    """The registry id the text names first (by position), or None."""
    low, best = (text or "").lower(), None
    for sid in known:
        if sid in ("world", "self", "unfiled"):
            continue
        m = re.search(r"(?<![\w.])" + re.escape(sid.lower()) + r"(?![\w])", low)
        if m and (best is None or (m.start(), -len(sid)) < best[0]):
            best = ((m.start(), -len(sid)), sid)
    return best[1] if best else None


BRIEF_RE = re.compile(r"ops/jobs/briefs/([\w.-]+\.md)")


def _brief_system(world: Path, command: str, known: set, cache: dict) -> str | None:
    m = BRIEF_RE.search(command or "")
    if not m:
        return None
    name = m.group(1)
    if name not in cache:
        try:
            cache[name] = named_first((world / "ops" / "jobs" / "briefs" / name).read_text(errors="replace")[:3000], known)
        except OSError:
            cache[name] = None
    return cache[name]


def _stamp(v) -> str:
    try:
        return datetime.fromtimestamp(int(v), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if v else ""
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _jobs(jobs: list, known: set, filing: dict, world: Path | None = None, job_system: dict | None = None) -> list:
    out, briefs = [], {}
    for j in jobs or []:
        title = str(j.get("title") or j.get("command") or "")
        started, ended = _stamp(j.get("started")), _stamp(j.get("ended"))
        th = str(j.get("thread") or "")
        log = str(j.get("log") or "")
        href = _talk(th) if THREAD_RE.match(th) else (_files(log) if log else "/board")
        sid = str(j.get("system") or "")
        if sid not in known:
            sid = str((job_system or {}).get(str(j.get("id") or "")) or "")
        if sid not in known:
            sid = system_for(title, known, filing)
            if sid == "world" and world is not None:
                sid = _brief_system(world, str(j.get("command") or ""), known, briefs) or "world"
        line = _line(title.split(":", 1)[1] if ":" in title else title, href, "jobs",
                     3 if j.get("ended") is None else 1, ended or started, j.get("ended") is None)
        if j.get("ended") is not None and isinstance(j.get("result"), dict):
            line["result"] = _result(j["result"])
        out.append({"system": sid, "ended": ended, "line": line, "running": j.get("ended") is None})
    return out


def _result(res: dict) -> dict:
    """A finished job's result on its line (JOBCARD-1, 2026-11-13): the first sentence of its final text, its
    exit code, the result file and the files it made as pane links, images marked. The bridge stores the result
    on the job record when the job ends (cc_extras.job_result)."""
    text = re.sub(r"[*_`#>]+", "", str(res.get("text") or "")).strip()
    first = re.split(r"(?<=[.!?])\s|\n", text, maxsplit=1)[0].strip()[:220] if text else ""
    src = str(res.get("source") or "")
    return {"first": first, "rc": res.get("rc"), "href": _files(src) if src else "",
            "files": [{"name": str(f.get("name") or ""), "href": _files(f.get("path") or ""),
                       "image": f.get("kind") == "image"} for f in (res.get("files") or [])[:6]
                      if isinstance(f, dict) and not str(f.get("name") or "").endswith(".json")]}   # never a raw json file


def _court(world: Path, known: set, filing: dict, rows: list | None = None) -> list:
    out = []
    for r in rows if rows is not None else read_tsv(world / "ops" / "inbox" / "rulings.tsv"):
        if r.get("state") != "open":
            continue
        ref = r.get("ref", "")
        href = _talk(ref) if THREAD_RE.match(ref) else "/cc/files/raw/home/hands/out/inbox/index.html"
        out.append({"system": system_for(f"{r.get('title', '')} {r.get('ask', '')}", known, filing, r.get("system", "")),
                    "line": _line(r.get("title"), href, "questions" if r.get("kind") == "question" else "decisions", 2, "")})
    return out


def _thoughts(world: Path, known: set, now: datetime) -> list:
    out = []
    for i in range(THOUGHT_DAYS):
        p = world / "ops" / "chop" / f"{(now - timedelta(days=i)).date()}.json"
        try:
            d = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        for t in d.get("thoughts", []) if isinstance(d, dict) else []:
            sid = str(t.get("system") or "")
            th = str(t.get("thread") or "")
            href = _talk(th) if THREAD_RE.match(th) else _files(world / "ops" / "chop" / f"{p.stem}.md")
            ts = str(t.get("ts") or "")
            out.append({"system": sid if sid in known else "unfiled", "fresh": _recent(ts, NOW_HOURS, now),
                        "line": _line(t.get("text"), href, THOUGHT_GROUP.get(t.get("kind"), "notes"), t.get("importance"), ts)})
    return out


def _next(world: Path, known: set, filing: dict, rows: list | None = None) -> list:
    out = []
    for r in rows if rows is not None else read_tsv(world / "ops" / "next.tsv"):
        if r.get("state") != "candidate":
            continue
        th = r.get("thread", "")
        href = _talk(th) if THREAD_RE.match(th) else _files(world / "ops" / "next.tsv")
        out.append({"system": system_for(r.get("what", ""), known, filing, r.get("system", ""), r.get("repo", "")),
                    "line": _line(r.get("what"), href, "tasks", 1, r.get("ts_utc", ""))})
    return out


def _from_static(static: dict, world: Path, known: set, now: datetime) -> tuple[list, list, list]:
    """The static board's rows (board.json) in the shape the readers above take; each keeps its own filing."""
    court = [{"state": "open", "ref": c.get("thread") or "", "kind": c.get("kind", ""), "title": c.get("title", ""),
              "ask": "", "system": c.get("system", "")} for c in static.get("court") or [] if isinstance(c, dict)]
    thoughts = []
    for t in static.get("thoughts") or []:
        if not isinstance(t, dict):
            continue
        th, ts = str(t.get("thread") or ""), str(t.get("ts") or "")
        sid = str(t.get("system") or "")
        href = _talk(th) if THREAD_RE.match(th) else _files(world / "ops" / "chop")
        thoughts.append({"system": sid if sid in known else "unfiled", "fresh": _recent(ts, NOW_HOURS, now),
                         "line": _line(t.get("text"), href, THOUGHT_GROUP.get(t.get("kind"), "notes"), t.get("importance"), ts)})
    nxt = [{"state": "candidate", "thread": n.get("thread") or "", "what": n.get("what", ""), "ts_utc": n.get("ts", ""),
            "repo": n.get("repo", ""), "system": n.get("system", "")} for n in static.get("next") or [] if isinstance(n, dict)]
    return court, thoughts, nxt


def load_static(path: Path | str | None, cache: dict | None = None) -> dict | None:
    """The owner's static board (board.json), read again only when its mtime moves; None when absent or unreadable."""
    if not path:
        return None
    p = Path(path)
    try:
        mt = p.stat().st_mtime
    except OSError:
        return None
    if cache is not None and cache.get("path") == str(p) and cache.get("mtime") == mt:
        return cache.get("data")
    try:
        d = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    d = d if isinstance(d, dict) else None
    if cache is not None:
        cache.update(path=str(p), mtime=mt, data=d)
    return d


KEEP = 14   # lines sent per group (the poll stays light); the counts are always whole


def _detail(lines: list) -> dict:
    return {"count": len(lines), "lines": lines[:KEEP], "extra": max(0, len(lines) - LINES)}


def board(world: Path | str | None, jobs: list, threads: dict | None = None, now: datetime | None = None,
          static: dict | None = None) -> dict:
    """GET /cc/systems: tiles ordered by agents running, things moving now, then everything known; each tile:
    {id, description, moving, lines (<= 7), more: [{kind, count, lines}], extra, thread,
     counts: {running, done_today, tasks, next}, detail: {<same keys>: {count, lines (<= 7), extra}}}.
    `static`: the owner's board.json, when there is one (see the module note)."""
    now = now or datetime.now(timezone.utc)
    world = Path(world) if world else None
    if world is None or not world.is_dir():
        systems = [{"id": i, "status": "active", "description": d0} for i, d0 in EXTRA]
        world = Path("/nonexistent")
    else:
        systems = load_systems(world)
    known = {s["id"] for s in systems}
    filing = load_filing(world)
    per = {s["id"]: {"run": [], "court": [], "fresh": [], "done": [], "old": [], "next": [], "today": [], "task": []}
           for s in systems}

    def put(sid, bucket, line):
        per.get(sid if sid in per else "world", per.get("world"))[bucket].append(line)

    today = now.strftime("%Y-%m-%d")
    static = static if isinstance(static, dict) and isinstance(static.get("court"), list) else None
    for j in _jobs(jobs, known, filing, world, (static or {}).get("job_system")):
        put(j["system"], "run" if j["running"] else "done", j["line"])
        if not j["running"] and j["ended"][:10] == today:
            put(j["system"], "today", j["line"])
    if static is not None:
        court_rows, thoughts, next_rows = _from_static(static, world, known, now)
    else:
        court_rows, thoughts, next_rows = None, _thoughts(world, known, now), None
    for c in _court(world, known, filing, court_rows):
        put(c["system"], "court", c["line"])
    for t in thoughts:
        put(t["system"], "fresh" if t["fresh"] else "old", t["line"])
        if t["line"]["group"] == "tasks":
            put(t["system"], "task", t["line"])
    for n in _next(world, known, filing, next_rows):
        put(n["system"], "next", n["line"])

    tiles = []
    threads = threads or {}
    for s in systems:
        b = per[s["id"]]
        for k in b:
            b[k].sort(key=lambda x: (x["importance"], x["ts"]), reverse=True)
        moving = len(b["run"]) + len(b["court"]) + len(b["fresh"])
        order = b["run"] + b["court"] + b["fresh"] + b["done"] + b["old"] + b["next"]
        tasks = sorted(b["court"] + b["task"], key=lambda x: (x["importance"], x["ts"]), reverse=True)
        detail = {"running": _detail(b["run"]), "done_today": _detail(b["today"]), "tasks": _detail(tasks),
                  "next": _detail(b["next"])}
        lines, rest = order[:LINES], order[LINES:]
        more = []
        for g in GROUPS:
            items = sorted((x for x in rest if x["group"] == g), key=lambda x: (x["importance"], x["ts"]), reverse=True)
            if items:
                more.append({"kind": g, "count": len(items), "lines": items[:LINES]})
        total = len(order)
        if s["id"] == "unfiled" and not total:
            continue
        tiles.append({"id": s["id"], "status": s.get("status", ""), "description": s.get("description", ""),
                      "moving": moving, "total": total, "lines": lines, "more": more, "extra": len(rest),
                      "thread": threads.get(s["id"]), "detail": detail,
                      "counts": {k: v["count"] for k, v in detail.items()}})
    tiles.sort(key=lambda t: (-t["counts"]["running"], -t["moving"], -t["total"], t["id"]))
    return {"tiles": tiles, "built": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "moving": sum(t["moving"] for t in tiles),
            "running": sum(t["counts"]["running"] for t in tiles), "source": "board.json" if static else "world",
            "static_built": (static or {}).get("built") or None}


# ---------------------------------------------------------------- voice ----

AUDIO_EXT = {"webm", "ogg", "m4a", "mp4", "wav", "mp3", "opus", "weba"}


def voice_name(system: str, filename: str, now: float | None = None) -> str:
    """memo_<system>_<UTC stamp>.<ext>: the memo tape takes a file in in/<date>/ whose name starts with "memo",
    and its clerk reads the name, so the system rides in it."""
    ext = (filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else "webm")
    ext = ext if ext in AUDIO_EXT else "webm"
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now if now is not None else time.time()))
    return f"memo_{system}_{stamp}.{ext}"
