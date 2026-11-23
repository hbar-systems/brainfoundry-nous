"""Talk in place (INLINE-1, 2026-11-23): a side conversation bound to one item on a page.

hbar, on the tasks court page and the tree cards: "I don't like that when you press talk it goes to a new
thread. I want there to be an item like a note where I can either make a question, a clarification or send
an agent right there and then. I don't want to leave this page ... when it's ready I can click, it will open
and I can read it and then either continue ... if I need to send agents they go get it done and then I stay
on this page and see it when they're done. I also want to be notified about all this."

A side is keyed by the item it hangs on (`key`, chosen by the page: "court-tasks:T123", "tree:<thread>:<node>").
The first turn carries the item's title, text and link as context; the brain thread it opens is the side's
own and is kept out of the thread list. Its answers come back into the side, marked ready (a dot) until the
owner opens them. "send an agent" is a turn in the same side with an agent's instruction; its report card
also lands in the home thread's log (REPORT-1 + the card log), and a job that turn starts lands in the side.

Presence: pages say the owner is looking (`seen`); an answer that comes while nobody looked for over five
minutes is announced on Telegram by its title only (the bridge does the sending).

One small JSON file, temp file and rename. Pure: no network, no bridge imports; tests/test_cc_sides.py.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

KEY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/#@-]{0,159}")
MODES = ("ask", "agent")
MESSAGE_MAX = 4000
CONTEXT_MAX = 2000           # the item's text carried on the first turn
TURNS_MAX = 40
MAX_SIDES = 500
TTL = 60 * 24 * 3600
STALE = 30 * 60              # a turn "working" this long was lost (a bridge restart); the next press may start again
AWAY = 5 * 60                # Telegram only when no page reported the owner for this long
STATES = ("idle", "running", "waiting", "ready", "failed")

AGENT_LINE = ("(Send an agent. Do this now with your tools: for anything longer than a few minutes start a cc-job "
              "so it shows as a card; then say in a few lines what was done and link the result. Same posture and "
              "cards as a typed turn.)")


def clean_key(key) -> str | None:
    k = str(key or "").strip()
    return k if KEY_RE.fullmatch(k) else None


def _one_line(s, n: int) -> str:
    return " ".join(str(s or "").split())[:n]


def _link(s) -> str:
    """A link the side may carry: a console path or an https address, nothing else (no javascript:, no data:)."""
    t = str(s or "").strip()[:500]
    return t if (t.startswith("/") and not t.startswith("//")) or t.startswith("https://") else ""


def prompt(side: dict, message: str, mode: str) -> str:
    """The text the reasoner gets. The first turn names the item; later turns are the owner's words."""
    head = []
    if not side.get("thread"):
        ctx = [f"(A note on an item, sent in place from {side.get('page') or 'a console page'}."]
        ctx.append(f" Item: {side.get('title') or side['key']}.")
        if side.get("text"):
            ctx.append(f" Item text: {side['text']}")
        if side.get("link"):
            ctx.append(f" Link: {side['link']}")
        ctx.append(" Answer short; the answer shows in a small box on that page.)")
        head.append("".join(ctx))
    if mode == "agent":
        head.append(AGENT_LINE)
    return ("\n".join(head) + "\n\n" if head else "") + message


def public(side: dict) -> dict:
    return {k: side.get(k) for k in ("key", "title", "link", "page", "home", "thread", "state", "ready", "turns", "updated", "mode", "error")}


