#!/usr/bin/env python3
"""Onboarding time, measured (IMPORT-PACE-1, 2026-11-24, docs/MEMBER_READY.md item 12).

Target: from the pasted line to the first real answer from the person's own material in under 30 minutes on
a 2-vCPU brain. Two modes, synthetic data only:

  --estimate                 the model: the walk and the send (measured once, small), plus the first pass at
                             the measured reading rate (api/import_pace.py MEASURED), plus one answer. Prints
                             the minutes and GREEN/RED. Runs anywhere, touches nothing.
  --brain URL --key-file F   live, on a local brain or the rehearsal slot ONLY (never a member's brain): makes
                             a synthetic home (notes with one planted fact), mints a survey line, runs the
                             real agent.sh against the brain, chooses "proposed", presses Remember all, waits
                             for the first pass, then asks the brain the planted question and checks the
                             answer names the fact. Prints each step's elapsed seconds and the total.

The key is read from a file (never on the command line). Exit 0 GREEN, 1 RED, 2 not run.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from api import import_pace as pace  # noqa: E402

TARGET_SECONDS = 30 * 60
FACT = "The synthetic project codename is HELIOTROPE-7."
QUESTION = "What is my synthetic project codename?"
# measured on the box, 2026-11-24 (tests/test_laptop_agent.py runs): walk + list + choose + send of ~100 small
# files over a LAN is seconds; a member's real walk of a full home folder took about 2 minutes (unverified
# beyond one sitting), so the estimate carries 5 minutes for it
WALK_AND_SEND_SECONDS = 5 * 60
ANSWER_SECONDS = 60


def estimate(n_notes: int = 1865) -> dict:
    rows = [(f"Documents/n{i:04d}.md", 2700, time.time(), "knowledge") for i in range(n_notes)]
    _first, _order, est = pace.first_pass(rows)
    total = WALK_AND_SEND_SECONDS + est["first_seconds"] + ANSWER_SECONDS
    return {"walk_and_send_s": WALK_AND_SEND_SECONDS, "first_pass_s": est["first_seconds"], "first_files": est["first_files"],
            "answer_s": ANSWER_SECONDS, "total_s": total, "rest_hours": round(est["rest_seconds"] / 3600, 1),
            "green": total < TARGET_SECONDS}


def _call(base, key, method, path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-API-Key": key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def live(base: str, key: str, notes: int) -> dict:
    t0 = time.monotonic()
    marks = {}
    home = Path(tempfile.mkdtemp(prefix="onboarding-home-"))
    docs = home / "Documents"
    docs.mkdir()
    for i in range(notes):
        (docs / f"note-{i:03d}.md").write_text(f"# Note {i}\n\n" + ("ordinary words of a note. " * 60))
    (docs / "project.md").write_text(f"# Project\n\n{FACT}\n")
    tok = _call(base, key, "POST", "/documents/import-laptop/token", {"survey": True})["token"]

    def owner():
        while True:
            st = _call(base, key, "GET", "/documents/import-laptop/status").get("survey") or {}
            if st.get("state") == "plan":
                _call(base, key, "POST", "/documents/import-laptop/plan", {"take": "proposed", "named": ["Documents"]})
                return
            time.sleep(1)
    th = threading.Thread(target=owner, daemon=True)
    th.start()
    env = dict(os.environ, HOME=str(home), BRAIN_AGENT_NO_TTY="1", BRAIN_AGENT_RETRY_WAIT="0")
    r = subprocess.run(["bash", "-c", f"curl -fsSL {base}/laptop/agent.sh | bash -s -- {tok} {base}"],
                       env=env, capture_output=True, text=True, timeout=3600)
    marks["sent_s"] = round(time.monotonic() - t0)
    if r.returncode != 0:
        return {"error": "agent failed", "tail": r.stdout[-400:] + r.stderr[-400:], **marks}
    _call(base, key, "POST", "/documents/approve-all", {"kind": "documents"})
    while True:
        w = _call(base, key, "GET", "/documents/waiting")
        rd = w.get("reading") or {}
        if not rd.get("running") or rd.get("first_done", 0) >= rd.get("first_total", 0) > 0:
            break
        time.sleep(5)
    marks["first_pass_s"] = round(time.monotonic() - t0)
    ans = _call(base, key, "POST", "/chat/rag", {"messages": [{"role": "user", "content": QUESTION}]}, timeout=600)
    text = json.dumps(ans)
    marks["answer_s"] = round(time.monotonic() - t0)
    marks["answer_has_fact"] = "HELIOTROPE-7" in text
    marks["total_s"] = marks["answer_s"]
    marks["green"] = marks["answer_has_fact"] and marks["total_s"] < TARGET_SECONDS
    return marks


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--estimate", action="store_true")
    a.add_argument("--brain")
    a.add_argument("--key-file")
    a.add_argument("--notes", type=int, default=80)
    a = a.parse_args(argv)
    if a.estimate:
        out = estimate()
    elif a.brain and a.key_file:
        out = live(a.brain.rstrip("/"), Path(a.key_file).read_text().strip(), a.notes)
    else:
        print("give --estimate, or --brain URL --key-file FILE (a local or rehearsal brain only)")
        return 2
    print(json.dumps(out))
    print(f"onboarding: {'GREEN' if out.get('green') else 'RED'} {round(out.get('total_s', 0) / 60, 1)} min "
          f"(target under {TARGET_SECONDS // 60})")
    return 0 if out.get("green") else 1


if __name__ == "__main__":
    sys.exit(main())
