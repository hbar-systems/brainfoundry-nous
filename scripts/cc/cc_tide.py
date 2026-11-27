"""Tide (AUTO-UPDATE-1, 2026-11-27): the brain updates itself at a quiet moment.

hbar, 2026-11-27: "we should have a system now does update automatically in optimal moments of the
workflow so for example of all systems are going and then update won't harm any of the or interfere in
any of these autonomous versions and I'm clearly not interacting directly at this time then it should
make an update."

Three parts, docs/TIDE.md:
  - quiet(): one pure rule, "is this a quiet moment", with the reason for "no" in plain words;
  - Store: the owner's switch, his last touch, the update in flight and the last automatic updates, one
    JSON file in the bridge's own state folder (mode 600, the hands and every agent cannot write it);
  - the bridge's routes (GET /cc/autoupdate for the page, POST /cc/autoupdate/switch for his press, and
    the root door /cc/autoupdate/quiet, /begin, /end for scripts/tide/brain-tide.sh, uid 0 on loopback only).

What an update stops (measured 2026-11-27, docs/TIDE.md "What dies"):
  - a turn in flight: an update that changes scripts/cc/install.sh reruns it, and it restarts cc-bridge
    and claude-tab outright; the reasoner's pipe to the bridge is cut and the answer is lost. So: no turn.
  - a card: it lives in the turn that waits for it. So: no card.
  - the terminal pane (claude-tab, tmux): the same rerun restarts it, its whole control group. So: the
    terminal untouched for the idle minutes (the root door measures tmux and passes it in).
  - an upload in progress: the bridge's request is cut. So: none in flight, no resumable piece in 10 min.
  - cc-jobs and standing agents SURVIVE: cc-bridge runs with KillMode=process, the jobs' processes stay
    in the unit's group and write their rc to a file the next bridge reads. Proof: SEAT-3 (J1795466731615,
    a claude -p build, 20:45 to 23:10 UTC on 2026-11-23) ran through the hard restart of cc-bridge and
    claude-tab at 22:30:49 (cc-install-watch) and ended rc=0; METRICS-1 preview (J1795651533706) ran
    through the restarts of 2026-11-26 04:03 and 06:30:50. So running jobs do not block (JOBS_BLOCK=False);
    they only see the api answer nothing for the 30 to 60 s its container is recreated.

Pure standard library, no bridge imports: tests/test_cc_tide.py runs it alone.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

FILE = "tide.json"
IDLE_MIN = 20            # his last message or press anywhere is older than this
GAP_MIN = 60             # at most one automatic update an hour
JOBS_BLOCK = False       # jobs survive an update (proof above); True puts them back in the rule
BEGIN_TTL = 2400         # an update that began and never reported ends as "unknown" after 40 min
UPLOAD_FRESH = 600       # a resumable upload's piece younger than this counts as an upload in progress
HISTORY = 20             # automatic updates kept
TOUCH_SAVE_EVERY = 30    # his touches reach the file at most every 30 s (kept in memory in between)
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

# POST routes only a person's action sends (a message, a press, a file or a recording he gives). The
# page also POSTs on timers (marks, checks), so a route list and not "any POST": a timer must not keep
# the brain from ever being quiet, and a missing route here only makes the rule wait less, never run
# something new. Uploads are also counted while in flight.
TOUCH_ROUTES = ("/chat", "/permits/approve", "/permits/deny", "/presses", "/update", "/autoupdate/switch",
                "/restart", "/restart/now", "/sides/say", "/booth/take", "/take/backing", "/transcribe",
                "/systems/voice", "/upload")
UPLOAD_ROUTES = ("/upload", "/booth/take", "/take/backing", "/transcribe", "/systems/voice")


def touch_route(route: str) -> bool:
    """A POST route that means he is here. /threads/<id>/say (the central chat steering) and
    /upload/big/<...> (a resumable upload's pieces) by prefix. Pure; tested."""
    r = str(route or "")
    return r in TOUCH_ROUTES or r.startswith("/upload/big/") or (r.startswith("/threads/") and r.endswith("/say"))


def upload_route(route: str) -> bool:
    r = str(route or "")
    return r in UPLOAD_ROUTES or r.startswith("/upload/big/")


def _n(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _hm(t: float) -> str:
    return time.strftime("%H:%M UTC", time.gmtime(t))


def quiet(f: dict, now: float, idle_min: int = IDLE_MIN, gap_min: int = GAP_MIN,
          jobs_block: bool = JOBS_BLOCK) -> tuple[bool, str]:
    """Is this a quiet moment to update? (True, why) only when every condition holds; else (False, the
    first reason in plain words). Pure; tested. Facts (missing = unknown, which never says yes):
      on           the owner's switch                      member      a member brain (never here)
      halt         the HALT text, or None                  behind      commits origin/main is ahead, or None
      latest       origin/main's sha                       failed_sha  the commit whose update failed
      updating     an update began and has not reported    last_update when the last automatic one began
      runs         turns in flight in any thread           cards       cards waiting for his press
      uploads      uploads or recordings coming in         jobs        cc-jobs running
      last_touch   his last message or press (console, Telegram)
      terminal     the terminal pane's last activity (the root door measures it; None = not measured)
    """
    if f.get("member"):
        return False, "off: a member's brain updates only by its owner's press"
    if not f.get("on"):
        return False, "off: it waits for your press"
    if f.get("halt"):
        return False, f"waiting: the brain is halted ({str(f['halt'])[:80]})"
    behind = f.get("behind")
    if behind is None:
        return False, "waiting: the running version cannot be read"
    if behind <= 0:
        return False, "waiting: nothing new on origin/main"
    if f.get("updating"):
        return False, "waiting: an update is running"
    latest = str(f.get("latest") or "")
    if latest and f.get("failed_sha") and latest == f.get("failed_sha"):
        return False, f"waiting: the update to {latest[:7]} failed its health check; no retry until a new commit"
    last = f.get("last_update")
    if last and now - float(last) < gap_min * 60:
        return False, f"waiting: an update ran {int((now - float(last)) // 60)} min ago; the next from {_hm(float(last) + gap_min * 60)}"
    runs = int(f.get("runs") or 0)
    if runs:
        return False, "waiting: " + _n(runs, "conversation answering", "conversations answering")
    cards = int(f.get("cards") or 0)
    if cards:
        return False, "waiting: " + _n(cards, "card waits", "cards wait") + " for your press"
    if int(f.get("uploads") or 0):
        return False, "waiting: an upload or a recording is coming in"
    jobs = int(f.get("jobs") or 0)
    if jobs_block and jobs:
        return False, "waiting: " + _n(jobs, "job running", "jobs running")
    touch = max(float(f.get("last_touch") or 0), float(f.get("terminal") or 0))
    if touch and now - touch < idle_min * 60:
        where = "in the terminal" if float(f.get("terminal") or 0) >= float(f.get("last_touch") or 0) else "here"
        return False, f"waiting: you were {where} {int((now - touch) // 60)} min ago; quiet from {_hm(touch + idle_min * 60)}"
    tail = f"; {_n(jobs, 'job runs', 'jobs run')} on (jobs survive an update)" if jobs else ""
    return True, f"quiet: {_n(behind, 'commit', 'commits')} to take, nothing answering, no card{tail}"


def begin_line(n: int, lines: list) -> str:
    """The line before an update, central thread and Telegram. Pure; tested."""
    heads = [" ".join(str(x).split())[:90] for x in (lines or []) if str(x).strip()][:3]
    more = f" (+{n - len(heads)} more)" if n > len(heads) and heads else ""
    return f"updating now: {_n(int(n), 'commit', 'commits')}" + (f": {'; '.join(heads)}{more}" if heads else "")


def end_line(rec: dict) -> str:
    """The line after an update. Pure; tested. A failure says which version runs: the script never rolls
    back, so after a failed pull nothing changed, and after a pulled but unhealthy rebuild the new
    checkout is in place and Revert on /update goes one step back."""
    to, frm, head = str(rec.get("to") or "")[:7], str(rec.get("from") or "")[:7], str(rec.get("head") or "")[:7]
    rc = rec.get("rc")
    if rec.get("result") == "busy":
        return "update skipped: another update or revert held the checkout; it is tried again at the next quiet moment"
    if rec.get("result") == "healthy":
        return f"updated to {head or to}, healthy"
    if rec.get("result") == "unknown":
        return f"the update to {to} never reported back; /update shows the version that runs"
    if head and frm and head == frm:
        return f"update to {to} failed (rc={rc}); the old version {frm} still runs; no retry until a new commit"
    return (f"update to {to} failed its health check (rc={rc}); the checkout is at {head or '?'}, "
            f"Revert on /update goes back to {frm}; no retry until a new commit")


class Store:
    """The tide's one file in the bridge's state folder. Written with a temp file and a rename."""

    def __init__(self, state_dir, clock=time.time):
        self.path = Path(state_dir) / FILE
        self.clock = clock
        self.lock = threading.Lock()
        self._touch = 0.0
        self._touch_saved = 0.0
        self._inflight = 0
        d = self._load()
        self._touch = float(d.get("touch") or 0)
        self._touch_saved = self._touch

    def _load(self) -> dict:
        try:
            d = json.loads(self.path.read_text())
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, d: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(d, fh, indent=1)
        os.replace(tmp, self.path)

    # ---- the switch ----
    def on(self) -> bool:
        return bool(self._load().get("on"))

    def set_on(self, on, by: str = "the owner") -> dict:
        if not isinstance(on, bool):
            raise ValueError("on must be true or false")
        with self.lock:
            d = self._load()
            d.update({"on": on, "by": by, "at": self.clock()})
            self._save(d)
        return self.view()

    # ---- his touch ----
    def touch(self) -> None:
        now = self.clock()
        with self.lock:
            self._touch = now
            if now - self._touch_saved >= TOUCH_SAVE_EVERY:
                d = self._load()
                d["touch"] = now
                self._save(d)
                self._touch_saved = now

    def last_touch(self) -> float:
        return self._touch

    def upload_start(self) -> None:
        with self.lock:
            self._inflight += 1

    def upload_end(self) -> None:
        with self.lock:
            self._inflight = max(0, self._inflight - 1)

    def uploads(self) -> int:
        return self._inflight

    # ---- an update ----
    def _expire(self, d: dict) -> bool:
        b = d.get("begun")
        if b and self.clock() - float(b.get("at") or 0) > BEGIN_TTL:
            rec = {**b, "started": b.get("at"), "at": self.clock(), "result": "unknown", "rc": None, "head": None}
            d["history"] = ([rec] + list(d.get("history") or []))[:HISTORY]
            d["begun"] = None
            return True
        return False

    def facts(self) -> dict:
        """The stored half of quiet()'s facts."""
        with self.lock:
            d = self._load()
            if self._expire(d):
                self._save(d)
        hist = d.get("history") or []
        last = (d.get("begun") or {}).get("at") or max([float(h.get("started") or 0) for h in hist] or [0]) or None
        return {"on": bool(d.get("on")), "updating": bool(d.get("begun")), "failed_sha": d.get("failed_sha"),
                "last_update": last, "last_touch": self._touch or None}

    def begin(self, frm: str, to: str, n: int, lines: list) -> dict:
        if not (SHA_RE.match(str(frm or "")) and SHA_RE.match(str(to or ""))):
            raise ValueError("from and to must be commit shas")
        rec = {"from": frm, "to": to, "n": max(0, int(n)), "lines": [" ".join(str(x).split())[:200] for x in (lines or [])][:5],
               "at": self.clock()}
        with self.lock:
            d = self._load()
            self._expire(d)
            if d.get("begun"):
                raise ValueError("an update is already running")
            d["begun"] = rec
            self._save(d)
        return rec

    def end(self, rc, head: str | None, to: str | None = None) -> dict | None:
        """The runner's report. rc 0 = update_brain.sh passed its health check; 75 = the checkout's lock
        was held (nothing ran). Returns the history record, or None when nothing had begun."""
        with self.lock:
            d = self._load()
            b = d.get("begun")
            if not b or (to and to != b.get("to")):
                return None
            rc = int(rc) if isinstance(rc, int) or (isinstance(rc, str) and rc.lstrip("-").isdigit()) else None
            result = "healthy" if rc == 0 else ("busy" if rc == 75 else "failed")
            rec = {**b, "started": b.get("at"), "at": self.clock(), "rc": rc, "result": result,
                   "head": head if SHA_RE.match(str(head or "")) else None}
            d["history"] = ([rec] + list(d.get("history") or []))[:HISTORY]
            d["begun"] = None
            if result == "failed":
                d["failed_sha"] = b.get("to")
            elif result == "healthy":
                d["failed_sha"] = None
            if result == "busy":
                rec["started"] = None       # nothing ran: the hour's gap does not start
                d["history"][0] = rec
            self._save(d)
        return rec

    def asked(self, answer: dict) -> None:
        """The root door asked (its time and answer, so the page can say the timer is there)."""
        with self.lock:
            d = self._load()
            d["asked"] = {"at": self.clock(), "quiet": bool(answer.get("quiet")), "why": str(answer.get("why") or "")[:200]}
            self._save(d)

    def view(self) -> dict:
        d = self._load()
        return {"on": bool(d.get("on")), "by": d.get("by"), "since": d.get("at"), "begun": d.get("begun"),
                "failed_sha": d.get("failed_sha"), "asked": d.get("asked"),
                "recent": [{k: h.get(k) for k in ("at", "started", "from", "to", "n", "rc", "result", "head")}
                           for h in (d.get("history") or [])[:3]]}
