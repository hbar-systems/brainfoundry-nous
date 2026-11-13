"""The Codex seat's gated write mode (2026-11-03, CC_CODEX_WRITE=1, default off).

The Codex seat answers with the same powers as the Claude seat (edits, commands, the owner's MCP
tools) and every one of them passes the same card gate (cc-bridge.py `_box_ask`, the same
posture and sudo rules). Measured on Codex CLI 0.162.1 with a stub model endpoint (E7-E report):

- `codex exec` does run hooks (OpenAI's page says otherwise), but only trusted ones. An untrusted
  hook is skipped without a word, so the gate is not the hook file: it is the hook file plus its
  trust entry, checked before every turn.
- Trust is read from `$CODEX_HOME/config.toml` only (`[hooks.state."<file>:pre_tool_use:0:0"]
  trusted_hash = "sha256:..."`); the same key passed with `-c` is ignored. So the write mode
  cannot use `--ignore-user-config`, and the bridge owns that file: it is rewritten before every
  turn with a managed header, and a config.toml without that header refuses the mode.
- The hash comes from Codex itself (`codex app-server`, method `hooks/list`, `currentHash`); the
  check then reads `hooks/list` again and requires `trustStatus: "trusted"` on exactly our hook.
- A hook that exits non-zero or outlives its timeout FAILS OPEN (the command ran). So the hook
  (cc-codex-hook.py) catches everything and prints a deny, gives up on the bridge well inside its
  Codex timeout, and the gate check runs it once with a probe call that must come back a deny.
- Commands run under `shell_environment_policy.inherit="core"` do not see CC_ASK_TOKEN; the hook does.
- Workspace-repo hooks (`<cwd>/.codex/hooks.json`) are listed untrusted and do not run.

Pure helpers and the gate check; the bridge runs the processes.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
from pathlib import Path

from cc_codex import Unsafe, _MODEL, _SID

MODE = "workspace-write"
LABEL = "Codex (gated)"
HEADER = "# managed by cc-bridge (CC_CODEX_WRITE): rewritten before every Codex turn; edits here are lost"
EVENT_KEY = "pre_tool_use:0:0"

# CC_CODEX_WRITE_SANDBOX=off: no Codex sandbox, the cards alone (as on the Claude seat). For kernels
# where bubblewrap cannot start (Ubuntu 24.04 restricts user namespaces): there workspace-write runs
# no command at all, allowed or not. The owner's choice; the default is the sandbox.
SANDBOXES = {"workspace-write": "workspace-write", "off": "danger-full-access"}


def _common(sandbox: str) -> list[str]:
    return ["--json", "--skip-git-repo-check", "--ignore-rules",
            "-c", f'sandbox_mode="{sandbox}"',
            "-c", 'approval_policy="never"',
            "-c", 'web_search="disabled"',
            "-c", 'shell_environment_policy.inherit="core"']
_FORBIDDEN = (
    "--dangerously-bypass-approvals-and-sandbox", "--yolo", "--approve-for-me", "--not-so-yolo",
    "--full-auto", "--dangerously-bypass-hook-trust", "bypass_hook_trust", "--search", "--add-dir",
    "--oss", "--worktree", "--profile", "on-request", "on-failure", "untrusted",
    "--disable", "features.hooks", "hooks.",
)
# What the Codex process sees: the seat's names plus what the hook needs to reach the bridge.
ENV_KEYS = ("HOME", "USER", "PATH", "LANG", "LC_ALL", "CODEX_HOME",
            "CC_PORT", "CC_BASE", "CC_ASK_TOKEN", "CC_PERMIT_TTL")


def env(base: dict) -> dict:
    out = {k: str(base[k]) for k in ENV_KEYS if base.get(k)}
    out["TERM"] = "dumb"
    out["NO_COLOR"] = "1"
    return out


def build_cmd(bin_path: str, cwd: str, session_id: str | None = None, model: str = "",
              sandbox: str = MODE, extra: list[str] | None = None) -> list[str]:
    """`codex exec` for one gated turn; `extra` is more `-c k=v` (a provider, in the tests)."""
    if sandbox not in SANDBOXES.values():
        raise Unsafe("not a sandbox this seat runs")
    if session_id and not _SID.match(session_id):
        raise Unsafe("not a Codex session id")
    if model and not _MODEL.match(model):
        raise Unsafe("not a model name")
    if session_id:
        cmd = [bin_path, "exec", "resume", *_common(sandbox)]
    else:
        cmd = [bin_path, "exec", *_common(sandbox), "-s", sandbox, "-C", cwd, "--color", "never"]
    cmd += list(extra or [])
    if model:
        cmd += ["-m", model]
    if session_id:
        cmd += [session_id]
    cmd += ["-"]
    assert_gated(cmd, sandbox)
    return cmd


def assert_gated(cmd: list[str], sandbox: str = MODE) -> None:
    """Raise Unsafe unless the command is an approval-never exec with hooks on, in the sandbox the
    owner chose (danger-full-access only when they set CC_CODEX_WRITE_SANDBOX=off)."""
    if sandbox not in SANDBOXES.values():
        raise Unsafe("not a sandbox this seat runs")
    if sandbox != "danger-full-access" and any("danger-full-access" in a for a in cmd):
        raise Unsafe("forbidden flag: danger-full-access")
    if len(cmd) < 2 or cmd[1] != "exec":
        raise Unsafe("not codex exec")
    for i, a in enumerate(cmd):
        if i > 0 and cmd[i - 1] in ("-C", "--cd"):
            continue                           # the working directory: a path, not a switch
        low = a.lower()
        if any(f == low or f in low for f in _FORBIDDEN):
            raise Unsafe(f"forbidden flag: {a}")
    for n in (f'sandbox_mode="{sandbox}"', 'approval_policy="never"', 'web_search="disabled"',
              'shell_environment_policy.inherit="core"'):
        if n not in cmd:
            raise Unsafe(f"missing {n}")
    if "-p" in cmd or "--enable" in cmd:
        raise Unsafe("a profile or feature switch would load")
    if "--ignore-rules" not in cmd:
        raise Unsafe("execpolicy rules would load")
    if "-s" in cmd and cmd[cmd.index("-s") + 1] != sandbox:
        raise Unsafe("sandbox not the chosen one")
    if sum(1 for a in cmd if a.startswith("sandbox_mode=")) != 1:
        raise Unsafe("more than one sandbox")


# ------------------------------------------------------------ the bridge-owned files ----
def hook_command(hook_python: str, hook_script) -> str:
    return f"{hook_python} {hook_script}"


def hooks_json(hook_python: str, hook_script, ttl: int) -> str:
    """One PreToolUse hook, no matcher: every shell command, patch and MCP call reaches it. Codex's
    timeout sits 120 s past the permit, the hook's own wait 30 s past it (a timeout fails open)."""
    return json.dumps({"hooks": {"PreToolUse": [{"hooks": [
        {"type": "command", "command": hook_command(hook_python, hook_script), "timeout": int(ttl) + 120}]}]}},
        indent=1) + "\n"


