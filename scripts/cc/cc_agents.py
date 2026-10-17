#!/usr/bin/env python3
"""Standing agents (2026-10-17): agents the person creates in the console and that then run on their own.

An agent is a charter: a name, a mission, the ground it may write in, a schedule, a budget and an optional
model. The bridge calls `tick` every minute as the hands user (so the ask token is in the environment and the
permission hook works). Each enabled agent whose time has come opens one cc-job: a headless reasoner turn with
the charter as its prompt. Writes inside its ground and its own folder pass; push, rm -rf and .env are refused;
everything else raises a card for the person. The job is a tile on the board like any other. The agent files a
sitrep to <agents dir>/<id>/sitreps/<UTC stamp>.md before it ends, and the Agents page shows the newest.

Storage: one JSON file per agent in CC_AGENTS_DIR (default ~/agents of the user running this). Nothing here
reads secrets or the brain's memory; the agent's turn reads what its permissions allow.

CLI (all output JSON on stdout; create/update read a JSON body on stdin):
  cc_agents.py list | create | update | delete <id> | run <id> | tick
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

AGENTS_DIR = Path(os.environ.get("CC_AGENTS_DIR") or (Path.home() / "agents"))
HOOK_DIR = Path(os.environ.get("CC_HOOK_DIR") or Path(__file__).resolve().parent)
HOOK_PYTHON = os.environ.get("CC_HOOK_PYTHON", "/usr/bin/python3")
MIN_EVERY_MIN = 15             # nothing runs more often than every 15 minutes
MAX_BUDGET_USD = 20.0          # the owner picks the budget on the page (that press is the ask, D65)
MAX_PER_TICK = 3               # at most three agents start in one tick; the rest wait a minute
SCHEDULES = {"on call": 0, "15 min": 15, "30 min": 30, "hourly": 60, "every 6 h": 360, "daily": 1440, "weekly": 10080}

BASH_ALLOW = ("ls", "ls *", "cat *", "grep *", "rg *", "find *", "wc *", "head *", "tail *", "date", "date *",
              "git status", "git status *", "git diff *", "git log *", "git show *", "git add *", "git commit *",
              "df *", "du *", "cc-job *", "python3 -c *",
              # read-only checks an unattended agent needs (2026-10-17): status codes with the body discarded,
              # headers, git state, tests; and moving between folders. No POST pattern, no branch deletion.
              "cd *", "pwd", "curl -sI *", "curl -s -o /dev/null *", "curl -sS -o /dev/null *",
              "git rev-parse *", "git ls-files *", "git branch --show-current", "git worktree list",
              "git fetch", "git fetch --quiet", "python3 -m pytest *", "node registry/validate.js",
              "dig *", "openssl s_client *", "WebFetch")
PUSH_DENY = ("Bash(git push*)", "Bash(git push)", "Bash(git push *)", "Bash(git -C * push*)", "Bash(* git push*)")
FORCE_DENY = ("Bash(git push -f*)", "Bash(git push --force*)", "Bash(git push * -f*)", "Bash(git push * --force*)",
              "Bash(git push * +*)", "Bash(git push --delete*)", "Bash(git push * --delete*)", "Bash(git push * :*)",
              "Bash(git -C * push*)", "Bash(* git push*)")
DENY = ("Bash(rm -rf*)", "Bash(rm -rf *)", "Bash(* rm -rf *)", "Bash(rm -fr *)", "Bash(* rm -fr *)",
        "Read(**/.env)", "Read(**/.env.*)", "Edit(**/.env)", "Edit(**/.env.*)",
        "Bash(*/.env*)", "Bash(* .env*)", "Bash(cat .env*)")
ASK = ("Bash(sudo *)", "Bash(sudo:*)")
# Autonomy levels (2026-10-17, the Czar-General's ruling): 0 propose (writes only its state and sitrep), 1 branch
# (commits on its own branch in its own worktree, never pushes; the default), 2 ship (may also push its own branch
# onto main of the repo in its worktree; never force, never delete). Only the owner sets a level, on the page.
LEVELS = {0: "propose", 1: "branch", 2: "ship"}
FORBIDDEN_GROUND = ("/", "/etc", "/root", "/home", "/usr", "/var", "/boot", "/proc", "/sys")


def now() -> float:
    return time.time()


def iso(t: float | None = None) -> str:
    return dt.datetime.fromtimestamp(t if t is not None else now(), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:40] or "agent"


def _path(aid: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]{1,40}", aid or ""):
        raise ValueError("bad agent id")
    return AGENTS_DIR / f"{aid}.json"


def load(aid: str) -> dict:
    return json.loads(_path(aid).read_text())


def save(a: dict) -> None:
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    p = _path(a["id"])
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(a, indent=1))
    tmp.replace(p)


def load_all() -> list[dict]:
    if not AGENTS_DIR.is_dir():
        return []
    out = []
    for p in sorted(AGENTS_DIR.glob("*.json")):
        try:
            out.append(json.loads(p.read_text()))
        except Exception:  # noqa: BLE001  a broken file is skipped, never a dead page
            continue
    return sorted(out, key=lambda a: (int(a.get("serial") or 0), a.get("created") or "", a.get("id") or ""))


def _clean_ground(ground) -> list[str]:
    if isinstance(ground, str):
        ground = [g for g in ground.splitlines()]
    out = []
    for g in ground or []:
        raw = str(g).strip()
        if not raw:
            continue
        g = raw.rstrip("/") or "/"
        if not g.startswith("/"):
            raise ValueError(f"ground must be absolute paths: {g}")
        if g in FORBIDDEN_GROUND or ".env" in g or "/.git" in g:
            raise ValueError(f"not allowed as ground: {g}")
        out.append(g)
    return out[:8]


def validate(body: dict, existing: dict | None = None) -> dict:
    """Pure: a clean agent from a request body. Raises ValueError with a sentence the page can show."""
    a = dict(existing or {})
    if "name" in body or not existing:
        name = str(body.get("name") or "").strip()
        if not name:
            raise ValueError("an agent needs a name")
        a["name"] = name[:60]
    if "mission" in body or not existing:
        mission = str(body.get("mission") or "").strip()
        if len(mission) < 10:
            raise ValueError("say in a sentence what the agent does (its mission)")
        a["mission"] = mission[:2000]
    if "ground" in body or not existing:
        a["ground"] = _clean_ground(body.get("ground"))
    if "every_minutes" in body or not existing:
        every = int(body.get("every_minutes") if body.get("every_minutes") is not None else 1440)
        if every < 0 or (every and every < MIN_EVERY_MIN):
            raise ValueError(f"nothing runs more often than every {MIN_EVERY_MIN} minutes")
        a["every_minutes"] = every
    if "budget_usd" in body or not existing:
        b = float(body.get("budget_usd") or 1)
        if b <= 0 or b > MAX_BUDGET_USD:
            raise ValueError(f"budget per run must be between 0 and {MAX_BUDGET_USD:g} USD")
        a["budget_usd"] = round(b, 2)
    if "model" in body or not existing:
        m = str(body.get("model") or "").strip()
        if m and not re.fullmatch(r"[A-Za-z0-9._:\-]{1,80}", m):
            raise ValueError("model name has characters it cannot have")
        a["model"] = m
    if "enabled" in body or not existing:
        a["enabled"] = bool(body.get("enabled", True))
    if "level" in body or not existing:
        lv = int(body.get("level") if body.get("level") is not None else 1)
        if lv not in LEVELS:
            raise ValueError("autonomy level is 0 (propose), 1 (branch) or 2 (ship)")
        a["level"] = lv
    if "callsign" in body or not existing:
        cs = str(body.get("callsign") or "").strip()
        if cs and not re.fullmatch(r"[A-Za-z0-9 ._'-]{1,30}", cs):
            raise ValueError("a callsign is up to 30 letters, digits, spaces or . _ ' -")
        a["callsign"] = cs
    if "code" in body or not existing:
        code = str(body.get("code") or "").strip().upper()
        if code and not re.fullmatch(r"[A-Z]{2,12}", code):
            raise ValueError("an institution name for the tag is 2 to 12 letters, like LAW or LOGISTICS")
        a["code"] = code
    if "post" in body or not existing:
        post = str(body.get("post") or "").strip()
        if post and not re.fullmatch(r"[A-Za-z0-9 ._'&/-]{1,40}", post):
            raise ValueError("a post name is up to 40 plain characters")
        a["post"] = post
    return a


def next_serial() -> int:
    """Serial numbers are never reused: a counter file, bumped under a rename, survives retirement."""
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    f = AGENTS_DIR / ".serial"
    try:
        n = int(f.read_text().strip() or 0)
    except (FileNotFoundError, ValueError):
        n = 0
    seen = [int(a.get("serial") or 0) for a in load_all()]
    n = max([n, *seen]) + 1
    tmp = f.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(str(n))
    tmp.replace(f)
    return n


def next_code_serial(code: str) -> int:
    """Number within an institution: LAW-1, LAW-2. Never reused, retired agents included."""
    seen = [int(a.get("code_serial") or 0) for a in load_all() if a.get("code") == code]
    trash = AGENTS_DIR / ".trash"
    if trash.is_dir():
        for p in trash.glob("*.json"):
            try:
                t = json.loads(p.read_text())
                if t.get("code") == code:
                    seen.append(int(t.get("code_serial") or 0))
            except Exception:  # noqa: BLE001
                pass
    return max([0, *seen]) + 1


def tag(a: dict) -> str:
    """Pure: the agent's designation: LAW-1 "Magistrate" with an institution code, else A-007 "Sentinel"."""
    t = f"{a['code']}-{int(a.get('code_serial') or 1)}" if a.get("code") else f"A-{int(a.get('serial') or 0):03d}"
    return f'{t} "{a["callsign"]}"' if a.get("callsign") else t


