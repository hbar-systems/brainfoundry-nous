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
# What a registry row is (WALL-3, 2026-11-24, hbar: "dont confuse systems with surfaces"): "work" is an area of work
# you talk into (its own standing thread, jobs, state); "instrument" is a thing you open and use (a page, a tool),
# even when it has a repo; "site" is a public address that shows work. A row without the field is work.
KINDS = ("work", "instrument", "site")
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
    out = [{"id": str(s["id"]), "status": s.get("status", ""), "description": _clean(s.get("description"), 200),
            "kind": s.get("kind") if s.get("kind") in KINDS else "work",
            "domain": next((str(x) for x in (s.get("domains") or []) if isinstance(x, str) and re.match(r"^[a-z0-9.-]+$", x)), "")}
           for s in d.get("systems", []) if isinstance(s, dict) and s.get("id")]
    have = {s["id"] for s in out}
    out += [{"id": i, "status": "active", "description": d0, "kind": "work", "domain": ""} for i, d0 in EXTRA if i not in have]
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


_BRIEF_SYSTEMS: dict = {}   # (world, brief name) -> (mtime, registry size, system): kept between polls (WALL-3)


def _brief_system(world: Path, command: str, known: set, cache: dict) -> str | None:
    """The first registry id a job's brief names. Read once per brief and kept across polls until the brief's mtime
    or the registry's size moves (WALL-3: re-reading every brief made each three-second poll cost over a second)."""
    m = BRIEF_RE.search(command or "")
    if not m:
        return None
    name = m.group(1)
    if name not in cache:
        p = world / "ops" / "jobs" / "briefs" / name
        try:
            mt = p.stat().st_mtime
        except OSError:
            cache[name] = None
            return None
        key = (str(world), name)
        got = _BRIEF_SYSTEMS.get(key)
        if got and got[0] == mt and got[1] == len(known):
            cache[name] = got[2]
        else:
            try:
                cache[name] = named_first(p.read_text(errors="replace")[:3000], known)
            except OSError:
                cache[name] = None
            if len(_BRIEF_SYSTEMS) > 2000:
                _BRIEF_SYSTEMS.clear()
            _BRIEF_SYSTEMS[key] = (mt, len(known), cache[name])
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
        out.append({"system": sid, "ended": ended, "line": line, "running": j.get("ended") is None, "rec": j})
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
        systems = [{"id": i, "status": "active", "description": d0, "kind": "work", "domain": ""} for i, d0 in EXTRA]
        world = Path("/nonexistent")
    else:
        systems = load_systems(world)
    known = {s["id"] for s in systems}
    filing = load_filing(world)
    per = {s["id"]: {"run": [], "court": [], "fresh": [], "done": [], "old": [], "next": [], "today": [], "task": []}
           for s in systems}
    running_recs = {s["id"]: [] for s in systems}

    def put(sid, bucket, line):
        per.get(sid if sid in per else "world", per.get("world"))[bucket].append(line)

    today = now.strftime("%Y-%m-%d")
    static = static if isinstance(static, dict) and isinstance(static.get("court"), list) else None
    kind_of = {s["id"]: s.get("kind", "work") for s in systems}
    for j in _jobs(jobs, known, filing, world, (static or {}).get("job_system")):
        # WALL-3: an instrument or a site is opened, not worked in; a job lands there only when it names that row
        # as its own system, else it goes to the centre (a brief that mentions hbar.ink is not ink's job)
        if kind_of.get(j["system"], "work") != "work" and str(j["rec"].get("system") or "") != j["system"]:
            j["system"] = "world"
        put(j["system"], "run" if j["running"] else "done", j["line"])
        if j["running"]:
            running_recs.get(j["system"] if j["system"] in running_recs else "world", running_recs.get("world", [])).append(j["rec"])
        if not j["running"] and j["ended"][:10] == today:
            put(j["system"], "today", j["line"])
    if static is not None:
        court_rows, thoughts, next_rows = _from_static(static, world, known, now)
    else:
        court_rows, thoughts, next_rows = None, _thoughts(world, known, now), None
    court_n = 0
    for c in _court(world, known, filing, court_rows):
        put(c["system"], "court", c["line"])
        court_n += 1
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
        tiles.append({"id": s["id"], "status": s.get("status", ""), "description": s.get("description", ""), "kind": s.get("kind", "work"),
                      "domain": s.get("domain", ""), "jobs": job_briefs(running_recs[s["id"]], jobs, now, world),
                      "moving": moving, "total": total, "lines": lines, "more": more, "extra": len(rest),
                      "thread": threads.get(s["id"]), "detail": detail,
                      "counts": {k: v["count"] for k, v in detail.items()}})
    tiles.sort(key=lambda t: (-t["counts"]["running"], -t["moving"], -t["total"], t["id"]))
    return {"tiles": tiles, "built": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "moving": sum(t["moving"] for t in tiles),
            "running": sum(t["counts"]["running"] for t in tiles), "source": "board.json" if static else "world",
            "static_built": (static or {}).get("built") or None, "waits": {"court": court_n}}


