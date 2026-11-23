"""The card log of a thread (INLINE-1, 2026-11-23).

hbar, after Firefox crashed and the reload showed none of the thread's cards: "WHY DO CARDS DISAPPEAR
IF THEY RELOAD! CARDS SHOULD BE KEPT. CARDS ARE LIKE LOGS NO?"

Why they vanished: a finished job's tile and a REPORT-1 card were handed to the page once (Jobs.take_unseen,
Reports.take) and lived only in the page's memory. The conversation itself is reloaded from the brain's
record, the cards were not; and the bridge's "unseen" set of jobs lived in RAM, so a bridge restart lost
them too.

Now every card is written here when it is made (a job ends, a thread reports), under the thread it belongs
to, and the page draws the log again after any reload, in time order between the messages. Each entry keeps
its state: open, or answered (the owner typed into the thread after it, or pressed "answered").

The rule of 2026-10-11 holds: an entry belongs to exactly one thread and is only handed to a page that
names that thread. One small JSON file, written with a temp file and a rename. Pure: no network, no bridge
imports; tests/test_cc_cardlog.py runs it on temp dirs.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

KINDS = ("job", "report")
PER_THREAD = 200            # the newest entries of a thread are kept
MAX_THREADS = 400           # threads with the oldest last entry are dropped first
TTL = 60 * 24 * 3600        # an entry older than sixty days is dropped
TEXT_MAX = 1500             # a job result's text kept in the log (the card's "more" reads the full log)
_JOB_KEYS = ("id", "title", "rc", "started", "ended", "log", "thread", "cmd")


def known(thread) -> bool:
    t = str(thread or "").strip()
    return bool(t) and t != "unknown" and not t.startswith("new:") and len(t) <= 120


def _job_data(job: dict) -> dict:
    out = {k: job.get(k) for k in _JOB_KEYS if job.get(k) is not None}
    res = job.get("result")
    if isinstance(res, dict):
        r = {k: res.get(k) for k in ("rc", "secs", "more", "files") if res.get(k) is not None}
        r["text"] = str(res.get("text") or "")[:TEXT_MAX]
        if len(str(res.get("text") or "")) > TEXT_MAX:
            r["more"] = True
        out["result"] = r
    return out


class CardLog:
    def __init__(self, path, ttl: int = TTL):
        self.path = Path(path)
        self.ttl = ttl
        self.lock = threading.Lock()

    def _load(self) -> dict:
        try:
            d = json.loads(self.path.read_text())
        except (OSError, ValueError):
            d = {}
        th = d.get("threads") if isinstance(d, dict) else None
        if not isinstance(th, dict):
            th = {}
        return {"threads": {k: [e for e in v if isinstance(e, dict) and e.get("id")] for k, v in th.items() if isinstance(v, list)}}

    def _save(self, d: dict) -> None:
        now = time.time()
        th = {}
        for k, v in d["threads"].items():
            keep = [e for e in v if now - float(e.get("at") or 0) < self.ttl][-PER_THREAD:]
            if keep:
                th[k] = keep
        if len(th) > MAX_THREADS:
            th = dict(sorted(th.items(), key=lambda kv: float(kv[1][-1].get("at") or 0))[-MAX_THREADS:])
        d["threads"] = th
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(d))
        os.replace(tmp, self.path)

    def add(self, thread, kind: str, data: dict, at: float | None = None) -> dict | None:
        """Log a card under `thread`. The same card again (same kind and id) updates its data and keeps
        its place and its answered state. A card of no known thread is not logged."""
        if not known(thread) or kind not in KINDS or not isinstance(data, dict) or not data.get("id"):
            return None
        data = _job_data(data) if kind == "job" else {k: v for k, v in data.items() if k != "parent" or v}
        eid = f"{kind}:{data['id']}"
        with self.lock:
            d = self._load()
            rows = d["threads"].setdefault(str(thread), [])
            for e in rows:
                if e["id"] == eid:
                    e["data"] = data
                    self._save(d)
                    return dict(e)
            if kind == "report" and data.get("child"):
                # REPORT-1 keeps one waiting card per child: a newer turn's card replaces an open older one
                rows[:] = [e for e in rows if not (e.get("kind") == "report" and not e.get("answered")
                                                  and (e.get("data") or {}).get("child") == data["child"])]
            e = {"id": eid, "kind": kind, "at": float(at if at is not None else (data.get("ended") or data.get("at") or time.time())),
                 "answered": False, "data": data}
            rows.append(e)
            rows.sort(key=lambda x: float(x.get("at") or 0))
            self._save(d)
            return dict(e)

    def list(self, thread) -> list:
        """The thread's cards, oldest first."""
        if not known(thread):
            return []
        with self.lock:
            now = time.time()
            return [dict(e) for e in self._load()["threads"].get(str(thread), []) if now - float(e.get("at") or 0) < self.ttl]

    def answer(self, thread, eid: str) -> bool:
        """The owner pressed "answered" on one card."""
        if not known(thread):
            return False
        with self.lock:
            d = self._load()
            for e in d["threads"].get(str(thread), []):
                if e["id"] == eid:
                    if not e.get("answered"):
                        e["answered"] = True
                        e["answered_at"] = time.time()
                        self._save(d)
                    return True
            return False

    def answer_before(self, thread, before: float | None = None) -> int:
        """The owner wrote into the thread: every open card that came before is answered. Returns how many."""
        if not known(thread):
            return 0
        before = time.time() if before is None else before
        with self.lock:
            d = self._load()
            n = 0
            for e in d["threads"].get(str(thread), []):
                if not e.get("answered") and float(e.get("at") or 0) <= before:
                    e["answered"] = True
                    e["answered_at"] = before
                    n += 1
            if n:
                self._save(d)
            return n

    def open_count(self, thread) -> int:
        return sum(1 for e in self.list(thread) if not e.get("answered"))