def create(body: dict) -> dict:
    a = validate(body)
    base = slug(a["name"])
    aid, n = base, 2
    while _path(aid).exists():
        aid, n = f"{base[:36]}-{n}", n + 1
    if a.get("code"):
        a["code_serial"] = next_code_serial(a["code"])
    a.update({"id": aid, "serial": next_serial(), "created": iso(), "last_run": None, "last_job": None, "runs": 0})
    save(a)
    (AGENTS_DIR / aid / "sitreps").mkdir(parents=True, exist_ok=True)
    return a


def update(aid: str, body: dict) -> dict:
    old = load(aid)
    a = validate(body, old)
    if a.get("code") and a.get("code") != old.get("code"):
        a["code_serial"] = next_code_serial(a["code"])
    save(a)
    return a


def delete(aid: str) -> dict:
    p = _path(aid)
    if p.exists():
        trash = AGENTS_DIR / ".trash"
        trash.mkdir(parents=True, exist_ok=True)
        p.replace(trash / f"{aid}.{int(now())}.json")   # kept, never erased; sitreps stay in place
    return {"ok": True, "id": aid}


def _ts(s: str | None) -> float:
    if not s:
        return 0.0
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
    except ValueError:
        return 0.0


def next_due(a: dict) -> float:
    return _ts(a.get("last_run")) + 60 * int(a.get("every_minutes") or 1440)