def _q(s: str) -> str:
    return json.dumps(str(s))          # a TOML basic string is a JSON string for our inputs


def mcp_toml(mcp: dict) -> str:
    """The owner's MCP servers (the Claude seat's CC_MCP_CONFIG, {"mcpServers": {...}}) as Codex
    [mcp_servers.<name>] tables. Only command servers with plain names; anything else is skipped."""
    out = []
    for name, s in sorted(((mcp or {}).get("mcpServers") or {}).items()):
        if not re.match(r"^[A-Za-z0-9_-]{1,64}$", str(name)) or not isinstance(s, dict) or not s.get("command"):
            continue
        out.append(f"[mcp_servers.{name}]")
        out.append(f"command = {_q(s['command'])}")
        out.append("args = [" + ", ".join(_q(a) for a in (s.get("args") or [])) + "]")
        e = {str(k): str(v) for k, v in (s.get("env") or {}).items() if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(k))}
        if e:
            out.append("env = { " + ", ".join(f"{k} = {_q(v)}" for k, v in sorted(e.items())) + " }")
        out.append("")
    return "\n".join(out)


def config_toml(codex_home, trusted_hash: str | None, mcp: dict | None = None) -> str:
    lines = [HEADER, ""]
    if trusted_hash:
        if not re.match(r"^sha256:[0-9a-f]{64}$", trusted_hash):
            raise Unsafe("not a hook hash")
        lines += [f"[hooks.state.{_q(hook_key(codex_home))}]", f"trusted_hash = {_q(trusted_hash)}", ""]
    return "\n".join(lines) + "\n" + mcp_toml(mcp or {})


def hook_key(codex_home) -> str:
    return f"{Path(codex_home) / 'hooks.json'}:{EVENT_KEY}"


def config_ours(text: str | None) -> bool:
    """An absent config.toml, or one this module wrote. Anything else is the owner's: refuse."""
    return not (text or "").strip() or (text or "").startswith(HEADER)


