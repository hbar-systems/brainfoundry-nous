#!/usr/bin/env python3
"""cc-job: run a command that outlives a CC turn, on the box, through the bridge. Created 2026-09-22.

Installed as ~/.local/bin/cc-job for the bridge user. Standard library only. The bridge
passes CC_PORT, CC_BASE and CC_ASK_TOKEN in the reasoner's environment, and since 2026-10-11
CC_THREAD_ID and CC_RUN_ID, so a job knows which conversation started it.

    cc-job run [-C <dir>] [-t "<title>"] -- '<command>'   start; prints the job id
                                    (one quoted string keeps &&, |, > and quotes intact)
    cc-job status <id>        state, exit code, last lines of the log
    cc-job tail <id> [n]      last n bytes of the log (default 4000)
    cc-job list               recent jobs
    cc-job ask <https://peer> "<question>"   ask another brain; this brain signs it
    cc-job task add "<text>" [--due <ISO 8601>]   put a task on the person's list (the /tasks page)
    cc-job task list          the open tasks
    cc-job task done <id>... [--undo]   close tasks on the person's word (--undo reopens)
    cc-job threads [words]    thread ids and titles, to link one as /talk?thread=<id>
    cc-job radio [https://station]   a link to listen on a radio brain with this brain (orfeo.music by default)
    cc-job halt ["reason"] [--kill]   the kill switch (2026-10-25): writes ~/.cc-bridge/HALT; no new
                              job, tick or agent starts until resume; --kill also ends running jobs
    cc-job halt --status      halted or not, budget halts, running jobs
    cc-job resume             removes the HALT file

Jobs never run sudo. A claude started by a job gets the turn's permission settings, and the flags
that would loosen the owner's posture are refused by the bridge (2026-10-19, cc_guard.py). The person sees every job on the CC page and can ask about it.
"""
import json
import os
import shlex
import sys
import urllib.error
import urllib.request
from pathlib import Path

# The kill switch's shared module (2026-10-25): beside this file in the repo, and install.sh copies
# it beside the installed cc-job. Without it, halt/resume still work on the file alone.
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cc_halt
except Exception:  # noqa: BLE001
    cc_halt = None

HANDS_HOME = Path(os.environ.get("HOME") or Path.home())


def _halt_cmd(rest: list[str]) -> int:
    """cc-job halt ["reason"] [--kill] | cc-job halt --status | cc-job resume (routed here as ["--resume"])."""
    by = os.environ.get("USER") or "hands"
    halt_file = HANDS_HOME / ".cc-bridge" / "HALT"
    if "--resume" in rest:
        if cc_halt:
            was = cc_halt.clear_halt(HANDS_HOME, by=by)
        else:
            was = halt_file.exists(); halt_file.unlink(missing_ok=True)
        print("resumed: new jobs, the tick and agents may start again" if was else "was not halted"); return 0
    if "--status" in rest:
        why = cc_halt.halted(HANDS_HOME) if cc_halt else (f"HALT: {halt_file.read_text().strip().splitlines()[0]}" if halt_file.exists() else None)
        print(why or "not halted (no HALT file)")
        if cc_halt:
            b = cc_halt.budget_halts(os.environ.get("CC_WORLD_DIR", ""))
            print("budget halts: " + (", ".join(f"{k} ({v})" for k, v in b.items()) if b else "none"))
            running = cc_halt.running_jobs(HANDS_HOME / "out" / "jobs" / "jobs.json")
            print(f"running jobs: {len(running)}" + ("".join(f"\n  {r['id']}  {r.get('title', '')[:70]}" for r in running)))
        print(f"file: {halt_file}"); return 0 if not why else 3
    kill = "--kill" in rest
    reason = " ".join(w for w in rest if w != "--kill").strip() or f"halted by {by}"
    if cc_halt:
        cc_halt.set_halt(HANDS_HOME, reason, by=by)
    else:
        halt_file.parent.mkdir(parents=True, exist_ok=True); halt_file.write_text(reason + "\n")
    print(f"HALT: {reason}\nno new job, tick or agent starts until: cc-job resume")
    if kill:
        if not cc_halt:
            print("--kill needs cc_halt.py beside cc-job; running jobs were left alone"); return 1
        ids = cc_halt.kill_jobs(HANDS_HOME / "out" / "jobs" / "jobs.json")
        cc_halt.log(HANDS_HOME, f"kill by {by}: {' '.join(ids) if ids else 'no running jobs'}")
        print("ended running jobs: " + (" ".join(ids) if ids else "none were running"))
    return 0


