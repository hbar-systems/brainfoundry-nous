#!/usr/bin/env python3
"""The permission shape of a reasoner turn, shared by the bridge and its jobs (2026-10-19).

Found 2026-10-18: a turn may start `cc-job run -- 'claude -p ...'`. That inner reasoner ran without the
bridge's permission hook (the bridge adds it per turn with --settings) and with whatever --permission-mode
its caller wrote, so a job could run looser than the owner's posture (auto while the posture is cards) and
without the ask rules that keep sudo on a card. Now every job command passes `check_job` before it starts:
each claude invocation gets the same settings a turn gets, and the loosening flags are refused.

Standard library only. Pure functions; the bridge supplies the posture, the settings and the agents check.
"""
from __future__ import annotations

import json
import os
import re
import shlex

POSTURES = ("cards", "auto", "judged")
ASK_ALWAYS = ["Bash(sudo *)", "Bash(sudo:*)"]


def hook_settings(posture: str, hook_python: str, hook_script, post_hook_script, ttl: int) -> str:
    """Claude Code settings JSON for a turn: the permission hook, with a timeout that outlives the
    permit; in the auto posture also the ask rules that keep sudo on a card."""
    s = {"hooks": {"PermissionRequest": [{"hooks": [
        {"type": "command", "command": f"{hook_python} {hook_script}", "timeout": ttl + 60}]}],
        # after every write the file is opened to the group, so the bridge (another user after the
        # split) can show it in the Files pane (2026-10-01)
        "PostToolUse": [{"matcher": "Write|Edit|MultiEdit|NotebookEdit", "hooks": [
        {"type": "command", "command": f"{hook_python} {post_hook_script}", "timeout": 10}]}]}}
    if posture == "auto":
        s["permissions"] = {"ask": ASK_ALWAYS}
    return json.dumps(s)


# ------------------------------------------------------------ agents' settings ----
def agent_settings_path_ok(path: str, agents_dir) -> bool:
    """The path cc_agents writes for a run: <agents dir>/<id>/settings.json, nothing else."""
    if not path or ".." in path.split("/"):
        return False
    root = os.path.normpath(str(agents_dir))
    p = os.path.normpath(path)
    return os.path.dirname(os.path.dirname(p)) == root and os.path.basename(p) == "settings.json"


def agent_settings_ok(text: str) -> bool:
    """The content cc_agents.settings() produces: the card hook, the sudo ask rules, no way around either."""
    try:
        s = json.loads(text)
        hooks = s["hooks"]["PermissionRequest"]
        cmds = [h.get("command", "") for e in hooks for h in e.get("hooks", [])]
        perm = s.get("permissions") or {}
    except Exception:  # noqa: BLE001
        return False
    if not any(c.endswith("cc-permit-hook.py") for c in cmds):
        return False
    if not all(r in (perm.get("ask") or []) for r in ASK_ALWAYS):
        return False
    return "defaultMode" not in perm and not s.get("disableAllHooks")


# ------------------------------------------------------------ the shell line ----
_OPS = ("&&", "||", "|&", ";;", ";", "|", "&", "(", ")", "\n")
_RESERVED = {"{", "}", "!", "if", "then", "elif", "else", "while", "until", "do"}
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_REDIRECT = re.compile(r"^\d*(>>?|<<?|>&|<&|&>)")
# wrappers that run the next word as the command; the options among them that take a value
_WRAPPERS = {"env": {"-u", "--unset", "-C", "--chdir"}, "nohup": set(), "exec": {"-a"}, "nice": {"-n", "--adjustment"},
             "timeout": {"-s", "--signal", "-k", "--kill-after"}, "setsid": set(), "command": set(), "builtin": set(),
             "stdbuf": {"-i", "-o", "-e"}, "ionice": {"-c", "-n", "-p"}, "chrt": set(), "taskset": set(), "time": set()}
_SHELLS = {"sh", "bash", "dash", "zsh", "ksh"}
_NPX = {"npx", "bunx", "pnpx"}
MODES_ALWAYS = {"default", "plan", "dontAsk"}
MODES_AUTO = {"auto", "acceptEdits"}


class Refused(Exception):
    pass


def _match_close(s: str, i: int, open_c: str, close_c: str) -> int:
    """Index just past the bracket that closes the one opened before i, respecting quotes."""
    depth = 1
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2; continue
        if c == "'":
            j = s.find("'", i + 1)
            i = (j if j >= 0 else len(s) - 1) + 1; continue
        if c == '"':
            i = _dquote_end(s, i + 1); continue
        if c == open_c:
            depth += 1
        elif c == close_c:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise Refused("an unclosed bracket in the command")


def _dquote_end(s: str, i: int) -> int:
    """From inside a double-quoted string, the index just past its closing quote; substitutions inside
    are checked on the way."""
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2; continue
        if c == '"':
            return i + 1
        if s.startswith("$(", i) or c == "`":
            i = _substitution(s, i); continue
        i += 1
    raise Refused("an unclosed quote in the command")


def _substitution(s: str, i: int) -> int:
    """$(...) or `...` at i: the reasoner may not be started from inside one (it could not be given its
    settings there). Returns the index past it."""
    if s[i] == "`":
        j = s.find("`", i + 1)
        if j < 0:
            raise Refused("an unclosed backtick in the command")
        inner, end = s[i + 1:j], j + 1
    else:
        end = _match_close(s, i + 2, "(", ")")
        inner = s[i + 2:end - 1]
    if _calls(_tokens(inner)):
        raise Refused("claude inside $(...) or backticks; start it as a plain command")
    return end


