"""cc_halt: the kill switch (2026-10-25). One file, read by everything that starts work.

HALT file: <hands home>/.cc-bridge/HALT (on a split box /home/hands/.cc-bridge/HALT). The hands
user writes it (cc-job halt / resume); the bridge user reads it (same group, directory 755). While
it exists: the bridge refuses /jobs/start (so `cc-job run` and every standing agent's job), the tick
skips its standing order, and cc_agents.py refuses tick and run. Running jobs are left alone unless
`cc-job halt --kill` asked for them. Nothing here touches permits, the posture, or the brain's chat.

Budget HALT: <world>/ops/finance/budgets.tsv (written by the finance thread) has a `state` column
that reads HALT-<post> when a post's weekly cap is spent; a job whose title starts with "<post>:"
is refused while that row says so. No file, no state column, no match: no budget halt.

Standard library only; installed beside cc-job as ~/.local/bin/cc_halt.py so cc-job can import it.
"""
from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path

HALT_FILE = "HALT"
LOG_FILE = "halt.log"
BUDGETS_REL = Path("ops") / "finance" / "budgets.tsv"


def halt_file(hands_home) -> Path:
    return Path(hands_home) / ".cc-bridge" / HALT_FILE


def halted(hands_home) -> str | None:
    """The reason the box is halted, or None. A file that exists but cannot be read is still a halt."""
    p = halt_file(hands_home)
    try:
        if not p.exists():
            return None
    except OSError:
        return None
    try:
        reason = p.read_text().strip().splitlines()
    except OSError:
        return f"HALT: (reason unreadable at {p})"
    return "HALT: " + (reason[0].strip() if reason and reason[0].strip() else "halted")


def log(hands_home, line: str) -> None:
    """One line, UTC stamped, to <hands home>/.cc-bridge/halt.log. Never raises."""
    try:
        d = Path(hands_home) / ".cc-bridge"
        d.mkdir(parents=True, exist_ok=True)
        with (d / LOG_FILE).open("a") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {line.strip()}\n")
    except OSError:
        pass


def set_halt(hands_home, reason: str = "", by: str = "") -> str:
    reason = (reason or "").strip() or "halted"
    p = halt_file(hands_home)
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p.write_text(f"{reason}\n# set {stamp}{' by ' + by if by else ''}\n")
    log(hands_home, f"halt{' by ' + by if by else ''}: {reason}")
    return reason


def clear_halt(hands_home, by: str = "") -> bool:
    p = halt_file(hands_home)
    try:
        p.unlink()
        was = True
    except FileNotFoundError:
        was = False
    log(hands_home, f"resume{' by ' + by if by else ''}: {'cleared' if was else 'was not halted'}")
    return was


def budget_halts(world_dir) -> dict:
    """{post: state} for every row of ops/finance/budgets.tsv whose state reads HALT-<post>
    (a row with a `post` column and state HALT counts too). Tolerant: anything missing = {}."""
    if not world_dir:
        return {}
    p = Path(world_dir) / BUDGETS_REL
    try:
        lines = [ln for ln in p.read_text().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    except OSError:
        return {}
    if not lines:
        return {}
    head = [h.strip().lower() for h in lines[0].split("\t")]
    if "state" not in head:
        return {}
    si = head.index("state")
    pi = head.index("post") if "post" in head else None
    out = {}
    for ln in lines[1:]:
        cells = ln.split("\t")
        state = cells[si].strip() if si < len(cells) else ""
        if not state.upper().startswith("HALT"):
            continue
        post = state[5:].strip() if state.upper().startswith("HALT-") else ""
        if not post and pi is not None and pi < len(cells):
            post = cells[pi].strip()
        if post:
            out[post] = state
    return out


def budget_refusal(title: str, world_dir) -> str | None:
    t = (title or "").strip().lower()
    for post, state in budget_halts(world_dir).items():
        if t.startswith(post.lower() + ":"):
            return f"HALT: budget for {post} is spent this week ({state} in ops/finance/budgets.tsv)"
    return None


def refusal(hands_home, world_dir, title: str = "") -> str | None:
    """Why a new job may not start now: the HALT file first, then the budget. None = go."""
    return halted(hands_home) or budget_refusal(title, world_dir)


def _proc_start(pid: int) -> float | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        ticks = int(stat.rsplit(")", 1)[1].split()[19])      # field 22, starttime
        btime = next(int(ln.split()[1]) for ln in Path("/proc/stat").read_text().splitlines() if ln.startswith("btime "))
        return btime + ticks / os.sysconf("SC_CLK_TCK")
    except Exception:  # noqa: BLE001
        return None


def running_jobs(jobs_json) -> list[dict]:
    try:
        items = json.loads(Path(jobs_json).read_text())
    except (OSError, ValueError):
        return []
    return [r for r in items if isinstance(r, dict) and r.get("ended") is None and r.get("pid")]


def kill_jobs(jobs_json, sig=signal.SIGTERM, killer=os.killpg) -> list[str]:
    """Signal the process group of every running cc-job (the bridge starts each in its own session,
    so the group is the job and its children). On a split box the group leader is root's sudo, which
    we may not signal; the hands' bash and its children are, and sudo exits when they do. A pid that
    the kernel reused since the job started is skipped. Returns the ids signalled."""
    out = []
    for r in running_jobs(jobs_json):
        pid = int(r["pid"])
        t0 = _proc_start(pid)
        if r.get("started") and t0 is not None and t0 > float(r["started"]) + 30:
            continue
        try:
            killer(pid, sig)
            out.append(str(r.get("id")))
        except (ProcessLookupError, PermissionError):
            continue
        except OSError:
            continue
    return out
