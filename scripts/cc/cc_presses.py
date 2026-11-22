"""The console's private usage log (USAGE-1, 2026-11-22).

Which controls the owner presses in the console: nav buttons, surfaces (pages), panes, choice
buttons and slash commands, each with the time and the thread it happened in. It is step 1 of the
adaptive-surfaces build (event log; the classifier comes later) and it follows that spec's limits:

  - counts and kinds only, never content: a name is a route or a command word from a closed
    alphabet, so a message, a file path, a choice's label or a slash command's argument cannot land here;
  - one file on the box, ~/.cc-bridge/surface-events.jsonl, mode 0600; nothing sends it anywhere
    (this module imports no network code and the export does not read the bridge's state);
  - the owner turns it off in Settings; while off nothing is written; clear deletes the file.

Pure standard library, no bridge imports: tests/test_cc_presses.py runs it alone.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

KINDS = ("nav", "surface", "pane", "choice", "slash")
NAME_RE = re.compile(r"^[a-z0-9/#][a-z0-9/#:._\-]{0,79}$")
THREAD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._\-]{0,79}$")
EVENTS = "surface-events.jsonl"
SWITCH = "usage-log.json"
MAX_BYTES = 2_000_000     # past this the file is trimmed to the last KEEP_DAYS days
KEEP_DAYS = 90
DAY = 86400.0

# The sentence the Settings switch, the page and the guide all show. One source, so they agree.
WHAT = ("Counted: which menu buttons, pages, panes, choice buttons and slash commands you press, "
        "with the time and the thread. Never what you write, never a choice's words, never a file's name. "
        "Kept in one file on this box; sent nowhere.")


class UsageError(ValueError):
    pass


def clean(kind, name, thread="") -> dict:
    """One checked event, without its time. Raises UsageError; nothing is repaired silently."""
    if kind not in KINDS:
        raise UsageError("kind must be one of: " + ", ".join(KINDS))
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise UsageError("name must be a route or a command word: a-z 0-9 / # : . _ - (80 at most)")
    if thread in (None, ""):
        thread = ""
    elif not isinstance(thread, str) or not THREAD_RE.match(thread):
        raise UsageError("thread must be a thread id")
    return {"kind": kind, "name": name, "thread": thread}


def _stamp(now: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))


def counts(events, now: float) -> list:
    """[{kind, name, d7, d30, all, last}] sorted by the 30-day count, then the 7-day one."""
    rows: dict = {}
    for e in events:
        try:
            key = (e["kind"], e["name"]); ts = float(e["ts"])
        except (KeyError, TypeError, ValueError):
            continue
        r = rows.setdefault(key, {"kind": key[0], "name": key[1], "d7": 0, "d30": 0, "all": 0, "last": 0.0})
        r["all"] += 1
        age = now - ts
        if age <= 30 * DAY:
            r["d30"] += 1
        if age <= 7 * DAY:
            r["d7"] += 1
        r["last"] = max(r["last"], ts)
    out = sorted(rows.values(), key=lambda r: (-r["d30"], -r["d7"], -r["all"], r["kind"], r["name"]))
    for r in out:
        r["last"] = _stamp(r["last"])
    return out


class Store:
    def __init__(self, state_dir):
        self.dir = Path(state_dir)
        self.events = self.dir / EVENTS
        self.switch = self.dir / SWITCH
        self._lock = threading.Lock()

    # ---- the switch ----
    def on(self) -> bool:
        """On unless the owner turned it off. An unreadable switch file reads as off (fail closed)."""
        if not self.switch.exists():
            return True
        try:
            return json.loads(self.switch.read_text()).get("on") is True
        except (OSError, ValueError, AttributeError):
            return False

    def set_on(self, on, now: float | None = None) -> bool:
        if not isinstance(on, bool):
            raise UsageError("on must be true or false")
        with self._lock:
            self.dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            tmp = self.switch.with_suffix(".tmp")
            tmp.write_text(json.dumps({"on": on, "changed": _stamp(now if now is not None else time.time())}))
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.switch)
        return on

    # ---- writing ----
    def log(self, kind, name, thread="", now: float | None = None) -> bool:
        """Append one event. False (and nothing written) while the log is off."""
        ev = clean(kind, name, thread)
        if not self.on():
            return False
        now = time.time() if now is None else now
        line = json.dumps({"t": _stamp(now), "ts": round(now, 3), **ev}, separators=(",", ":"))
        with self._lock:
            self.dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(self.events, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, (line + "\n").encode())
            finally:
                os.close(fd)
            try:
                if self.events.stat().st_size > MAX_BYTES:
                    self._trim(now)
            except OSError:
                pass
        return True

    def _trim(self, now: float) -> None:
        keep = [e for e in self._read() if now - float(e.get("ts") or 0) <= KEEP_DAYS * DAY]
        tmp = self.events.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(e, separators=(",", ":")) + "\n" for e in keep))
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.events)

    def clear(self) -> int:
        """Delete the log. Returns how many events it held."""
        with self._lock:
            n = len(self._read())
            try:
                self.events.unlink()
            except FileNotFoundError:
                pass
        return n

    # ---- reading ----
    def _read(self) -> list:
        try:
            raw = self.events.read_text().splitlines()
        except (OSError, UnicodeDecodeError):
            return []
        out = []
        for ln in raw:
            try:
                e = json.loads(ln)
            except ValueError:
                continue
            if isinstance(e, dict) and e.get("kind") in KINDS:
                out.append(e)
        return out

    def view(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        ev = self._read()
        rows = counts(ev, now)
        threads7 = {e.get("thread") for e in ev if e.get("thread") and now - float(e.get("ts") or 0) <= 7 * DAY}
        threads30 = {e.get("thread") for e in ev if e.get("thread") and now - float(e.get("ts") or 0) <= 30 * DAY}
        return {"on": self.on(), "what": WHAT, "file": str(self.events), "kinds": list(KINDS),
                "events": len(ev), "since": ev[0].get("t") if ev else None,
                "d7": sum(r["d7"] for r in rows), "d30": sum(r["d30"] for r in rows),
                "threads7": len(threads7), "threads30": len(threads30), "controls": rows}
