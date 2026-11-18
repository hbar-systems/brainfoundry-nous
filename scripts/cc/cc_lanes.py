"""Production lanes and the idle archive for the thread list (THREADS-1, 2026-11-18).

hbar 2026-11-18: "we need better archival of the threads, as well as human-friendly-visual (coloring, clear
lighting up whats active in a systematic creative color-code scheme) + different color of production but also
clear to understand."

Two things, both pure apart from the files they are handed:

  lane_of(...)   the production a thread belongs to, one of LANES (film, music, brains, sites, science, ops) or ""
                 when nothing says. In order: the owner's own words (<world>/ops/threads/lanes.json:
                 {"systems": {"<registry id>": "<lane>"}, "keywords": [["word", "<lane>"]]}), the thread's
                 standing system (the `system` field of a systems-board thread), a registry id
                 (<world>/registry/systems.json) named in the title, mapped through the id and its description,
                 then the plain words of the title. The console colours a small mark by it; the colours live in
                 ui/lib/threadcolor.js, the words here.
  idle_sweep(...) threads quiet for ARCHIVE_IDLE_DAYS leave the main list by themselves: `archived` true with
                 `archived_by` "idle" and `archived_at`. Never a pinned thread, one answering, one waiting, or one
                 with a job of its own running. A thread the owner brings back by hand carries `kept_at`, and the
                 days count from then. Nothing is ever deleted; a new turn brings an archived thread back
                 (unarchive_on_turn).
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

LANES = ("film", "music", "brains", "sites", "science", "ops")

# Plain words per lane, matched as whole words in lower case. Generic on purpose: an owner's own names go in
# <world>/ops/threads/lanes.json, never in this template.
WORDS = {
    "film": ("film", "video", "videos", "movie", "clip", "clips", "reel", "reels", "footage", "animatic", "storyboard",
             "camera", "shot", "shots", "media", "vision", "youtube"),
    "music": ("music", "track", "tracks", "song", "songs", "beat", "beats", "loop", "loops", "stem", "stems", "mix",
              "master", "album", "ableton", "melody", "vocal", "vocals", "audio", "sound", "rap", "orfeo", "dj"),
    "brains": ("brain", "brains", "member", "members", "nous", "foundry", "brainfoundry", "spoke", "fleet", "persona",
               "onboarding", "friend", "friends", "seat", "codex", "reasoner"),
    "sites": ("site", "sites", "page", "pages", "website", "web", "front", "landing", "vercel", "domain", "domains",
              "dns", "blog", "css", "ui", "console", "design", "favicon"),
    "science": ("science", "research", "paper", "papers", "study", "eval", "evals", "experiment", "experiments",
                "bio", "health", "psychology", "model", "models", "training", "forecast", "coherence",
                "harmonics", "mirror", "lesson", "learning", "university"),
    "ops": ("ops", "steward", "ledger", "deploy", "deploys", "push", "pushes", "infra", "server", "servers", "box",
            "boxes", "backup", "backups", "security", "cost", "costs", "finance", "economy", "job",
            "jobs", "queue", "audit", "court", "inbox", "rulings", "organizer", "threads"),
}
_WORD_RE = re.compile(r"[a-z0-9]+")
ARCHIVE_IDLE_DAYS = 3.0


def _words(text: str) -> list:
    return _WORD_RE.findall(str(text or "").lower())


def lane_of_words(text: str) -> str:
    """The lane the most words of `text` name; ties go to the first lane in LANES order. "" when none."""
    best, score = "", 0
    words = _words(text)
    for lane in LANES:
        n = sum(1 for w in words if w in WORDS[lane])
        if n > score:
            best, score = lane, n
    return best


def load_owner(world) -> dict:
    """<world>/ops/threads/lanes.json, checked: unknown lanes dropped. Missing or broken: empty."""
    out = {"systems": {}, "keywords": []}
    if not world:
        return out
    try:
        d = json.loads((Path(world) / "ops" / "threads" / "lanes.json").read_text())
    except (OSError, ValueError):
        return out
    if not isinstance(d, dict):
        return out
    for k, v in (d.get("systems") or {}).items():
        if str(v) in LANES:
            out["systems"][str(k)] = str(v)
    for p in d.get("keywords") or []:
        if isinstance(p, (list, tuple)) and len(p) == 2 and str(p[1]) in LANES and str(p[0]).strip():
            out["keywords"].append((str(p[0]).strip().lower(), str(p[1])))
    return out


def load_registry(world) -> dict:
    """registry id -> lane, from the id and description of each system in <world>/registry/systems.json."""
    if not world:
        return {}
    try:
        d = json.loads((Path(world) / "registry" / "systems.json").read_text())
    except (OSError, ValueError):
        return {}
    systems = d.get("systems") if isinstance(d, dict) else d
    out = {}
    for s in systems if isinstance(systems, list) else []:
        if not isinstance(s, dict) or not s.get("id"):
            continue
        sid = str(s["id"])
        # the id's own words count twice: hbar.music is music whatever its description says
        lane = lane_of_words(sid.replace(".", " ")) or lane_of_words(s.get("description") or "")
        if lane:
            out[sid] = lane
    return out


class Lanes:
    """The owner file and the registry, read again when either file's mtime moves (the list is polled)."""

    def __init__(self, world):
        self.world = str(world or "")
        self._stamp = None
        self.owner = {"systems": {}, "keywords": []}
        self.registry = {}

    def _fresh(self):
        if not self.world:
            return
        stamp = []
        for rel in (("ops", "threads", "lanes.json"), ("registry", "systems.json")):
            try:
                stamp.append(Path(self.world, *rel).stat().st_mtime)
            except OSError:
                stamp.append(None)
        if stamp != self._stamp:
            self._stamp = stamp
            self.owner = load_owner(self.world)
            self.registry = load_registry(self.world)

    def of(self, title: str = "", system: str = "") -> str:
        self._fresh()
        low = str(title or "").lower()
        for word, lane in self.owner["keywords"]:
            if word in low:
                return lane
        if system:
            lane = self.owner["systems"].get(system) or self.registry.get(system)
            if lane:
                return lane
        # the longest registry id named in the title wins (hbar.music.video before hbar.music)
        for sid in sorted(set(self.owner["systems"]) | set(self.registry), key=len, reverse=True):
            if re.search(r"(?<![a-z0-9.])" + re.escape(sid.lower()) + r"(?![a-z0-9])", low):
                return self.owner["systems"].get(sid) or self.registry.get(sid) or ""
        return lane_of_words(re.sub(r"^cc:\s*", "", low))