# ------------------------------------------------------------ the check ----
def hooks_list(bin_path: str, cwd: str, spawn, timeout: int = 20) -> list[dict]:
    """The hooks Codex itself sees for `cwd`, from `codex app-server` (stdio JSON-RPC). The server
    quits when its stdin closes, so stdin stays open until the answer is read.
    `spawn(argv) -> Popen` (text, stdin and stdout piped) runs it as the hands, in the seat's env."""
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientInfo": {"name": "cc-bridge", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "hooks/list", "params": {"cwds": [cwd]}}]
    proc = spawn([bin_path, "app-server"])
    found: list = []
    timer = threading.Timer(timeout, proc.kill)
    timer.start()
    try:
        proc.stdin.write("".join(json.dumps(m) + "\n" for m in msgs))
        proc.stdin.flush()
        for line in proc.stdout:
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(m, dict) and m.get("id") == 2:
                data = ((m.get("result") or {}).get("data") or [{}])
                found.append(list((data[0] or {}).get("hooks") or []))
                break
    finally:
        timer.cancel()
        try:
            proc.stdin.close()
        except OSError:
            pass
        proc.kill()
        proc.wait()
    if not found:
        raise RuntimeError("codex app-server gave no hooks/list answer")
    return found[0]


def ours(hooks: list[dict], codex_home, command: str) -> dict | None:
    key = hook_key(codex_home)
    h = next((h for h in hooks if h.get("key") == key), None)
    if h is None or h.get("command") != command or h.get("handlerType") != "command" or not h.get("enabled"):
        return None
    if h.get("matcher") not in (None, "", "*") or h.get("async"):
        return None
    return h


def verdict(hooks: list[dict], codex_home, command: str, ttl: int) -> tuple[bool, str]:
    """(ok, reason) for the second listing: our hook, trusted, unmatched, sync, timeout past the permit."""
    h = ours(hooks, codex_home, command)
    if h is None:
        return False, "the card hook is not in Codex's own hook list"
    if h.get("trustStatus") != "trusted":
        return False, f"the card hook is {h.get('trustStatus') or 'not trusted'} (Codex would skip it)"
    if int(h.get("timeoutSec") or 0) < int(ttl) + 60:
        return False, "the card hook's timeout is shorter than a permit"
    return True, "the card hook is trusted and fires before every tool call"


def probe_ok(stdout: str) -> bool:
    """The hook, run once with a probe call and no valid ask token, must print a deny."""
    try:
        d = json.loads((stdout or "").strip().splitlines()[-1])
        return d["hookSpecificOutput"]["permissionDecision"] == "deny"
    except Exception:  # noqa: BLE001
        return False


PROBE_INPUT = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                          "tool_input": {"command": "true # cc-bridge gate probe"}, "session_id": "probe"})


# ------------------------------------------------------------ the hook's mapping ----
# "*** Move to: <path>" under an Update writes the destination too (audit 2026-11-13,
# codex-gate-patch-move-destination-not-asked): it is asked as a Write of that path.
_PATCH_FILE = re.compile(r"^\*\*\* (Add File|Update File|Delete File|Move to): (.+?)\s*$", re.M)


def asks(payload: dict) -> list[tuple[str, dict]]:
    """(tool_name, tool_input) the bridge's /ask is called with for one Codex PreToolUse payload,
    in the names the Claude seat uses, so standing allows and cards read the same. A patch asks once
    per file (every file must be allowed); an unknown tool keeps its own name."""
    tool = str(payload.get("tool_name") or "")
    inp = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    cwd = str(payload.get("cwd") or "")
    if tool in ("Bash", "shell", "exec_command", "shell_command", "local_shell"):
        c = inp.get("command") if "command" in inp else inp.get("cmd")
        c = " ".join(c) if isinstance(c, list) else str(c or "")
        return [("Bash", {"command": c})]
    if tool.lower() in ("apply_patch", "applypatch", "edit", "write"):
        text = str(inp.get("command") or inp.get("patch") or inp.get("input") or "")
        files = [(m.group(1).split()[0], m.group(2)) for m in _PATCH_FILE.finditer(text)]
        if not files and inp.get("file_path"):
            files = [("Update", str(inp["file_path"]))]
        if not files:
            return [("apply_patch", {"summary": text[:200]})]
        out = []
        for verb, p in files:
            fp = p if p.startswith("/") or not cwd else str(Path(cwd) / p)
            out.append(("Write" if verb in ("Add", "Move") else "Edit", {"file_path": fp}))
        return out
    return [(tool or "unknown", inp)]


def _spawn(argv, env=None):
    return subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, env=env)