def _tokens(s: str) -> list:
    """Words and operators with their spans: (kind, start, end, value). Quotes are removed from values."""
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c in " \t":
            i += 1; continue
        if c == "#" and (i == 0 or s[i - 1] in " \t\n;&|("):
            j = s.find("\n", i)
            i = n if j < 0 else j; continue
        op = next((o for o in _OPS if s.startswith(o, i)), None)
        if op:
            out.append(("op", i, i + len(op), op)); i += len(op); continue
        start, val = i, []
        while i < n and s[i] not in " \t\n;&|()":
            c = s[i]
            if c == "\\":
                val.append(s[i + 1:i + 2]); i += 2
            elif c == "'":
                j = s.find("'", i + 1)
                if j < 0:
                    raise Refused("an unclosed quote in the command")
                val.append(s[i + 1:j]); i = j + 1
            elif c == '"':
                j = _dquote_end(s, i + 1)
                val.append(re.sub(r'\\(["\\$`])', r"\1", s[i + 1:j - 1])); i = j
            elif s.startswith("${", i):
                j = _match_close(s, i + 2, "{", "}")
                val.append(s[i:j]); i = j
            elif s.startswith("$(", i) or c == "`" or (c in "<>" and s.startswith("(", i + 1)):
                k = i + 1 if c in "<>" else i
                j = _substitution(s, k)
                val.append(s[i:j]); i = j
            else:
                val.append(c); i += 1
        out.append(("word", start, i, "".join(val)))
    return out


def _calls(toks: list) -> list:
    """Every command-position word that starts the reasoner or a shell with a script:
    ("claude", index of the word, index past its last argument) or ("shell", index of the script word)."""
    found, i, n = [], 0, len(toks)
    while i < n:
        # one simple command, from i to the next operator
        j = i
        while j < n and toks[j][0] == "word":
            j += 1
        k = i
        while k < j:
            w = toks[k][3]
            if w in _RESERVED or _ASSIGN.match(w):
                k += 1; continue
            if _REDIRECT.match(w):
                k += 1 if re.search(r"[<>&]\S", w) else 2; continue
            base = os.path.basename(w)
            if base in _WRAPPERS:
                takes, k = _WRAPPERS[base], k + 1
                while k < j and (toks[k][3].startswith("-") or _ASSIGN.match(toks[k][3])):
                    k += 2 if toks[k][3] in takes else 1
                if base == "timeout" and k < j:
                    k += 1                                   # the duration
                continue
            if base in _NPX:
                k += 1
                while k < j and toks[k][3].startswith("-"):
                    k += 1
                if k < j and "claude-code" in toks[k][3]:
                    found.append(("claude", k, j))
                break
            if base == "claude":
                found.append(("claude", k, j))
            elif base in _SHELLS:
                for m in range(k + 1, j):
                    a = toks[m][3]
                    if not a.startswith("-") or a.startswith("--"):
                        break
                    if "c" in a[1:]:
                        if m + 1 < j:
                            found.append(("shell", m + 1))
                        break
            elif base in ("eval", "xargs") and any(os.path.basename(t[3]) == "claude" or re.search(r"(^|[\s;&|(/])claude(\s|$)", t[3])
                                                   for t in toks[k + 1:j]):
                raise Refused(f"claude through {base}; start it as a plain command")
            break
        i = j + 1
    return found


def _check_args(args: list, posture: str, agent_ok) -> bool:
    """Refuse the flags that loosen a job's reasoner. True when an accepted agents' --settings is present."""
    agent, k = False, 0
    while k < len(args):
        a = args[k]
        if a == "--":
            break
        name, sep, val = a.partition("=")
        if name in ("--dangerously-skip-permissions", "--allow-dangerously-skip-permissions"):
            raise Refused(f"{name} is never allowed in a job; the job's reasoner asks like any turn")
        if name in ("--permission-mode", "--settings", "--allowedTools", "--allowed-tools"):
            if not sep:
                val = args[k + 1] if k + 1 < len(args) else ""
                k += 1
            if name == "--permission-mode":
                if val == "bypassPermissions":
                    raise Refused("--permission-mode bypassPermissions is never allowed in a job")
                if val in MODES_AUTO and posture != "auto":
                    raise Refused(f"--permission-mode {val} needs the auto posture; the posture is {posture}")
                if val not in MODES_ALWAYS | MODES_AUTO:
                    raise Refused(f"--permission-mode {val!r} is not one a job may use")
            elif name == "--settings":
                if not agent_ok(val):
                    raise Refused("a job's reasoner runs with the bridge's settings; drop --settings")
                agent = True
            elif posture != "auto":
                raise Refused(f"{name} would let the job skip its cards; it needs the auto posture, the posture is {posture}")
        k += 1
    return agent


def check_job(command: str, posture: str, settings: str | None, agent_ok=lambda path: False) -> str:
    """The command a job may run, or Refused with the reason. Every claude invocation (as the command
    word, after assignments and wrappers like env or nohup, or inside sh -c) gets `--settings <settings>`
    right after the word, unless it already names an agent's settings file that `agent_ok` accepts.
    `settings` None injects nothing (the box lane is off) but still refuses."""
    posture = posture if posture in POSTURES else "cards"
    toks = _tokens(command)
    edits = []                                               # (start, end, replacement), applied from the back
    for call in _calls(toks):
        if call[0] == "shell":
            _, m = call
            inner = toks[m][3]
            new = check_job(inner, posture, settings, agent_ok)
            if new != inner:
                edits.append((toks[m][1], toks[m][2], shlex.quote(new)))
            continue
        _, w, end = call
        agent = _check_args([t[3] for t in toks[w + 1:end]], posture, agent_ok)
        if settings is not None and not agent:
            edits.append((toks[w][2], toks[w][2], " --settings " + shlex.quote(settings)))
    for start, end, rep in sorted(edits, reverse=True):
        command = command[:start] + rep + command[end:]
    return command