def due(a: dict, t: float | None = None) -> bool:
    if not int(a.get("every_minutes") or 0):      # on call: runs only when someone presses run now
        return False
    return bool(a.get("enabled")) and (t if t is not None else now()) >= next_due(a)


def sitrep_dir(a: dict) -> Path:
    return AGENTS_DIR / a["id"] / "sitreps"


def prompt(a: dict, stamp: str) -> str:
    """Pure: the charter the agent's turn reads."""
    ground = "\n".join(f"- {g}" for g in a.get("ground") or []) or "- (none: report only)"
    sit = sitrep_dir(a) / f"{stamp}.md"
    return (
        f"You are the standing agent {tag(a)}, \"{a['name']}\"{(', of the post ' + a['post']) if a.get('post') else ''}, of this brain. This turn was started by its schedule, "
        f"not by a person; nobody is watching it live.\n\n"
        f"MISSION\n{a['mission']}\n\n"
        f"GROUND (the only places you may write, besides your sitrep)\n{ground}\n\n"
        "STANDING ORDERS\n"
        "1. Do one useful round of the mission and stop. Small, inspectable steps; no long loops.\n"
        "2. Write only inside your ground. Work that belongs elsewhere becomes a proposal in your sitrep.\n"
        "3. Do not start other agents. Nothing that leaves the brain (send, publish, pay): propose it instead.\n"
        "4. Never read or print secrets (.env, keys, tokens). Say \"(not checkable)\" instead of guessing.\n"
        + {0: "5. Autonomy level 0 (propose): write only your state and sitrep; every change is a proposal.\n\n",
           1: "5. Autonomy level 1 (branch): commit on your own branch in your worktree, by exact path; never push.\n\n",
           2: "5. Autonomy level 2 (ship): commit on your own branch in your worktree, by exact path. You may ship it with "
              "`git push origin HEAD:main` only when (a) the repo's tests pass and you name the count in your sitrep, "
              "(b) the diff holds no secret, no private material and no employer name, (c) the change is one small "
              "reviewable step. Never force, never delete a branch, never push anything else. Name the pushed commit id "
              "in your sitrep; the Inspector General audits every ship.\n\n"}[
            int(a.get("level", 1)) if int(a.get("level", 1)) in LEVELS else 1]
        + f"Before you end, write your sitrep to {sit} in this shape:\n"
        + f"SITREP {tag(a)} <time UTC>\n1. STATE ON | DEGRADED | OFF, one line why\n2. DONE what changed, with full paths\n"
        + "3. FOUND what you noticed\n4. OWED one word or one press each from the owner, with the exact address\n"
        + "5. NEXT at most three\n"
    )