# ---------------------------------------------------------------- depth (WALL-3) ----
# hbar 2026-11-24 on the orbit: "will i be satisfied with the number of information i can get about the system (and
# talkign to it: ex: how many jobs are going, maybe agentic substructure of each job or info, clear summary, this
# thing too [the thread tree] ... but like everything is hidden, and i can gain access some easy way WITHOUT
# interfering with production and the main focus". The wall's quiet layer reads these; every one is pure and cheap.

TREE_RE = re.compile(r"<tree>\s*([{\[][\s\S]*?)\s*</tree>")
TREE_MAX_BYTES = 64 * 1024
SUMMARY_MAX = 220
_BRIEF_HEADS: dict = {}     # brief name -> (mtime, first 3000 chars): the waiter search reads a brief once


def _sentence(text: str, n: int = SUMMARY_MAX) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", str(text or ""))        # [words](link) -> words
    s = re.sub(r"[*_`]+", "", s)
    s = re.sub(r"^\s*(?:[-+>]|\d+[.)])\s+", "", s)
    s = _clean(s)
    first = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'])", s, maxsplit=1)[0]
    return _clean(first, n)


def first_line(text: str) -> str:
    """The first sentence of an answer that says something: no heading, fence, table, rule or block marker."""
    fence = False
    for ln in str(text or "").splitlines():
        t = ln.strip()
        if t.startswith("```"):
            fence = not fence
            continue
        if fence or not t or t.startswith(("#", "|", "<", "---", "***")):
            continue
        out = _sentence(t)
        if out:
            return out
    return ""


def card_line(text: str) -> str:
    """Where a system stands, from its state card (a markdown file): a "Goal:", "State:", "Now:" or "Scope:" line
    first, else the first prose line after the title. Front matter and headings are skipped."""
    body = str(text or "")
    if body.startswith("---"):
        end = body.find("\n---", 3)
        body = body[end + 4:] if end > 0 else body
    m = re.search(r"^\s*(?:[-*]\s*)?(?:\*\*)?(?:Now|State|Goal|Scope|Where it stands)(?:\*\*)?:\s*(.+)$", body, re.M | re.I)
    if m:
        return _sentence(m.group(1))
    return first_line(body)


def state_cards(world: Path | None) -> dict:
    """The owner's map system -> state card, <world>/ops/wall/states.json {"states": {"<system>": "<path in world>"}}.
    Paths stay inside the world; anything else is dropped."""
    if world is None:
        return {}
    try:
        d = json.loads((Path(world) / "ops" / "wall" / "states.json").read_text())
    except (OSError, ValueError):
        return {}
    out = {}
    for sid, rel in ((d or {}).get("states") or {}).items() if isinstance(d, dict) else ():
        if isinstance(sid, str) and ID_RE.match(sid) and isinstance(rel, str) and rel and not rel.startswith("/") \
                and ".." not in Path(rel).parts:
            out[sid] = rel
    return out


def last_tree(messages) -> dict | None:
    """The last <tree> block the thread's answers carry (newest answer first; within one, its last block that
    parses), as the raw object the page's ui/lib/tree.js cleans. None when there is none or it is too big."""
    for m in reversed(messages or []):
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        text = str(m.get("content") or "")
        if "<tree>" not in text:
            continue
        for raw in reversed(TREE_RE.findall(text)):
            if len(raw) > TREE_MAX_BYTES:
                continue
            try:
                v = json.loads(raw)
            except ValueError:
                continue
            if isinstance(v, list):
                v = {"nodes": v}
            if isinstance(v, dict) and isinstance(v.get("nodes"), list) and v["nodes"]:
                return v
    return None


def tree_size(tree) -> int:
    n = 0
    stack = list((tree or {}).get("nodes") or []) if isinstance(tree, dict) else []
    while stack and n < 1000:
        x = stack.pop()
        if isinstance(x, dict):
            n += 1
            kids = x.get("children")
            stack.extend(kids if isinstance(kids, list) else [])
    return n


def brief_of(command: str) -> str:
    m = BRIEF_RE.search(command or "")
    return m.group(1) if m else ""


def _brief_head(world: Path | None, name: str) -> str:
    if not name or world is None:
        return ""
    p = Path(world) / "ops" / "jobs" / "briefs" / name
    try:
        mt = p.stat().st_mtime
    except OSError:
        return ""
    got = _BRIEF_HEADS.get(name)
    if got and got[0] == mt:
        return got[1]
    try:
        head = p.read_text(errors="replace")[:3000]
    except OSError:
        head = ""
    if len(_BRIEF_HEADS) > 300:
        _BRIEF_HEADS.clear()
    _BRIEF_HEADS[name] = (mt, head)
    return head


