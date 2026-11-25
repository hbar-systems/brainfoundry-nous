"""cc_listen.py: /listen, the owner's own listening played back in the console (LISTEN-1, 2026-11-24).

The owner asked to hear their own playlists and their own tracks while they work in the console. This module is
the bridge side: it reads the listening tables the brain's world already holds and answers stations; the console
plays them (ui/lib/listen.js, one audio owner for the whole console; ui/pages/listen.js).

Where it reads (this template names no person; everything comes from the world):

  <world>/systems/*/ops/listening/   the newest of each, by the date in the file name (YYYY-MM-DD_):
    *_playlists-all.tsv    account, playlist_id, title, created, privacy, item_count, fetched
    *_playlist-items.tsv   account, playlist_id, playlist_title, video_id, title, channel, artist_guess, ..., duration_s
    *_youtube-likes.tsv    source, video_id, title, channel, artist_guess, ..., duration_s   (the likes, newest first)
    *_listening.tsv        video_id, title, channel, artist_guess, ..., music, own, ..., styles, liked, ...
    *_taste.md             the taste note; its "## Genres" numbered list orders "mixed by the brain"
    own.tsv                id, title, artist, file (a path under the world), duration_s: the owner's own tracks
    listen.json            optional: {"first": ["beats", ...]} title words whose playlists come first
  <bridge state>/listening/listening.tsv   a member's own read (cc_listening.py), when the world holds none

Stations: the "first" playlists (newest first), the likes, the owner's own tracks, "mixed by the brain", then
every other playlist (newest first). A YouTube item is {k: "yt", id: <video id>}: the console plays it through the
official embed player only (nothing downloaded or rehosted; an item whose embedding is off is skipped there and
counted). An own track is {k: "file", n: <its id>}: GET /cc/listen/file?n=<id> streams the file named in own.tsv,
and only those files (never a path from the request).

The play log: POST /cc/listen/event appends one row per event (start, finish, skip, blocked, pause) to
<log> (CC_LISTEN_LOG, default <out>/listen/plays.tsv), UTC ISO times, columns in LOG_COLUMNS. It stays on the box;
the world's own nightly script may copy it into a private record. Standard library only.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import random
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

VID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
OWN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
DATED_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)$")
STATION_RE = re.compile(r"^(pl:[A-Za-z0-9_-]{2,64}|likes|own|mix)$")
EVENTS = ("start", "finish", "skip", "blocked", "pause")
LOG_COLUMNS = ("ts_utc", "event", "station_id", "station", "kind", "item_id", "title", "artist",
               "position_s", "duration_s", "reason", "browser_tz", "tab")
MAX_ITEMS = 400          # a station is cut here (the longest playlist on hbar's world has 129)
MIX_LEN = 240            # "mixed by the brain": this many items
CACHE_S = 30.0
MAX_ROWS_DAY = 5000      # the log refuses past this many rows in a UTC day (a stuck page cannot fill the disk)
STOP = {"and", "the", "with", "from", "into", "over", "smaller", "videos", "video", "songs", "music", "named",
        "short", "most", "first", "their", "touches", "colour", "color", "style", "lists", "old", "rebuilt",
        "playlist", "minute", "long", "calm"}


def _cell(v, n: int = 300) -> str:
    return " ".join(str(v or "").split())[:n]


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if 0 <= f < 10 ** 7 else None


def _rows(p: Path | None) -> list[dict]:
    if not p:
        return []
    try:
        with open(p, newline="", encoding="utf-8") as f:
            return list(csv.DictReader((ln for ln in f if not ln.startswith("#")), delimiter="\t"))
    except (OSError, csv.Error, UnicodeDecodeError):
        return []


def _newest(dirs: list[Path], suffix: str) -> Path | None:
    """The newest <date>_<...><suffix> across the listening folders (date in the name, then the name)."""
    best = None
    for d in dirs:
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for n in names:
            m = DATED_RE.match(n)
            if m and n.endswith(suffix) and (d / n).is_file():
                key = (m.group(1), n)
                if best is None or key > best[0]:
                    best = (key, d / n)
    return best[1] if best else None


def _yt(r: dict) -> dict | None:
    vid = (r.get("video_id") or "").strip()
    if not VID_RE.match(vid):
        return None
    it = {"k": "yt", "id": vid, "title": _cell(r.get("title"), 200),
          "artist": _cell(r.get("artist_guess") or r.get("channel"), 120)}
    d = _num(r.get("duration_s"))
    if d:
        it["dur"] = int(d)
    return it


def _dedupe(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for it in items:
        key = (it["k"], it.get("id") or it.get("n"))
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out[:MAX_ITEMS]


def taste_genres(text: str) -> list[dict]:
    """The numbered list under a '## Genres' heading of a taste note: [{name, words}] in its order."""
    out, on = [], False
    for ln in (text or "").splitlines():
        s = ln.strip()
        if s.startswith("## "):
            on = s[3:].lower().startswith("genre")
            continue
        m = re.match(r"^\d+\.\s+(.*)$", s) if on else None
        if not m:
            continue
        body = re.sub(r"\(.*?\)", " ", m.group(1))
        head = body.split(":", 1)[0]
        body = re.split(r"[.;](?:\s|$)", body, maxsplit=1)[0]          # the genre and its kinds, not the prose after
        words = []
        for w in re.findall(r"[^\W\d_]{3,}", body.lower()):
            w = w[:-1] if w.endswith("s") and len(w) > 3 else w   # beats -> beat, remixes -> remixe -> stem below
            w = w[:-1] if w.endswith("e") and w.startswith("remix") else w
            if w not in STOP and w not in words:
                words.append(w)
        if words:
            out.append({"name": _cell(head, 60), "words": words[:24]})
    return out[:12]


def mix(records: list[dict], genres: list[dict], day: str) -> list[dict]:
    """Mixed by the brain: the owner's music records grouped by the first taste genre whose words they carry
    (styles first, else the title), then taken in the note's order, 3 of the first genre, 2 of the second and
    1 of each other per round, until MIX_LEN. Liked items lead inside a genre; the rest are shuffled with the
    UTC day as the seed, so the mix changes once a day and is the same all day."""
    buckets: list[list[tuple]] = [[] for _ in genres]
    rnd = random.Random(day)
    for r in records:
        if (r.get("music") or "").strip() not in ("yes", "likely"):
            continue
        it = _yt(r)
        if not it:
            continue
        styles = " ".join(s.strip().lower() for s in (r.get("styles") or "").split(","))
        title = (r.get("title") or "").lower()
        for i, g in enumerate(genres):
            if any(w in styles for w in g["words"]) or any(re.search(rf"\b{re.escape(w)}", title) for w in g["words"]):
                liked = (r.get("liked") or "").strip() == "yes"
                buckets[i].append((0 if liked else 1, rnd.random(), it))
                break
    for b in buckets:
        b.sort(key=lambda t: (t[0], t[1]))
    queues = [[t[2] for t in b] for b in buckets]
    weights = [3, 2] + [1] * max(0, len(queues) - 2)
    out: list[dict] = []
    while len(out) < MIX_LEN and any(queues):
        for q, w in zip(queues, weights):
            for _ in range(w):
                if q:
                    out.append(q.pop(0))
    return _dedupe(out)[:MIX_LEN]


class Listen:
    def __init__(self, world: str | None, state_dir: str | Path, log: str | Path):
        self.world = Path(world).resolve() if world and Path(world).is_dir() else None
        self.state_dir = Path(state_dir)
        self.log = Path(log)
        self._lock = threading.Lock()
        self._cache: tuple[float, dict] | None = None
        self._day_rows: dict[str, int] = {}

    # ---- reading -------------------------------------------------------------------------------------------------
    def _dirs(self) -> list[Path]:
        out = []
        if self.world:
            sysdir = self.world / "systems"
            try:
                for s in sorted(os.listdir(sysdir)):
                    d = sysdir / s / "ops" / "listening"
                    if d.is_dir():
                        out.append(d)
            except OSError:
                pass
        return out

    def _load(self) -> dict:
        now = time.time()
        if self._cache and now - self._cache[0] < CACHE_S:
            return self._cache[1]
        dirs = self._dirs()
        lists = _rows(_newest(dirs, "_playlists-all.tsv"))
        items = _rows(_newest(dirs, "_playlist-items.tsv"))
        likes = _rows(_newest(dirs, "_youtube-likes.tsv"))
        records = _rows(_newest(dirs, "_listening.tsv"))
        if not records:                                  # a member's own read (cc_listening.py)
            records = _rows(self.state_dir / "listening" / "listening.tsv")
        taste_p = _newest(dirs, "_taste.md")
        try:
            taste = taste_p.read_text(encoding="utf-8")[:200_000] if taste_p else ""
        except OSError:
            taste = ""
        first: list[str] = []
        own: list[dict] = []
        own_files: dict[str, Path] = {}
        for d in dirs:
            try:
                cfg = json.loads((d / "listen.json").read_text(encoding="utf-8"))
                first += [w.lower() for w in cfg.get("first", []) if isinstance(w, str) and 0 < len(w) < 40]
            except (OSError, ValueError, AttributeError):
                pass
            for r in _rows(d / "own.tsv"):
                n = (r.get("id") or "").strip()
                p = self._world_file(r.get("file"))
                if OWN_ID_RE.match(n) and p and n not in own_files:
                    own_files[n] = p
                    it = {"k": "file", "n": n, "title": _cell(r.get("title"), 200), "artist": _cell(r.get("artist"), 120)}
                    dur = _num(r.get("duration_s"))
                    if dur:
                        it["dur"] = int(dur)
                    own.append(it)

        by_pl: dict[str, list[dict]] = {}
        for r in items:
            it = _yt(r)
            pid = (r.get("playlist_id") or "").strip()
            if it and re.match(r"^[A-Za-z0-9_-]{2,64}$", pid):
                by_pl.setdefault(pid, []).append(it)
        pls = []
        for r in lists:
            pid = (r.get("playlist_id") or "").strip()
            if pid not in by_pl:
                continue
            title = _cell(r.get("title"), 120) or pid
            word = (title.split() or [""])[0].lower()
            pls.append({"id": f"pl:{pid}", "name": title, "kind": "playlist", "made": _cell(r.get("created"), 10),
                        "first": any(word.startswith(f) for f in first), "items": _dedupe(by_pl[pid])})
        pls.sort(key=lambda s: s["made"], reverse=True)

        like_items = _dedupe([i for i in (_yt(r) for r in likes) if i])
        if not like_items:
            like_items = _dedupe([i for r in records if (r.get("liked") or "").strip() == "yes" for i in [_yt(r)] if i])
        genres = taste_genres(taste)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        mix_items = mix(records, genres, day) if genres else []

        stations = [s for s in pls if s["first"]]
        if like_items:
            stations.append({"id": "likes", "name": "my likes", "kind": "likes", "items": like_items})
        if own:
            stations.append({"id": "own", "name": "my own tracks", "kind": "own", "items": own[:MAX_ITEMS]})
        if mix_items:
            stations.append({"id": "mix", "name": "mixed by the brain", "kind": "mix", "items": mix_items,
                             "note": "in the order of your taste note: " + ", ".join(g["name"].lower() for g in genres[:6])})
        stations += [s for s in pls if not s["first"]]
        data = {"stations": stations, "own_files": own_files,
                "from": [str(p.relative_to(self.world)) if self.world else str(p) for p in dirs]}
        self._cache = (now, data)
        return data

    def _world_file(self, raw) -> Path | None:
        """A file under the world, symlinks followed, or None."""
        if not self.world or not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
            return None
        try:
            p = (self.world / raw.strip()).resolve()
        except (OSError, RuntimeError):
            return None
        if self.world not in p.parents or not p.is_file():
            return None
        return p

    # ---- answers -------------------------------------------------------------------------------------------------
    def state(self) -> dict:
        d = self._load()
        st = [{k: s[k] for k in ("id", "name", "kind") if k in s} | {"count": len(s["items"]), **({"note": s["note"]} if s.get("note") else {}),
              **({"first": True} if s.get("first") else {})} for s in d["stations"]]
        if not st:
            return {"ok": True, "stations": [], "why": "this brain's world holds no listening tables yet "
                    "(systems/<system>/ops/listening/, or Bring your listening on the home page)"}
        return {"ok": True, "stations": st, "from": d["from"]}

    def station(self, sid) -> tuple[int, dict]:
        if not isinstance(sid, str) or not STATION_RE.match(sid):
            return 400, {"ok": False, "error": "which station?"}
        for s in self._load()["stations"]:
            if s["id"] == sid:
                return 200, {"ok": True, "id": s["id"], "name": s["name"], "kind": s["kind"], "items": s["items"]}
        return 404, {"ok": False, "error": "no such station on this brain"}

    def file_for(self, n) -> Path | None:
        if not isinstance(n, str) or not OWN_ID_RE.match(n):
            return None
        return self._load()["own_files"].get(n)

    def serve(self, handler, n, files_cls) -> None:
        p = self.file_for(n)
        if p is None:
            body = json.dumps({"error": "no such track"}).encode()
            handler.send_response(404)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
            return
        files_cls({"listen": str(p.parent)}).serve(handler, str(p))

    # ---- the play log --------------------------------------------------------------------------------------------
    def event(self, body) -> tuple[int, dict]:
        b = body if isinstance(body, dict) else {}
        ev = b.get("event")
        if ev not in EVENTS:
            return 400, {"ok": False, "error": "event is one of " + ", ".join(EVENTS)}
        sid = b.get("station")
        if not isinstance(sid, str) or not STATION_RE.match(sid):
            return 400, {"ok": False, "error": "which station?"}
        kind = b.get("kind")
        item = str(b.get("item") or "")
        if kind == "yt":
            if not VID_RE.match(item):
                return 400, {"ok": False, "error": "not a video id"}
        elif kind == "file":
            if not OWN_ID_RE.match(item):
                return 400, {"ok": False, "error": "not a track id"}
        else:
            return 400, {"ok": False, "error": "kind is yt or file"}
        name = next((s["name"] for s in self._load()["stations"] if s["id"] == sid), "")
        if not name:
            return 404, {"ok": False, "error": "no such station on this brain"}
        now = datetime.now(timezone.utc)
        day = now.strftime("%Y-%m-%d")
        pos, dur = _num(b.get("position_s")), _num(b.get("duration_s"))
        tz = b.get("tz") if isinstance(b.get("tz"), str) and re.match(r"^[A-Za-z_]+(/[A-Za-z0-9_+-]+){0,2}$", b.get("tz") or "") else ""
        row = {"ts_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "event": ev, "station_id": sid, "station": name, "kind": kind,
               "item_id": item, "title": _cell(b.get("title"), 200), "artist": _cell(b.get("artist"), 120),
               "position_s": f"{pos:.1f}" if pos is not None else "", "duration_s": f"{dur:.1f}" if dur is not None else "",
               "reason": _cell(b.get("reason"), 40), "browser_tz": tz,
               "tab": b.get("tab") if b.get("tab") in ("visible", "hidden") else ""}
        with self._lock:
            n = self._day_rows.get(day)
            if n is None:
                n = self._count_day(day)
            if n >= MAX_ROWS_DAY:
                return 429, {"ok": False, "error": f"more than {MAX_ROWS_DAY} plays logged today"}
            self.log.parent.mkdir(parents=True, exist_ok=True)
            new = not self.log.exists() or self.log.stat().st_size == 0
            buf = io.StringIO()
            w = csv.writer(buf, delimiter="\t", lineterminator="\n")
            if new:
                w.writerow(LOG_COLUMNS)
            w.writerow([row[c].replace("\t", " ") for c in LOG_COLUMNS])
            with open(self.log, "a", encoding="utf-8") as f:
                f.write(buf.getvalue())
            self._day_rows = {day: n + 1}
        return 200, {"ok": True}

    def _count_day(self, day: str) -> int:
        try:
            with open(self.log, encoding="utf-8") as f:
                return sum(1 for ln in f if ln.startswith(day))
        except OSError:
            return 0


def digest(items: list[dict]) -> str:
    """A short fingerprint of a station's order (tests and the record use it to say 'same order')."""
    return hashlib.sha256(json.dumps([i.get("id") or i.get("n") for i in items]).encode()).hexdigest()[:12]
