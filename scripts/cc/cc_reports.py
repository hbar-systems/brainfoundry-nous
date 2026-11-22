"""Thread reports (REPORT-1, 2026-11-22): a thread started from another thread's choice button
(mode "agent") reports back. When it finishes a turn, a short card is posted into the PARENT
thread: title, state, the first three lines of the answer, and the child's id so the page can link
to it.

The rule of 2026-10-11 holds (tiles stay in their thread): a card belongs to exactly one parent,
is handed only to a page that names that parent, once, and says which thread it came from. A page
showing any other thread never sees it.

Kept in one small JSON file (links child -> parent, and the cards not yet taken), written with a
temp file and a rename, so a bridge restart between the child's answer and the parent page's next
poll loses nothing. Pure: no network, no bridge imports; tests/test_cc_reports.py runs it on temp dirs.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

STATES = ("done", "asks you", "waits for your yes", "stopped", "failed")
LINES = 3
WIDTH = 200
TTL = 7 * 24 * 3600          # an untaken card is dropped after a week
MAX_CARDS = 200
MAX_LINKS = 500

_BLOCKS = re.compile(r"<(choices|proposal|pane|layout|profile)>.*?(</\1>|\Z)", re.S | re.I)
_COMMENT = re.compile(r"<!--.*?(-->|\Z)", re.S)
_RULE = re.compile(r"^[\s\-=*_|:]+$")          # a rule, a table separator, an empty bullet
_FENCE = re.compile(r"^\s*(```|~~~)")


def known(thread) -> bool:
    """A thread id a card can hang on: a real brain id, not a page's 'new:' placeholder."""
    t = str(thread or "").strip()
    return bool(t) and t != "unknown" and not t.startswith("new:") and len(t) <= 120


def first_lines(text: str, n: int = LINES, width: int = WIDTH) -> list:
    """The first n lines of an answer that say something: markers (choices, proposal, pane), comments,
    rules and code fences are skipped, a heading loses its hashes, a long line is cut with an ellipsis."""
    body = _COMMENT.sub("", _BLOCKS.sub("", str(text or "")))
    out: list = []
    for raw in body.splitlines():
        line = " ".join(raw.split())
        if not line or _RULE.match(line) or _FENCE.match(line):
            continue
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"^>\s?", "", line)
        if not line:
            continue
        if len(line) > width:
            line = line[: width - 1].rstrip() + "…"
        out.append(line)
        if len(out) >= n:
            break
    return out


def state_of(*, error: bool = False, stopped: bool = False, card: dict | None = None, reply: str = "") -> str:
    """One word on how the turn ended, most urgent first."""
    if error:
        return "failed"
    if stopped:
        return "stopped"
    if card and card.get("id") and not card.get("auto"):
        return "waits for your yes"
    if re.search(r"<choices>", str(reply or ""), re.I):
        return "asks you"
    return "done"


def clean_title(title: str | None, label: str | None = None) -> str:
    t = " ".join(str(title or "").split())
    if t.lower().startswith("cc:"):
        t = t[3:].strip()
    t = t or " ".join(str(label or "").split()) or "a thread"
    return t[:120]


class Reports:
    def __init__(self, path, ttl: int = TTL):
        self.path = Path(path)
        self.ttl = ttl
        self.lock = threading.Lock()

    # ---- the file ----
    def _load(self) -> dict:
        try:
            d = json.loads(self.path.read_text())
        except (OSError, ValueError):
            d = {}
        if not isinstance(d, dict):
            d = {}
        links = d.get("links") if isinstance(d.get("links"), dict) else {}
        cards = [c for c in (d.get("cards") or []) if isinstance(c, dict) and c.get("id") and c.get("parent")] \
            if isinstance(d.get("cards"), list) else []
        return {"links": links, "cards": cards}

    def _save(self, d: dict) -> None:
        now = time.time()
        d["cards"] = [c for c in d["cards"] if now - float(c.get("at") or 0) < self.ttl][-MAX_CARDS:]
        if len(d["links"]) > MAX_LINKS:
            keep = sorted(d["links"].items(), key=lambda kv: float((kv[1] or {}).get("at") or 0))[-MAX_LINKS:]
            d["links"] = dict(keep)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(d))
        os.replace(tmp, self.path)

    # ---- links ----
    def link(self, child, parent, label: str = "") -> bool:
        """Remember that `child` was started from `parent`. The first link wins (a thread has one
        origin); a thread is never its own parent, and two threads never report to each other."""
        if not known(child) or not known(parent) or child == parent:
            return False
        with self.lock:
            d = self._load()
            if child in d["links"]:
                return d["links"][child].get("parent") == parent
            if (d["links"].get(parent) or {}).get("parent") == child:
                return False
            d["links"][child] = {"parent": str(parent), "label": " ".join(str(label or "").split())[:120], "at": time.time()}
            self._save(d)
            return True

    def parent_of(self, child) -> str | None:
        if not known(child):
            return None
        with self.lock:
            return (self._load()["links"].get(child) or {}).get("parent") or None

    def unlink(self, child) -> bool:
        with self.lock:
            d = self._load()
            if child not in d["links"]:
                return False
            d["links"].pop(child)
            self._save(d)
            return True

    # ---- cards ----
    def post(self, child, *, title: str | None = None, state: str = "done", reply: str = "",
             parent: str | None = None, label: str = "") -> dict | None:
        """A turn of `child` ended: leave a card for its parent. Returns the card, or None when the
        thread has no parent (an ordinary thread reports to nobody). `parent` is given for a first
        turn that never got a thread id (it failed before it was recorded): the card then has no link.
        One waiting card per child: a newer turn replaces the card the parent has not read yet."""
        with self.lock:
            d = self._load()
            ln = d["links"].get(child) if known(child) else None
            to = (ln or {}).get("parent") or (parent if known(parent) else None)
            if not to or to == child:
                return None
            card = {
                "id": "R" + secrets.token_hex(5),
                "parent": to,
                "child": child if known(child) else None,
                "title": clean_title(title, (ln or {}).get("label") or label),
                "state": state if state in STATES else "done",
                "lines": first_lines(reply),
                "at": time.time(),
            }
            if card["child"]:
                d["cards"] = [c for c in d["cards"] if c.get("child") != card["child"]]
            d["cards"].append(card)
            self._save(d)
            return dict(card)

    def take(self, parent) -> list:
        """The cards waiting for this parent, oldest first; each is handed over once."""
        if not known(parent):
            return []
        with self.lock:
            d = self._load()
            now = time.time()
            mine = [c for c in d["cards"] if c.get("parent") == parent and now - float(c.get("at") or 0) < self.ttl]
            if not mine:
                return []
            d["cards"] = [c for c in d["cards"] if c.get("parent") != parent]
            self._save(d)
            return sorted(mine, key=lambda c: float(c.get("at") or 0))

    def waiting(self) -> dict:
        """{parent: count} of cards not yet taken, for a mark in the thread list."""
        with self.lock:
            out: dict = {}
            now = time.time()
            for c in self._load()["cards"]:
                if now - float(c.get("at") or 0) < self.ttl:
                    out[c["parent"]] = out.get(c["parent"], 0) + 1
            return out