def _ts(s) -> float | None:
    try:
        return datetime.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def idle_sweep(items: list, now: float | None = None, days: float = ARCHIVE_IDLE_DAYS,
               busy: set | frozenset = frozenset()) -> int:
    """Archive in place the threads quiet for `days` (see the module text). `busy`: thread ids answering,
    waiting or with a job running. Returns how many were archived; 0 days turns the sweep off."""
    if not days or days <= 0:
        return 0
    now = time.time() if now is None else now
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    n = 0
    for th in items:
        if th.get("archived") or th.get("pinned") or th.get("brain") in busy:
            continue
        quiet = max([t for t in (_ts(th.get("last")), _ts(th.get("started")), _ts(th.get("kept_at"))) if t] or [now])
        if now - quiet >= days * 86400:
            th["archived"] = True
            th["archived_by"] = "idle"
            th["archived_at"] = stamp
            n += 1
    return n


def set_archived(th: dict, archived: bool, now: float | None = None) -> None:
    """The archive press on a row: by hand either way. Brought back by hand, the idle days count from now."""
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None else now))
    if archived:
        th["archived"] = True
        th["archived_by"] = "hand"
        th["archived_at"] = stamp
    else:
        th["archived"] = False
        th.pop("archived_by", None)
        th.pop("archived_at", None)
        th["kept_at"] = stamp


def unarchive_on_turn(th: dict) -> bool:
    """A new turn in an archived thread brings it back. True when it did."""
    if not th.get("archived"):
        return False
    th["archived"] = False
    th.pop("archived_by", None)
    th.pop("archived_at", None)
    return True