def settings(a: dict) -> dict:
    """Pure: Claude Code settings for the agent's turn: its own write area, the card hook for the rest."""
    lv = int(a.get("level", 1))
    ground = list(a.get("ground") or [])
    if lv == 0:                                   # propose: no worktree writes
        ground = [g for g in ground if "/wt/" not in g]
    write = [*ground, str(AGENTS_DIR / a["id"])]
    allow = ([f"Edit(//{w.lstrip('/')}/**)" for w in write]
             + [c if c == "WebFetch" else f"Bash({c})" for c in BASH_ALLOW])
    if lv == 2:
        allow += ["Bash(git push origin HEAD:main)"]
    deny = list(DENY) + (list(FORCE_DENY) if lv == 2 else list(PUSH_DENY))
    return {
        "hooks": {"PermissionRequest": [{"hooks": [{"type": "command",
                                                    "command": f"{HOOK_PYTHON} {HOOK_DIR / 'cc-permit-hook.py'}", "timeout": 960}]}],
                  "PostToolUse": [{"matcher": "Write|Edit|MultiEdit|NotebookEdit",
                                   "hooks": [{"type": "command", "command": f"{HOOK_PYTHON} {HOOK_DIR / 'cc-post-hook.py'}", "timeout": 10}]}]},
        "permissions": {"allow": allow, "ask": list(ASK), "deny": deny},
    }


def job_command(a: dict, prompt_path: Path, settings_path: Path) -> str:
    """Pure: one shell line for cc-job."""
    parts = ["claude", "-p", "--output-format", "text", "--max-budget-usd", str(a.get("budget_usd") or 1),
             "--settings", str(settings_path), "--add-dir", str(AGENTS_DIR / a["id"])]
    for g in a.get("ground") or []:
        parts += ["--add-dir", g]
    if a.get("model"):
        parts += ["--model", a["model"]]
    line = " ".join(shlex.quote(p) for p in parts)
    return (line + ' ${CC_MCP_CONFIG:+--strict-mcp-config --mcp-config "$CC_MCP_CONFIG"}'
            + f' -- "$(cat {shlex.quote(str(prompt_path))})"')


