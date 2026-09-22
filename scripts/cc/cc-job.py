#!/usr/bin/env python3
"""cc-job: run a command that outlives a CC turn, on the box, through the bridge. Created 2026-09-22.

Installed as ~/.local/bin/cc-job for the bridge user. Standard library only. The bridge
passes CC_PORT, CC_BASE and CC_ASK_TOKEN in the reasoner's environment.

    cc-job run [-C <dir>] [-t "<title>"] -- <command ...>   start; prints the job id
    cc-job status <id>        state, exit code, last lines of the log
    cc-job tail <id> [n]      last n bytes of the log (default 4000)
    cc-job list               recent jobs

Jobs never run sudo. The person sees every job on the CC page and can ask about it.
"""
import json
import os
import sys
import urllib.error
import urllib.request


def _call(method: str, route: str, body: dict | None = None) -> dict:
    port = os.environ.get("CC_PORT", "7682")
    base = os.environ.get("CC_BASE", "/cc").rstrip("/")
    url = f"http://127.0.0.1:{port}{base}{route}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"Content-Type": "application/json", "X-CC-Ask": os.environ.get("CC_ASK_TOKEN", "")})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
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
            d = _call("POST", "/jobs/start", {"command": " ".join(rest), "cwd": cwd, "title": title})
            if d.get("error"):
                print("refused:", d["error"]); return 1
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
        if cmd == "list":
            for j in _call("GET", "/jobs").get("jobs", []):
                state = "running" if j.get("ended") is None else f"rc={j.get('rc')}"
                print(f"{j['id']}  {state:12} {j['title']}")
            return 0
    except Exception as e:  # noqa: BLE001
        print(f"the bridge did not answer ({type(e).__name__})"); return 1
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