def _mentions(text: str, tag: str, jid: str) -> bool:
    if jid and jid in (text or ""):
        return True
    return bool(tag) and re.search(r"(?<![A-Z0-9-])" + re.escape(tag) + r"(?![0-9])", text or "") is not None


def waiter_of(rec: dict, jobs: list, world: Path | None = None) -> dict | None:
    """The running job that waits for this one (to gate and push it): another running job whose title or brief
    names this job's tag or id; one that pushes or waits is preferred."""
    tag, jid = _tag(str(rec.get("title") or "")), str(rec.get("id") or "")
    best = None
    for o in jobs or []:
        if not isinstance(o, dict) or o.get("ended") is not None or str(o.get("id") or "") == jid:
            continue
        otitle = str(o.get("title") or "")
        if _tag(otitle) == tag and tag:
            continue
        text = otitle + "\n" + _brief_head(world, brief_of(str(o.get("command") or "")))
        if not _mentions(text, tag, jid):
            continue
        rank = 0 if re.search(r"push|wait|gate", otitle, re.I) else 1
        if best is None or rank < best[0]:
            best = (rank, {"id": str(o.get("id") or ""), "title": _clean(otitle, 120)})
    return best[1] if best else None


def job_briefs(recs: list, jobs: list, now: datetime, world: Path | None = None) -> list:
    """The running jobs of one system for the depth layer: id, title, minutes running, its brief, the waiter."""
    out = []
    t_now = now.timestamp()
    for r in sorted(recs or [], key=lambda x: x.get("started") or 0):
        try:
            mins = max(0, int((t_now - float(r.get("started"))) // 60))
        except (TypeError, ValueError):
            mins = None
        out.append({"id": str(r.get("id") or ""), "title": _clean(r.get("title") or r.get("command"), 120),
                    "tag": _tag(str(r.get("title") or "")), "mins": mins, "brief": brief_of(str(r.get("command") or "")),
                    "waiter": waiter_of(r, jobs, world), "thread": str(r.get("thread") or "") if THREAD_RE.match(str(r.get("thread") or "")) else ""})
    return out


def _tail_lines(path, n: int = 3, nbytes: int = 4096) -> list:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - nbytes))
            raw = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = [_clean(x, 160) for x in raw.splitlines()]
    lines = [x for x in lines if x and not re.match(r"^# J\d+ |^# ", x)]
    return lines[-n:]


def job_steps(log: str, out_file: str, out_dir: Path | None, brief: str, started, n_files: int = 4) -> dict:
    """What a running job shows of its inside: the last lines of its log and of the file it writes to, and the
    files it made so far in its own folder out/<date>/<name>/ (the brief's name without the date)."""
    steps = _tail_lines(log) if log else []
    if out_file:
        steps = (steps + _tail_lines(out_file))[-3:]
    made = []
    slug = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", brief or "").removesuffix(".md")
    if out_dir and slug and ID_RE.match(slug):
        try:
            lo = float(started or 0)
        except (TypeError, ValueError):
            lo = 0.0
        day = time.strftime("%Y-%m-%d", time.gmtime(lo or time.time()))
        d = Path(out_dir) / day / slug
        try:
            got = [(e.name, e.stat().st_mtime) for e in os.scandir(d) if e.is_file(follow_symlinks=False) and not e.name.startswith(".")]
        except OSError:
            got = []
        got = [g for g in got if g[1] >= lo - 2]
        got.sort(key=lambda g: -g[1])
        made = [g[0] for g in got[:n_files]]
    return {"steps": steps, "made": made}


def due_today(tasks, today: str) -> int:
    """Open tasks due today or before (an overdue task is due today too); today is YYYY-MM-DD."""
    n = 0
    for t in tasks or []:
        if isinstance(t, dict) and not t.get("done") and isinstance(t.get("due"), str) and t["due"][:10] and t["due"][:10] <= today:
            n += 1
    return n


# ---------------------------------------------------------------- voice ----

AUDIO_EXT = {"webm", "ogg", "m4a", "mp4", "wav", "mp3", "opus", "weba"}


def voice_name(system: str, filename: str, now: float | None = None) -> str:
    """memo_<system>_<UTC stamp>.<ext>: the memo tape takes a file in in/<date>/ whose name starts with "memo",
    and its clerk reads the name, so the system rides in it."""
    ext = (filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else "webm")
    ext = ext if ext in AUDIO_EXT else "webm"
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now if now is not None else time.time()))
    return f"memo_{system}_{stamp}.{ext}"