def parse_job(out: str) -> str | None:
    m = re.search(r"\b(J\d{6,})\b", out or "")
    return m.group(1) if m else None


def open_job(a: dict, cmd: str, cwd: str) -> str:
    r = subprocess.run(["cc-job", "run", "-C", cwd, "-t", f"{tag(a)} {a['name']}", "--", cmd],
                       capture_output=True, text=True, timeout=60)
    jid = parse_job((r.stdout or "") + (r.stderr or ""))
    if r.returncode != 0 or not jid:
        raise RuntimeError(((r.stdout or "") + (r.stderr or "")).strip()[:200] or f"cc-job rc {r.returncode}")
    return jid


def run(aid: str, opener=open_job) -> dict:
    a = load(aid)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    d = AGENTS_DIR / a["id"]
    sitrep_dir(a).mkdir(parents=True, exist_ok=True)
    pp, sp = d / "prompt.md", d / "settings.json"
    pp.write_text(prompt(a, stamp))
    sp.write_text(json.dumps(settings(a), indent=1))
    cwd = next((g for g in a.get("ground") or [] if Path(g).is_dir()), str(d))
    a["last_run"] = iso()                       # set first: a failing launch does not retry every minute
    try:
        a["last_job"] = opener(a, job_command(a, pp, sp), cwd)
        a["last_error"] = None
        a["runs"] = int(a.get("runs") or 0) + 1
    except Exception as e:  # noqa: BLE001
        a["last_error"] = f"{type(e).__name__}: {e}"[:200]
    save(a)
    return a


def tick(opener=open_job, t: float | None = None) -> list[dict]:
    started = []
    for a in load_all():
        if len(started) >= MAX_PER_TICK:
            break
        if due(a, t):
            started.append(run(a["id"], opener=opener))
    return started


def last_sitrep(a: dict) -> dict | None:
    d = sitrep_dir(a)
    if not d.is_dir():
        return None
    files = sorted(d.glob("*.md"))
    if not files:
        return None
    f = files[-1]
    return {"path": str(f), "name": f.name, "text": f.read_text(errors="replace")[:1500]}


def view() -> dict:
    agents = []
    for a in load_all():
        agents.append({**a, "tag": tag(a), "next_due": iso(next_due(a)) if (a.get("enabled") and int(a.get("every_minutes") or 0)) else None, "sitrep": last_sitrep(a)})
    return {"agents": agents, "dir": str(AGENTS_DIR), "schedules": SCHEDULES,
            "limits": {"min_every_minutes": MIN_EVERY_MIN, "max_budget_usd": MAX_BUDGET_USD, "max_per_tick": MAX_PER_TICK}}


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "list"
    try:
        if cmd == "list":
            out = view()
        elif cmd == "create":
            out = {"ok": True, "agent": create(json.loads(sys.stdin.read() or "{}"))}
        elif cmd == "update":
            out = {"ok": True, "agent": update(argv[2], json.loads(sys.stdin.read() or "{}"))}
        elif cmd == "delete":
            out = delete(argv[2])
        elif cmd == "run":
            out = {"ok": True, "agent": run(argv[2])}
        elif cmd == "tick":
            out = {"ok": True, "started": [{"id": a["id"], "job": a.get("last_job"), "error": a.get("last_error")} for a in tick()]}
        else:
            out = {"ok": False, "error": f"unknown command {cmd}"}
    except (ValueError, FileNotFoundError, KeyError) as e:
        out = {"ok": False, "error": str(e) if not isinstance(e, FileNotFoundError) else "no such agent"}
    print(json.dumps(out))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