def _call(method: str, route: str, body: dict | None = None, timeout: float = 30) -> dict:
    port = os.environ.get("CC_PORT", "7682")
    base = os.environ.get("CC_BASE", "/cc").rstrip("/")
    url = f"http://127.0.0.1:{port}{base}{route}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"Content-Type": "application/json", "X-CC-Ask": os.environ.get("CC_ASK_TOKEN", "")})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode() or "{}") or {"error": f"HTTP {e.code}"}
        except Exception:  # noqa: BLE001
            return {"error": f"HTTP {e.code}"}


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__); return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "halt":
        return _halt_cmd(rest)
    if cmd == "resume":
        return _halt_cmd(["--resume"])
    try:
        if cmd == "run":
            cwd, title = None, ""
            while rest and rest[0] in ("-C", "-t"):
                if rest[0] == "-C":
                    cwd = rest[1]
                else:
                    title = rest[1]
                rest = rest[2:]
            if rest and rest[0] == "--":
                rest = rest[1:]
            if not rest:
                print("cc-job run -- <command>"); return 2
            # Keep the caller's words exactly (quotes included): one argument stays one argument.
            command = rest[0] if len(rest) == 1 else shlex.join(rest)
            # The thread whose hands start this job (2026-10-11): the bridge puts CC_THREAD_ID and
            # CC_RUN_ID into the reasoner's environment, and the Bash tool passes them on. The tile
            # for the finished job then lands in that conversation only; "unknown" keeps it off
            # every conversation (the board still lists it).
            d = _call("POST", "/jobs/start", {"command": command, "cwd": cwd, "title": title,
                                              "thread": os.environ.get("CC_THREAD_ID", "").strip() or "unknown",
                                              "run": os.environ.get("CC_RUN_ID", "").strip() or None})
            if d.get("error"):
                # The kill switch (2026-10-25): the bridge says HALT: <reason>; print it as it is.
                print(d["error"] if str(d["error"]).startswith("HALT") else "refused: " + str(d["error"])); return 1
            print(f"started {d['id']} (log {d['log']}); check with: cc-job status {d['id']}"); return 0
        if cmd == "status" and rest:
            d = _call("GET", f"/jobs/{rest[0]}")
            if not d or d.get("error"):
                print("no such job"); return 1
            state = "running" if d.get("running") else f"finished rc={d.get('rc')}"
            took = (d.get("ended") or __import__("time").time()) - d["started"]
            print(f"{d['id']} {state} · {int(took)} s · {d['title']}\n--- log tail ---\n{d.get('tail', '')}"); return 0
        if cmd == "tail" and rest:
            n = int(rest[1]) if len(rest) > 1 else 4000
            d = _call("GET", f"/jobs/{rest[0]}?tail={n}")
            print(d.get("tail", "") if d else "no such job"); return 0
        if cmd == "ask" and len(rest) >= 2:
            # Ask a peer brain (2026-10-20): the bridge has the brain sign it; no key here.
            d = _call("POST", "/ask-peer", {"peer": rest[0], "question": " ".join(rest[1:])}, timeout=200)
            if not d or not d.get("ok"):
                print("refused:", (d or {}).get("error", "no answer")); return 1
            print(d.get("answer", ""))
            if d.get("citations"):
                print("\nCited:\n" + "\n".join(f"  - {c}" for c in d["citations"]))
            print(f"\n(from {d.get('brain_id')} at {d.get('peer')})"); return 0
        if cmd == "task" and rest and rest[0] == "add":
            # The reasoner's task-write path (2026-10-20): the bridge holds the brain's key and adds it.
            words, due, i = [], None, 1
            while i < len(rest):
                if rest[i] == "--due" and i + 1 < len(rest):
                    due, i = rest[i + 1], i + 2
                else:
                    words.append(rest[i]); i += 1
            if not words:
                print('cc-job task add "<text>" [--due <ISO 8601>]'); return 2
            d = _call("POST", "/tasks/add", {"text": " ".join(words), "due": due,
                                             "thread": os.environ.get("CC_THREAD_ID", "").strip()})
            if not d.get("ok"):
                print("refused:", d.get("error", "no answer")); return 1
            t = d["task"]
            print(f"task {t['id']} added{' due ' + t['due'] if t.get('due') else ''}: {t['text']}"); return 0
        if cmd == "task" and rest and rest[0] == "done":
            # Close (or with --undo reopen) tasks on the person's word (2026-10-24).
            ids = [w for w in rest[1:] if w != "--undo"]
            if not ids:
                print('cc-job task done <id>... [--undo]'); return 2
            d = _call("POST", "/tasks/done", {"ids": ids, "done": "--undo" not in rest,
                                              "thread": os.environ.get("CC_THREAD_ID", "").strip()})
            for i, ok in (d.get("results") or {}).items():
                print(f"{i} {('reopened' if '--undo' in rest else 'closed') if ok else 'not found'}")
            if not d.get("results"):
                print("refused:", d.get("error", "no answer"))
            return 0 if d.get("ok") else 1
        if cmd == "radio":
            # Listen on a radio brain (2026-10-25): the bridge asks the api for a signed taste-note link.
            station = rest[0] if rest else "https://orfeo.music"
            d = _call("POST", "/radio/link", {"station": station}, timeout=60)
            if not d.get("ok"):
                print("refused:", d.get("error", "no answer")); return 1
            ev = d.get("event") or {}
            tail = f"  (harmonics score {ev.get('score')})" if isinstance(ev, dict) and ev.get("score") is not None else ""
            print(d["url"] + tail); return 0
        if cmd == "threads":
            # Thread ids and titles (2026-10-24), to link a thread as /talk?thread=<id>.
            words = [w.lower() for w in rest]
            for t in _call("GET", "/threads/brief").get("threads", []):
                if all(w in t["title"].lower() for w in words):
                    print(f"{t['id']}  {str(t.get('last') or '')[:16]:16}  {t['title']}")
            return 0
        if cmd == "task" and rest and rest[0] == "list":
            d = _call("GET", "/tasks")
            if "tasks" not in d:
                print("refused:", d.get("error", "no answer")); return 1
            for t in d["tasks"]:
                print(f"{t['id']}  {t.get('due') or '-':20} {t['text']}{'  (from ' + t['source'] + ')' if t.get('source') else ''}")
            if not d["tasks"]:
                print("no open tasks")
            return 0
        if cmd == "list":
            for j in _call("GET", "/jobs").get("jobs", []):
                state = "running" if j.get("ended") is None else f"rc={j.get('rc')}"
                mine = os.environ.get("CC_THREAD_ID", "").strip()
                where = "" if not mine or j.get("thread") == mine else ("  (another conversation)" if j.get("thread") not in (None, "", "unknown") else "  (no conversation)")
                print(f"{j['id']}  {state:12} {j['title']}{where}")
            return 0
    except Exception as e:  # noqa: BLE001
        print(f"the bridge did not answer ({type(e).__name__})"); return 1
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
