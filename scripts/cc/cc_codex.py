"""The Codex seat (2026-10-15): OpenAI's Codex CLI as a second reasoner beside Claude Code.

Read-only by construction. Codex CLI 0.162 has hooks (PreToolUse, PermissionRequest), but they
need a persisted trust review per hook hash, and whether they fire under `codex exec` is not
documented; an unfired hook would be an open door, not a closed one. So the seat does not rely
on them: every turn runs in Codex's own read-only sandbox (no file writes, no network for the
commands it runs), with approvals off (a blocked action fails back to the model instead of
asking), no web search, no user config (so no MCP servers or looser defaults from
~/.codex/config.toml), no execpolicy rules, and a minimal environment. `assert_restrictive`
checks every command line before it runs and refuses anything that would loosen it. The page
labels the seat "Codex (read-only)".

Fail closed: no binary or no sign-in means the turn is refused with a plain sentence; nothing
falls back to the Claude seat. The sign-in status is read from `codex login status`'s exit code
and mapped to a method word; the CLI's own output (which can name a masked key) never leaves
this module.

Pure helpers here; the bridge (cc-bridge.py) runs the process and streams the events.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

PINNED_VERSION = "0.162.1"   # scripts/cc/install-codex.sh installs exactly this
MODE = "read-only"
LABEL = "Codex (read-only)"

# The flags every turn carries, fresh or resumed. -c values are TOML.
_COMMON = [
    "--json",
    "--skip-git-repo-check",
    "--ignore-user-config",
    "--ignore-rules",
    "-c", 'sandbox_mode="read-only"',
    "-c", 'approval_policy="never"',
    "-c", 'web_search="disabled"',
    "-c", 'shell_environment_policy.inherit="core"',
]
# Anything that would let Codex write, reach the network, or skip the sandbox.
_FORBIDDEN = (
    "--dangerously-bypass-approvals-and-sandbox", "--yolo", "--approve-for-me", "--not-so-yolo",
    "--full-auto", "--dangerously-bypass-hook-trust", "--search", "--add-dir", "--oss", "--worktree",
    "workspace-write", "danger-full-access", "on-request", "on-failure", "untrusted",
)
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_SID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
# What the commands Codex runs may see: no bridge keys, no ask token, nothing of Claude's.
ENV_KEYS = ("HOME", "USER", "PATH", "LANG", "LC_ALL", "CODEX_HOME")


class Unsafe(ValueError):
    """A command line that would loosen the seat; never run."""


def binary(hands_home: str | Path, override: str = "") -> str:
    return override.strip() or str(Path(hands_home) / ".local" / "bin" / "codex")


def env(base: dict) -> dict:
    """The environment for a Codex process: a handful of names from the hands' environment."""
    out = {k: base[k] for k in ENV_KEYS if base.get(k)}
    out["TERM"] = "dumb"
    out["NO_COLOR"] = "1"
    return out


def build_cmd(bin_path: str, cwd: str, session_id: str | None = None, model: str = "",
              extra: list[str] | None = None) -> list[str]:
    """`codex exec` for one turn. The prompt goes in on stdin ("-"), never on the command line
    (sudo logs arguments). A resumed turn takes the sandbox from -c (`exec resume` has no -s/-C).
    `extra` is more `-c k=v` pairs (the local seat's provider, cc_local.py); the read-only check
    below runs over the whole line either way."""
    if session_id and not _SID.match(session_id):
        raise Unsafe("not a Codex session id")
    if model and not _MODEL.match(model):
        raise Unsafe("not a model name")
    if session_id:
        cmd = [bin_path, "exec", "resume", *_COMMON]
    else:
        cmd = [bin_path, "exec", *_COMMON, "-s", MODE, "-C", cwd, "--color", "never"]
    cmd += list(extra or [])
    if model:
        cmd += ["-m", model]
    if session_id:
        cmd += [session_id]
    cmd += ["-"]
    assert_restrictive(cmd)
    return cmd


def assert_restrictive(cmd: list[str]) -> None:
    """Raise Unsafe unless the command is a read-only, approval-never, no-search exec."""
    if len(cmd) < 2 or cmd[1] != "exec":
        raise Unsafe("not codex exec")
    for a in cmd:
        low = a.lower()
        if any(f == low or f in low for f in _FORBIDDEN):
            raise Unsafe(f"forbidden flag: {a}")
    need = ['sandbox_mode="read-only"', 'approval_policy="never"', 'web_search="disabled"']
    for n in need:
        if n not in cmd:
            raise Unsafe(f"missing {n}")
    if "--ignore-user-config" not in cmd or "--ignore-rules" not in cmd:
        raise Unsafe("user config or rules would load")
    if "-s" in cmd and cmd[cmd.index("-s") + 1] != MODE:
        raise Unsafe("sandbox not read-only")


def status(bin_path: str, run=None, timeout: int = 20) -> dict:
    """{"installed", "signedIn", "method", "mode", "label"}: never the CLI's own words.
    `run(argv) -> CompletedProcess` runs as the hands user (the bridge passes its wrapper)."""
    st = {"installed": False, "signedIn": False, "method": None, "mode": MODE, "label": LABEL}
    if not Path(bin_path).exists():
        st["reason"] = "not installed"
        return st
    st["installed"] = True
    try:
        out = (run or _run)([bin_path, "login", "status"], timeout)
    except Exception as e:
        st["reason"] = f"status check failed ({type(e).__name__})"
        return st
    text = ((out.stdout or "") + " " + (out.stderr or "")).lower()
    if out.returncode == 0 and "not logged in" not in text:
        st["signedIn"] = True
        st["method"] = "chatgpt" if "chatgpt" in text else "api-key" if ("api key" in text or "api-key" in text) else "other"
    else:
        st["reason"] = "not signed in"
    return st


def _run(argv: list[str], timeout: int):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def refusal(st: dict) -> str | None:
    """The sentence a refused turn shows, or None when the seat can answer."""
    if not st.get("installed"):
        return ("The Codex seat is not installed on this box (no codex binary for the hands user). "
                "This turn was not answered, and nothing fell back to the Claude seat. "
                "Install it with scripts/cc/install-codex.sh, then sign in with ChatGPT.")
    if not st.get("signedIn"):
        return ("The Codex seat is not signed in. This turn was not answered, and nothing fell back to the "
                "Claude seat. Use Sign in with ChatGPT, then send again.")
    return None


def brief(item: dict) -> tuple[str, str] | None:
    """(tool name, one-line brief) for an item the page shows as a tool line; None otherwise."""
    t = item.get("type")
    if t == "command_execution":
        return "shell", "run: " + " ".join(str(item.get("command") or "").split())[:140]
    if t == "file_change":
        paths = [str(c.get("path") or "") for c in (item.get("changes") or []) if isinstance(c, dict)]
        return "edit", "edit (refused by the sandbox): " + ", ".join(paths)[:140]
    if t == "mcp_tool_call":
        return "mcp", f"{item.get('server', '')}.{item.get('tool', '')}"[:140]
    if t == "web_search":
        return "search", "search: " + str(item.get("query") or "")[:140]
    return None


def parse_line(line: str) -> dict | None:
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        return None
    return ev if isinstance(ev, dict) else None


def is_auth_error(msg: str) -> bool:
    low = (msg or "").lower()
    return any(s in low for s in ("401", "unauthorized", "not logged in", "login", "sign in", "authentication"))