class Sides:
    def __init__(self, path, ttl: int = TTL):
        self.path = Path(path)
        self.ttl = ttl
        self.lock = threading.Lock()

    def _load(self) -> dict:
        try:
            d = json.loads(self.path.read_text())
        except (OSError, ValueError):
            d = {}
        if not isinstance(d, dict):
            d = {}
        items = d.get("items") if isinstance(d.get("items"), dict) else {}
        seen = d.get("seen") if isinstance(d.get("seen"), (int, float)) else 0
        return {"items": {k: v for k, v in items.items() if isinstance(v, dict)}, "seen": float(seen)}

    def _save(self, d: dict) -> None:
        now = time.time()
        items = {k: v for k, v in d["items"].items() if now - float(v.get("updated") or 0) < self.ttl}
        if len(items) > MAX_SIDES:
            items = dict(sorted(items.items(), key=lambda kv: float(kv[1].get("updated") or 0))[-MAX_SIDES:])
        d["items"] = items
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(d))
        os.replace(tmp, self.path)

    # ---- a turn ----
    def begin(self, key, message: str, *, mode: str = "ask", title: str = "", text: str = "", link: str = "",
              page: str = "", home: str | None = None) -> tuple[int, dict]:
        """Record the owner's turn and return (200, {side, prompt}) to run, or an error. One turn at a time per side."""
        k = clean_key(key)
        if not k:
            return 400, {"ok": False, "error": "an item needs a key of letters, digits and ._:/#@-"}
        msg = str(message or "").strip()
        if not msg:
            return 400, {"ok": False, "error": "nothing to say"}
        if len(msg) > MESSAGE_MAX:
            return 413, {"ok": False, "error": f"a note is at most {MESSAGE_MAX} characters"}
        mode = mode if mode in MODES else "ask"
        with self.lock:
            d = self._load()
            s = d["items"].get(k)
            if s and s.get("state") in ("running", "waiting") and time.time() - float(s.get("updated") or 0) < STALE:
                return 409, {"ok": False, "busy": True, "error": "this note is still answering"}
            if not s:
                s = {"key": k, "title": _one_line(title, 160) or k, "text": str(text or "").strip()[:CONTEXT_MAX],
                     "link": _link(link), "page": _one_line(page, 200), "home": _one_line(home, 120) or None,
                     "thread": None, "turns": [], "created": time.time()}
                d["items"][k] = s
            elif home and not s.get("home"):
                s["home"] = _one_line(home, 120)      # a note first used by a ruling press learns its home on a later turn
            p = prompt(s, msg, mode)
            s["turns"] = (s.get("turns") or []) + [{"who": "me", "text": msg, "mode": mode, "at": time.time()}]
            s["turns"] = s["turns"][-TURNS_MAX:]
            s.update(state="running", ready=False, mode=mode, pending=p, error=None, updated=time.time())
            self._save(d)
            return 200, {"ok": True, "side": public(s), "prompt": p}

    def waiting(self, key) -> None:
        """The box was full: the turn waits in line and starts by itself."""
        with self.lock:
            d = self._load()
            s = d["items"].get(clean_key(key) or "")
            if s and s.get("state") == "running":
                s.update(state="waiting", updated=time.time())
                self._save(d)

    def by_prompt(self, text: str) -> str | None:
        """The side whose pending turn is exactly this text (a turn that waited in line comes back this way)."""
        with self.lock:
            for k, s in self._load()["items"].items():
                if s.get("pending") and s["pending"] == text and s.get("state") in ("running", "waiting"):
                    return k
        return None

    def finish(self, key, *, ok: bool, reply: str = "", thread: str | None = None, error: str = "") -> dict | None:
        """The turn ended: keep the thread, add the answer, mark it ready (a dot until the owner opens it)."""
        with self.lock:
            d = self._load()
            s = d["items"].get(clean_key(key) or "")
            if not s:
                return None
            if thread and not s.get("thread") and not str(thread).startswith("new:"):
                s["thread"] = str(thread)[:120]
            if ok:
                s["turns"] = (s.get("turns") or []) + [{"who": "brain", "text": str(reply or "")[:20000], "at": time.time()}]
                s["turns"] = s["turns"][-TURNS_MAX:]
            s.update(state="ready" if ok else "failed", ready=True, pending=None,
                     error=None if ok else (_one_line(error, 300) or "the turn did not finish"), updated=time.time())
            self._save(d)
            return dict(s)

    def finish_thread(self, key, thread: str) -> None:
        """The side's own thread was made before its first turn (so it never moves the box's current thread)."""
        with self.lock:
            d = self._load()
            s = d["items"].get(clean_key(key) or "")
            if s and not s.get("thread") and thread:
                s["thread"] = str(thread)[:120]
                self._save(d)

    def read(self, key) -> bool:
        """The owner opened the answer: the dot goes."""
        with self.lock:
            d = self._load()
            s = d["items"].get(clean_key(key) or "")
            if not s:
                return False
            if s.get("ready"):
                s["ready"] = False
                self._save(d)
            return True

    def touch_thread(self, thread) -> dict | None:
        """A job of a side's own thread finished: the side is ready again (its card is in the thread's log)."""
        t = str(thread or "")
        if not t:
            return None
        with self.lock:
            d = self._load()
            for s in d["items"].values():
                if s.get("thread") == t:
                    s.update(ready=True, updated=time.time())
                    if s.get("state") not in ("running", "waiting"):
                        s["state"] = "ready"
                    self._save(d)
                    return dict(s)
        return None

    # ---- reading ----
    def get(self, key) -> dict | None:
        with self.lock:
            s = self._load()["items"].get(clean_key(key) or "")
            return public(s) if s else None

    def list(self, *, keys=None, page: str = "", home: str = "") -> list:
        with self.lock:
            items = self._load()["items"].values()
        want = {clean_key(k) for k in (keys or []) if clean_key(k)}
        out = [public(s) for s in items
               if (not want or s["key"] in want) and (not page or s.get("page") == page) and (not home or s.get("home") == home)]
        return sorted(out, key=lambda s: -float(s.get("updated") or 0))

    def ready_count(self) -> int:
        with self.lock:
            return sum(1 for s in self._load()["items"].values() if s.get("ready"))

    def ready_list(self, n: int = 8) -> list:
        with self.lock:
            rows = [s for s in self._load()["items"].values() if s.get("ready")]
        rows.sort(key=lambda s: -float(s.get("updated") or 0))
        return [{k: s.get(k) for k in ("key", "title", "link", "page", "state")} for s in rows[:n]]

    def thread_ids(self) -> set:
        with self.lock:
            return {s["thread"] for s in self._load()["items"].values() if s.get("thread")}

    # ---- presence ----
    def seen(self, now: float | None = None) -> None:
        with self.lock:
            d = self._load()
            d["seen"] = float(now if now is not None else time.time())
            self._save(d)

    def away(self, now: float | None = None) -> bool:
        with self.lock:
            last = self._load()["seen"]
        return (float(now if now is not None else time.time()) - last) > AWAY
