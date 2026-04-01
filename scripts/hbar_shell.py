#!/usr/bin/env python3
"""
hbar-shell v0 — chat-assisted governance shell over hbar.py + NodeOS

Usage:
    python scripts/hbar_shell.py

Commands:
    look                    full governance state (status + pending + active permits)
    pending                 list PENDING proposals
    approve <id>            approve + execute a proposal (uses session permit)
    deny <id> [--note ..]   deny a proposal (uses session permit)
    permit <reason>         request a governed_git permit, store in session
    plan push               governed push sequence — permit→preview→approve→push→approve
    plan preview            preview sequence using session permit
    plan commit [msg]       commit sequence using session permit
    intent <text>           LLM-assisted plan from natural-language intent (push/preview only)
    run <hbar args>         pass-through to hbar.py
    history [N]             last N audit events (default 10)
    help                    this message
    exit / quit             end session

Environment:
    HBAR_NODEOS_URL   NodeOS base URL (default: http://localhost:8001)
    HBAR_LLM_URL      Ollama base URL   (default: http://localhost:11435)
    HBAR_LLM_MODEL    Ollama model name (default: llama3.2:1b)
"""

import json
import os
import re
import subprocess
import sys
import time
import uuid
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# hbar.py subprocess interface
# ---------------------------------------------------------------------------

_HBAR = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hbar.py")]

# ---------------------------------------------------------------------------
# LLM transport (Ollama — confirmed running at host port 11435)
# Override via HBAR_LLM_URL / HBAR_LLM_MODEL
# ---------------------------------------------------------------------------

_LLM_URL   = os.getenv("HBAR_LLM_URL",   "http://localhost:11435")
_LLM_MODEL = os.getenv("HBAR_LLM_MODEL", "llama3.2:3b")  # 1b collapses to push; 3b is minimum viable

# ---------------------------------------------------------------------------
# Local state directory  (~/.hbar/)
# ---------------------------------------------------------------------------

_HBAR_DIR = Path.home() / ".hbar"


def _load_identity() -> str:
    """
    Load operator_id from ~/.hbar/identity.yaml.
    Returns "operator" (unchanged default) if the file is absent or malformed.
    Only reads the operator_id field — nothing else.
    """
    identity_path = _HBAR_DIR / "identity.yaml"
    if not identity_path.exists():
        return "operator"
    try:
        for line in identity_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("operator_id:"):
                val = line.split(":", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    except OSError:
        pass
    return "operator"


def _log_event(s: "Session", event_type: str, **fields) -> None:
    """
    Append a structured event to ~/.hbar/log.jsonl.
    Never raises — log failures are silently dropped.
    """
    try:
        _HBAR_DIR.mkdir(parents=True, exist_ok=True)
        event = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "session_id": s.session_id,
            "operator_id": s.operator_id,
            "event_type": event_type,
            **fields,
        }
        with (_HBAR_DIR / "log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, separators=(",", ":")) + "\n")
    except Exception:
        pass


def _load_intent_context(n: int = 3) -> str:
    """
    Read the last n successful write_commit extractions from the local log
    and return a formatted context block for injection into the intent prompt.
    Returns empty string if no history exists.
    """
    log_path = _HBAR_DIR / "log.jsonl"
    if not log_path.exists():
        return ""
    hits = []
    try:
        with log_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (ev.get("event_type") == "intent_run"
                        and ev.get("extracted_type") == "write_commit"
                        and ev.get("extracted_path")):
                    hits.append(ev)
    except OSError:
        return ""
    if not hits:
        return ""
    recent = hits[-n:]
    lines = ["RECENT SUCCESSFUL EXTRACTIONS (from your session history):"]
    for ev in recent:
        text = ev.get("intent_text", "")[:60]
        path = ev.get("extracted_path", "")
        lines.append(f'  "{text}…" → {path}')
    return "\n".join(lines) + "\n\n"


# ---------------------------------------------------------------------------
# Operator orientation context  (~/.hbar/context.yaml) — Phase 7D
# ---------------------------------------------------------------------------

def _load_context() -> dict:
    """
    Load focus and notes from ~/.hbar/context.yaml.
    Returns {"focus": "", "notes": []} if the file is absent or unreadable.
    Parses only the two known keys; all other lines are ignored.
    """
    ctx: dict = {"focus": "", "notes": []}
    path = _HBAR_DIR / "context.yaml"
    if not path.exists():
        return ctx
    try:
        in_notes = False
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("focus:"):
                ctx["focus"] = line[len("focus:"):].strip().strip('"').strip("'")
                in_notes = False
            elif line == "notes:":
                in_notes = True
            elif in_notes and line.startswith("- "):
                note = line[2:].strip().strip('"').strip("'")
                if note:
                    ctx["notes"].append(note)
            elif line and not line.startswith("#") and not line.startswith("-"):
                in_notes = False
    except OSError:
        pass
    return ctx


def _save_context(ctx: dict) -> bool:
    """
    Write focus and notes to ~/.hbar/context.yaml.
    Returns True on success, prints error and returns False on failure.
    """
    try:
        _HBAR_DIR.mkdir(parents=True, exist_ok=True)
        lines = [f'focus: "{ctx.get("focus", "")}"', "notes:"]
        for note in ctx.get("notes", []):
            lines.append(f'  - "{note.replace(chr(34), chr(92) + chr(34))}"')
        (_HBAR_DIR / "context.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    except OSError as e:
        print(f"  error: could not save context: {e}")
        return False


def _hbar(*args, live: bool = False):
    """Run hbar.py. If live=True, stream stdout/stderr directly to terminal."""
    if live:
        r = subprocess.run(_HBAR + list(args))
        return r.returncode, "", ""
    r = subprocess.run(_HBAR + list(args), capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def _hbar_json(*args):
    """Run hbar.py --json ..., return (dict|None, error_str|None)."""
    rc, out, err = _hbar("--json", *args)
    if rc != 0:
        return None, (err or out).strip()
    try:
        return json.loads(out), None
    except json.JSONDecodeError as e:
        return None, f"json parse error: {e}\n{out[:200]}"


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

@dataclass
class Session:
    # identity (7A)
    operator_id: str = "operator"
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    # governance
    permit_id: Optional[str] = None
    permit_expires: Optional[int] = None
    node_id: str = "?"
    branch: str = "?"
    head: str = "?"
    ahead: int = 0
    behind: int = 0
    pending: int = 0
    active_permits: int = 0
    # session counters (7B)
    proposals_created: int = 0
    proposals_approved: int = 0
    proposals_denied: int = 0


def _refresh(s: Session) -> bool:
    data, _ = _hbar_json("status")
    if not data:
        return False
    s.node_id = data.get("node", {}).get("node_id", "?")
    repo = data.get("repo", {})
    s.branch = repo.get("branch", "?")
    head = repo.get("head") or ""
    s.head = head[:8] if head else "?"
    s.ahead = repo.get("ahead", 0)
    s.behind = repo.get("behind", 0)
    counts = data.get("counts", {})
    s.pending = counts.get("pending_proposals", 0)
    s.active_permits = counts.get("active_permits", 0)
    return True


def _prompt(s: Session) -> str:
    permit_str = f"permit:{s.permit_id[:8]}…" if s.permit_id else "no permit"
    return (
        f"\nhbar [{s.operator_id} | {s.node_id} | {s.branch[:20]} | "
        f"+{s.ahead}/-{s.behind} | {permit_str} | {s.pending} pending]> "
    )


def _confirm(msg: str = "Run this plan? [y/N] ") -> bool:
    try:
        return input(msg).strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def do_look(s: Session):
    rc, out, err = _hbar("status")
    if out:
        print(out, end="")
    if s.pending > 0:
        rc, out, err = _hbar("proposals", "--status", "PENDING", "--limit", "10")
        if out:
            print(out, end="")
    if s.active_permits > 0:
        rc, out, err = _hbar("permits", "--status", "ACTIVE", "--limit", "5")
        if out:
            print(out, end="")
    _refresh(s)


def do_pending(s: Session):
    rc, out, err = _hbar("proposals", "--status", "PENDING")
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    _refresh(s)


def do_approve(s: Session, proposal_id: str):
    if not s.permit_id:
        print("error: no active permit in session — run:  permit <reason>")
        return
    rc, out, err = _hbar(
        "proposal", "decide", proposal_id,
        "--permit-id", s.permit_id,
        "--decided-by", s.operator_id,
        "--approve",
    )
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    _refresh(s)


def do_deny(s: Session, proposal_id: str, note: Optional[str]):
    if not s.permit_id:
        print("error: no active permit in session — run:  permit <reason>")
        return
    args = [
        "proposal", "decide", proposal_id,
        "--permit-id", s.permit_id,
        "--decided-by", s.operator_id,
        "--deny",
    ]
    if note:
        args += ["--note", note]
    rc, out, err = _hbar(*args)
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    _refresh(s)


def do_permit(s: Session, reason: str):
    data, err = _hbar_json(
        "permit", "request",
        "--agent-id", s.operator_id,
        "--loop-type", "governed_git",
        "--scopes", "git.preview,git.push",
        "--reason", reason,
        "--ttl", "3600",
    )
    if err:
        print(f"error: {err}")
        return
    s.permit_id = data.get("permit_id")
    s.permit_expires = data.get("expires_at_unix")
    print(f"  permit_id      {s.permit_id}")
    print(f"  expires_at     {s.permit_expires}")
    print(f"  scopes         git.preview, git.push")
    _refresh(s)


def do_history(s: Session, n: int):
    # Local session log (7B) — richer shell-side context
    log_path = _HBAR_DIR / "log.jsonl"
    if log_path.exists():
        events = []
        try:
            with log_path.open(encoding="utf-8") as f:
                for line in f:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except OSError:
            pass
        if events:
            shown = events[-n:]
            print(f"  -- local log (last {len(shown)} of {len(events)}) --")
            for ev in shown:
                ts    = ev.get("ts", "?")[:19]
                etype = ev.get("event_type", "?")
                if etype == "command":
                    detail = ev.get("cmd", "")
                elif etype in ("proposal_created", "proposal_decided"):
                    pid = (ev.get("proposal_id") or "")[:8]
                    detail = f"{pid} {ev.get('action_type', ev.get('decision', ''))}"
                elif etype == "intent_run":
                    detail = f"→{ev.get('extracted_type','?')} {ev.get('extracted_path','')}"
                elif etype == "session_start":
                    detail = ev.get("branch", "")
                elif etype == "session_end":
                    detail = ev.get("summary", "")
                else:
                    detail = ""
                print(f"  {ts}  {etype:<22}  {detail}")
            print()

    # NodeOS audit — execution record
    print("  -- NodeOS audit --")
    rc, out, err = _hbar("audit", "--limit", str(n))
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)


def do_run(s: Session, args: list):
    _hbar(*args, live=True)
    _refresh(s)


# ---------------------------------------------------------------------------
# Orientation surface — where / focus / note  (Phase 7D)
# ---------------------------------------------------------------------------

def do_where(s: Session):
    ctx = _load_context()
    print(f"  operator   {s.operator_id}")
    focus = ctx["focus"] or "(not set)"
    print(f"  focus      {focus}")
    notes = ctx["notes"]
    if notes:
        print(f"  notes")
        for i, n in enumerate(notes, 1):
            print(f"    [{i}]  {n}")
    else:
        print(f"  notes      (none)")


def do_focus(s: Session, tokens: list):
    if not tokens:
        ctx = _load_context()
        focus = ctx["focus"] or "(not set)"
        print(f"  focus: {focus}")
        print("  usage: focus set <text>  |  focus clear")
        return
    sub = tokens[0].lower()
    if sub == "clear":
        ctx = _load_context()
        ctx["focus"] = ""
        if _save_context(ctx):
            _log_event(s, "context_mutation", field="focus", value="")
            print("  focus cleared")
    elif sub == "set":
        text = " ".join(tokens[1:]).strip()
        if not text:
            print("  usage: focus set <text>")
            return
        ctx = _load_context()
        ctx["focus"] = text
        if _save_context(ctx):
            _log_event(s, "context_mutation", field="focus", value=text)
            print(f"  focus: {text}")
    else:
        print("  usage: focus set <text>  |  focus clear")


def do_note(s: Session, tokens: list):
    if not tokens:
        ctx = _load_context()
        notes = ctx["notes"]
        if notes:
            for i, n in enumerate(notes, 1):
                print(f"  [{i}]  {n}")
        else:
            print("  (no pinned notes)")
        print("  usage: note add <text>  |  note drop <N>  |  note clear")
        return
    sub = tokens[0].lower()
    if sub == "add":
        text = " ".join(tokens[1:]).strip()
        if not text:
            print("  usage: note add <text>")
            return
        ctx = _load_context()
        ctx["notes"].append(text)
        if _save_context(ctx):
            _log_event(s, "context_mutation", field="notes", action="add", value=text)
            print(f"  note [{len(ctx['notes'])}] added")
    elif sub == "drop":
        if len(tokens) < 2 or not tokens[1].isdigit():
            print("  usage: note drop <N>  (1-based index)")
            return
        idx = int(tokens[1]) - 1
        ctx = _load_context()
        if idx < 0 or idx >= len(ctx["notes"]):
            print(f"  error: no note at [{idx + 1}]  ({len(ctx['notes'])} notes total)")
            return
        removed = ctx["notes"].pop(idx)
        if _save_context(ctx):
            _log_event(s, "context_mutation", field="notes", action="drop", value=removed)
            print(f"  note [{idx + 1}] removed: {removed}")
    elif sub == "clear":
        ctx = _load_context()
        count = len(ctx["notes"])
        ctx["notes"] = []
        if _save_context(ctx):
            _log_event(s, "context_mutation", field="notes", action="clear")
            print(f"  {count} note(s) cleared")
    else:
        print("  usage: note add <text>  |  note drop <N>  |  note clear")


# ---------------------------------------------------------------------------
# intent — LLM-assisted plan formulation (Phase 6B)
# ---------------------------------------------------------------------------

_INTENT_PROMPT = """\
You are a strict JSON extraction API. Output only a single JSON object. No prose, no markdown, no code fences.

SUPPORTED TYPES:
  write_commit       Create exactly one new file and commit it only. No push.
  write_commit_push  Create exactly one new file, commit it, AND push to origin.
  push               Push existing commits to the remote repository.
  preview            Inspect or view pending changes without pushing.
  unknown            Everything else. When in doubt, use unknown.

CHOOSING write_commit vs write_commit_push:
  write_commit_push: intent includes push/deploy/publish/send/upload in addition to create/write/save
  write_commit:      intent only creates/writes/saves a file and commits — no push mentioned

USE unknown WHEN:
  - more than one file is mentioned
  - path is ambiguous, missing, unsafe, or contains ..
  - path does not start with scratch/, notes/, or generated/
  - path starts with / (absolute path — always unsafe)
  - request is to edit, append, rename, or delete (not create)
  - intent requires inspecting repo state
  - anything unclear, partial, or not covered above

OUTPUT FORMAT — exactly one, no other keys:
  write_commit:      {{"type": "write_commit",      "params": {{"path": "scratch/filename.txt", "content": "actual content", "message": "chore: short description"}}}}
  write_commit_push: {{"type": "write_commit_push", "params": {{"path": "scratch/filename.txt", "content": "actual content", "message": "chore: short description"}}}}
  push:              {{"type": "push",              "params": {{"reason": "one sentence"}}}}
  preview:           {{"type": "preview",           "params": {{}}}}
  unknown:           {{"type": "unknown",           "params": {{"reason": "one sentence"}}}}

EXTRACTION RULES for write_commit and write_commit_push params (identical schema):
  path:    exact or derived relative path; must start with scratch/, notes/, or generated/
  content: the ACTUAL text the user wants in the file — extract verbatim, no explanations, no wrappers
  message: short git commit message under 72 chars derived from path and content, e.g. "chore: add scratch/hello.txt"

EXAMPLES:

User: "create scratch/hello.txt with 'hello world' and commit it"
{{"type": "write_commit", "params": {{"path": "scratch/hello.txt", "content": "hello world", "message": "chore: add scratch/hello.txt"}}}}

User: "write notes/q2.txt saying 'Q2 goals: reliability, governance' and commit"
{{"type": "write_commit", "params": {{"path": "notes/q2.txt", "content": "Q2 goals: reliability, governance", "message": "notes: add Q2 planning notes"}}}}

User: "save generated/report.txt with 'Phase 6D complete. Tests pass.' and commit"
{{"type": "write_commit", "params": {{"path": "generated/report.txt", "content": "Phase 6D complete. Tests pass.", "message": "chore: add generated report"}}}}

User: "create scratch/proof.txt with 'all systems nominal' commit it and push to origin"
{{"type": "write_commit_push", "params": {{"path": "scratch/proof.txt", "content": "all systems nominal", "message": "chore: add scratch/proof.txt"}}}}

User: "write notes/release.txt saying 'v0.17 ready' and deploy it"
{{"type": "write_commit_push", "params": {{"path": "notes/release.txt", "content": "v0.17 ready", "message": "notes: add release note"}}}}

User: "push the branch"
{{"type": "push", "params": {{"reason": "user wants to push commits to origin"}}}}

User: "show me the diff"
{{"type": "preview", "params": {{}}}}

User: "append a line to scratch/log.txt saying done"
{{"type": "unknown", "params": {{"reason": "append/edit is not supported; only new file creation is allowed"}}}}

User: "create scratch/a.txt and scratch/b.txt both saying hello"
{{"type": "unknown", "params": {{"reason": "multi-file operations are not supported"}}}}

User: "write /etc/passwd with 'root:x:0:0' and commit"
{{"type": "unknown", "params": {{"reason": "unsafe path: absolute paths are not allowed"}}}}

User: "create ../secrets.txt with 'GITHUB_TOKEN=abc' and commit"
{{"type": "unknown", "params": {{"reason": "unsafe path: path traversal (..) is not allowed"}}}}

User: "delete scratch/temp.txt"
{{"type": "unknown", "params": {{"reason": "delete operations are not supported"}}}}

REPOSITORY STATE:
  branch: {branch}
  HEAD: {head}
  ahead/behind: +{ahead}/-{behind}
  permit: {permit_status}

{recent_context}User intent: "{intent}"

Output only the JSON object:\
"""

_INTENT_PARAMS: dict[str, set] = {
    "write_commit":      {"path", "content", "message"},
    "write_commit_push": {"path", "content", "message"},   # same params, full chain (6D-A)
    "push":              {"reason"},
    "preview":           set(),
    "unknown":           {"reason"},
}

_ALLOWED_PATH_PREFIXES = ("scratch/", "notes/", "generated/")

# ---------------------------------------------------------------------------
# Semantic validator for write_commit params (Phase 6D-B)
# ---------------------------------------------------------------------------

_GENERIC_MESSAGES = frozenset({
    "chore: describe the commit",
    "chore: add file",
    "feat: add file",
    "fix: update file",
    "add file",
    "commit",
    "update",
    "changes",
    "initial commit",
    "chore: update file",
    "chore: update",
})

# Shell metacharacters and whitespace that must not appear in a file path
_PATH_UNSAFE_RE = re.compile(r'[|&;`$><\\!*?\[\]{}()\'" \t\n\r]')

# Content prefixes that indicate the LLM returned explanatory text rather than file content
_CONTENT_WRAPPER_PREFIXES = (
    "here is",
    "here's",
    "the content",
    "the file",
    "file content",
    "```",
    "i will",
    "this file",
    "below is",
    "the following",
    "sure,",
    "certainly,",
)


def _validate_write_commit_semantics(params: dict) -> tuple[Optional[dict], Optional[str]]:
    """
    Semantic validation for write_commit params beyond schema-level checks.

    Returns (params, None) on success, (None, error_str) on failure.
    All checks are fail-closed — any ambiguous case is rejected.
    """
    path    = params["path"]
    content = params["content"]
    message = params["message"].strip()

    # ── path ──────────────────────────────────────────────────────────────
    if path.startswith("/"):
        return None, "path must be relative (no leading /)"

    path_parts = path.replace("\\", "/").split("/")
    if ".." in path_parts:
        return None, "path must not contain .."

    if _PATH_UNSAFE_RE.search(path):
        return None, f"path contains unsafe characters: {path!r}"

    # Verify the allowed prefix is still intact after earlier schema check
    if not any(path.startswith(p) for p in _ALLOWED_PATH_PREFIXES):
        allowed = ", ".join(_ALLOWED_PATH_PREFIXES)
        return None, f"path must begin with one of: {allowed}"

    # ── content ───────────────────────────────────────────────────────────
    content_stripped = content.strip()
    if not content_stripped:
        return None, "content is empty after stripping whitespace"

    lower = content_stripped.lower()
    if any(lower.startswith(p) for p in _CONTENT_WRAPPER_PREFIXES):
        return None, "content appears to be explanatory text, not file content"

    # ── message ───────────────────────────────────────────────────────────
    if message.lower() in _GENERIC_MESSAGES:
        return None, f"commit message is too generic: {message!r}"

    if len(message) > 100:
        return None, f"commit message too long: {len(message)} chars (max 100)"

    if len(message) < 5:
        return None, f"commit message too short: {len(message)} chars (min 5)"

    return params, None


def _llm_intent(text: str, s: Session,
                _context: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """POST intent to Ollama, return (raw_content, error).

    _context: override the recent_context block; pass "" to disable context injection
              (used by the test harness for deterministic runs).  Default: load from log.
    """
    permit_status = f"permit:{s.permit_id[:8]}…" if s.permit_id else "none"
    ctx = _load_intent_context() if _context is None else _context
    prompt = _INTENT_PROMPT.format(
        branch=s.branch,
        head=s.head,
        ahead=s.ahead,
        behind=s.behind,
        permit_status=permit_status,
        recent_context=ctx,
        intent=text,
    )
    payload = json.dumps({
        "model": _LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{_LLM_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read())
            err_msg = err_body.get("error", str(e))
        except Exception:
            err_msg = str(e)
        if "not found" in err_msg.lower():
            return None, f"model '{_LLM_MODEL}' not found — run: ollama pull {_LLM_MODEL}"
        return None, f"Ollama HTTP {e.code}: {err_msg}"
    except urllib.error.URLError as e:
        return None, f"LLM unreachable ({_LLM_URL}) — check HBAR_LLM_URL ({e.reason})"
    except TimeoutError:
        return None, "LLM request timed out after 30s"
    except json.JSONDecodeError as e:
        return None, f"LLM transport returned non-JSON: {e}"

    # Ollama surfaces model-not-found as {"error": "..."}
    if "error" in body:
        err = body["error"]
        if "not found" in err.lower():
            return None, f"model '{_LLM_MODEL}' not found — run: ollama pull {_LLM_MODEL}"
        return None, f"Ollama error: {err}"

    content = body.get("message", {}).get("content", "")
    return content, None


def _validate_intent(raw: str) -> tuple[Optional[dict], Optional[str]]:
    """Strictly validate LLM output. Fail closed on any unexpected structure."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        preview = raw.strip()[:120].replace("\n", " ")
        return None, f"LLM returned non-JSON: {preview}"

    if not isinstance(data, dict):
        return None, "LLM response is not a JSON object"

    top_keys = set(data.keys())
    expected_top = {"type", "params"}
    extra = top_keys - expected_top
    missing = expected_top - top_keys
    if extra:
        return None, f"unexpected top-level keys: {sorted(extra)}"
    if missing:
        return None, f"missing top-level keys: {sorted(missing)}"

    plan_type = data["type"]
    if plan_type not in _INTENT_PARAMS:
        return None, (f"unrecognized type {plan_type!r} "
                      f"(allowed: write_commit, write_commit_push, push, preview, unknown)")

    params = data["params"]
    if not isinstance(params, dict):
        return None, "params must be a JSON object"

    expected_params = _INTENT_PARAMS[plan_type]
    param_keys = set(params.keys())
    extra_p = param_keys - expected_params
    missing_p = expected_params - param_keys
    if extra_p:
        return None, f"{plan_type}.params has unexpected keys: {sorted(extra_p)}"
    if missing_p:
        return None, f"{plan_type}.params missing required keys: {sorted(missing_p)}"

    if plan_type in ("push", "unknown"):
        reason = params.get("reason", "")
        if not isinstance(reason, str) or not reason.strip():
            return None, f"{plan_type}.params.reason must be a non-empty string"

    if plan_type in ("write_commit", "write_commit_push"):
        path = params.get("path", "")
        if not isinstance(path, str) or not path.strip():
            return None, f"{plan_type}.params.path must be a non-empty string"
        if not any(path.startswith(p) for p in _ALLOWED_PATH_PREFIXES):
            allowed = ", ".join(_ALLOWED_PATH_PREFIXES)
            return None, f"{plan_type}.params.path must begin with: {allowed}"
        content = params.get("content")
        if not isinstance(content, str):
            return None, f"{plan_type}.params.content must be a string"
        message = params.get("message", "")
        if not isinstance(message, str) or not message.strip():
            return None, f"{plan_type}.params.message must be a non-empty string"

    return data, None


def do_intent(s: Session, tokens: list):
    if not tokens:
        print("usage: intent <free text describing what to do>")
        return

    text = " ".join(tokens)
    print(f"  querying {_LLM_MODEL} at {_LLM_URL} …")

    raw, err = _llm_intent(text, s)
    if err:
        print(f"  error: {err}")
        return

    data, err = _validate_intent(raw)
    if err:
        print(f"  error: invalid LLM response — {err}")
        return

    plan_type = data["type"]
    params    = data["params"]

    if plan_type == "unknown":
        print(f"  LLM: cannot map intent — {params['reason']}")
        _log_event(s, "intent_run", intent_text=text, extracted_type="unknown")
        return

    print(f"  LLM suggested plan type: {plan_type!r}")
    if plan_type in ("write_commit", "write_commit_push"):
        _, sem_err = _validate_write_commit_semantics(params)
        if sem_err:
            print(f"  error: semantic validation failed — {sem_err}")
            _log_event(s, "intent_run", intent_text=text,
                       extracted_type="write_commit", extracted_path=params.get("path"),
                       outcome="semantic_rejected", error=sem_err)
            return
        # Log successful extraction for 7C context replay
        _log_event(s, "intent_run", intent_text=text,
                   extracted_type="write_commit",
                   extracted_path=params["path"],
                   extracted_message=params["message"],
                   outcome="accepted")
        print(f"  path:    {params['path']}")
        print(f"  message: {params['message']}")
        if plan_type == "write_commit_push":
            plan_write_commit_push(s, params["path"], params["content"], params["message"])
        else:
            plan_write_commit(s, params["path"], params["content"], params["message"])
    elif plan_type == "push":
        _log_event(s, "intent_run", intent_text=text, extracted_type="push", outcome="accepted")
        print(f"  reason: {params['reason']}")
        plan_push(s)
    elif plan_type == "preview":
        _log_event(s, "intent_run", intent_text=text, extracted_type="preview", outcome="accepted")
        plan_preview(s)


# ---------------------------------------------------------------------------
# plan — structured step generator + executor
# ---------------------------------------------------------------------------

# A step is (label: str, description: str, cmd: list[str])
# cmd may contain {permit_id}, {preview_proposal_id}, {push_proposal_id},
# {commit_proposal_id} as placeholders filled in at execution time.

def _print_plan(title: str, steps: list):
    print(f"\n  Plan: {title}\n")
    for i, (label, desc, _cmd) in enumerate(steps, 1):
        print(f"    Step {i}  {label:<20}  {desc}")
    print()


def _run_plan(steps: list, s: Session) -> bool:
    """Execute steps sequentially, chaining IDs via {placeholder} substitution."""
    ids: dict = {}

    for i, (label, _desc, cmd) in enumerate(steps, 1):
        resolved = [ids.get(t.lstrip("{").rstrip("}"), t) for t in cmd]
        print(f"\n  >> Step {i}: {label}")
        data, err = _hbar_json(*resolved)
        if err:
            print(f"  !! failed: {err}")
            return False

        # Extract and chain key IDs
        if "permit_id" in data:
            ids["permit_id"] = data["permit_id"]
            s.permit_id = data["permit_id"]
            s.permit_expires = data.get("expires_at_unix")
            print(f"     permit_id:    {data['permit_id']}")

        if "proposal_id" in data:
            pid = data["proposal_id"]
            if "preview" in label:
                ids["preview_proposal_id"] = pid
            elif "push" in label:
                ids["push_proposal_id"] = pid
            elif "write" in label:
                ids["write_proposal_id"] = pid
            elif "commit" in label:
                ids["commit_proposal_id"] = pid
            print(f"     proposal_id:  {pid}")
            # infer action_type from label for log
            _atype = next((t for t in ("push", "commit", "preview", "write") if t in label), label)
            if "propose" in label:
                s.proposals_created += 1
                _log_event(s, "proposal_created", proposal_id=pid, action_type=_atype)

        status = data.get("status", "")
        if status:
            print(f"     status:       {status}")
            if status == "APPROVED":
                s.proposals_approved += 1
                _log_event(s, "proposal_decided",
                           proposal_id=ids.get(label, ""),
                           decision="APPROVED", action_type=label)
            elif status in ("DENIED", "EXECUTION_FAILED"):
                s.proposals_denied += 1
                _log_event(s, "proposal_decided",
                           proposal_id=ids.get(label, ""),
                           decision=status, action_type=label)

        result = data.get("result") or {}
        if result.get("ok") is False:
            print(f"  !! execution failed: {result}")
            return False

        # Show key result fields for preview and push
        for key in ("branch", "ahead", "behind", "will_fast_forward", "stdout", "output"):
            if key in result and result[key] not in (None, "", 0):
                print(f"     {key:<14}  {str(result[key])[:100]}")

        # Extract commit hash from git output for downstream push steps (6D-A)
        if "approve" in label and "commit" in label:
            out_text = result.get("output", "")
            m = re.search(r"^\[[^\]]+ ([0-9a-f]{7,40})\]", out_text, re.MULTILINE)
            if m:
                ids["commit_hash"] = m.group(1)
                print(f"     commit_hash:  {m.group(1)}")

        # Safety check after preview: stop if workspace is not fast-forwardable (6D-A)
        if "approve" in label and "preview" in label:
            ff = result.get("will_fast_forward")
            if ff is False:
                ahead_n  = result.get("ahead",  "?")
                behind_n = result.get("behind", "?")
                print(f"  !! preview: push not safe — "
                      f"ahead:{ahead_n} behind:{behind_n} will_fast_forward:False")
                print(f"     workspace must be fast-forwardable before pushing; stopping plan")
                return False

    _refresh(s)
    return True


def plan_push(s: Session):
    data, _ = _hbar_json("status")
    repo = data.get("repo", {}) if data else {}
    branch = repo.get("branch", "?")
    head = repo.get("head", "")
    head_short = head[:8] if head else "?"

    steps = [
        ("permit request",
         "request governed_git permit (git.preview + git.push, TTL 3600)",
         ["permit", "request",
          "--agent-id", s.operator_id,
          "--loop-type", "governed_git",
          "--scopes", "git.preview,git.push",
          "--reason", f"governed push of {branch}",
          "--ttl", "3600"]),

        ("propose preview",
         "create git_diff_preview proposal",
         ["propose", "preview", "{permit_id}"]),

        ("approve preview",
         "execute preview, record snapshot",
         ["proposal", "decide", "{preview_proposal_id}",
          "--permit-id", "{permit_id}",
          "--decided-by", s.operator_id,
          "--approve",
          "--note", "plan: preview"]),

        ("propose push",
         f"create git_push proposal for {branch} @ {head_short}",
         ["propose", "push", "{permit_id}",
          "--branch", branch,
          "--commit-hash", head,
          "--preview-snapshot", "{preview_proposal_id}"]),

        ("approve push",
         "execute git push to origin",
         ["proposal", "decide", "{push_proposal_id}",
          "--permit-id", "{permit_id}",
          "--decided-by", s.operator_id,
          "--approve",
          "--note", "plan: push"]),
    ]

    _print_plan(f"governed push of {branch} @ {head_short}", steps)
    if _confirm():
        _run_plan(steps, s)


def plan_preview(s: Session):
    if not s.permit_id:
        print("  error: no active permit — run:  permit <reason>  (needs git.preview scope)")
        return

    steps = [
        ("propose preview",
         "create git_diff_preview proposal",
         ["propose", "preview", s.permit_id]),

        ("approve preview",
         "execute preview, record snapshot",
         ["proposal", "decide", "{preview_proposal_id}",
          "--permit-id", s.permit_id,
          "--decided-by", s.operator_id,
          "--approve",
          "--note", "plan: preview"]),
    ]

    _print_plan("git diff preview", steps)
    if _confirm():
        _run_plan(steps, s)


def plan_commit(s: Session, tokens: list):
    if not s.permit_id:
        print("  error: no active permit — run:  permit <reason>  (needs git.commit scope)")
        return

    message = " ".join(tokens) if tokens else None
    if not message:
        try:
            message = input("  commit message: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
    if not message:
        print("  error: commit message required")
        return

    steps = [
        ("propose commit",
         f'create git_commit proposal: "{message}"',
         ["propose", "commit", s.permit_id, "--message", message]),

        ("approve commit",
         "execute git commit",
         ["proposal", "decide", "{commit_proposal_id}",
          "--permit-id", s.permit_id,
          "--decided-by", s.operator_id,
          "--approve",
          "--note", "plan: commit"]),
    ]

    _print_plan(f'git commit: "{message}"', steps)
    if _confirm():
        _run_plan(steps, s)


def plan_write_commit(s: Session, path: str, content: str, message: str):
    steps = [
        ("permit request",
         "request permit (fs.write + git.commit, TTL 3600)",
         ["permit", "request",
          "--agent-id", s.operator_id,
          "--loop-type", "governed_git",
          "--scopes", "fs.write,git.commit",
          "--reason", f"write {path} and commit",
          "--ttl", "3600"]),

        ("propose write",
         f"propose write_file to {path}",
         ["propose", "write", "{permit_id}",
          "--path", path,
          "--content", content]),

        ("approve write",
         f"execute write, create {path}",
         ["proposal", "decide", "{write_proposal_id}",
          "--permit-id", "{permit_id}",
          "--decided-by", s.operator_id,
          "--approve",
          "--note", "plan: write"]),

        ("propose commit",
         f'propose git_commit: "{message}"',
         ["propose", "commit", "{permit_id}",
          "--message", message]),

        ("approve commit",
         "execute git commit",
         ["proposal", "decide", "{commit_proposal_id}",
          "--permit-id", "{permit_id}",
          "--decided-by", s.operator_id,
          "--approve",
          "--note", "plan: commit"]),
    ]

    _print_plan(f'write {path} → commit: "{message}"', steps)
    if _confirm():
        _run_plan(steps, s)


def plan_write_commit_push(s: Session, path: str, content: str, message: str):
    """9-step governed plan: write → commit → preview → push (Phase 6D-A)."""
    branch = s.branch
    steps = [
        ("permit request",
         "request permit (fs.write + git.commit + git.preview + git.push, TTL 3600)",
         ["permit", "request",
          "--agent-id", s.operator_id,
          "--loop-type", "governed_git",
          "--scopes", "fs.write,git.commit,git.preview,git.push",
          "--reason", f"write {path}, commit, preview, push",
          "--ttl", "3600"]),

        ("propose write",
         f"propose write_file to {path}",
         ["propose", "write", "{permit_id}",
          "--path", path,
          "--content", content]),

        ("approve write",
         f"execute write, create {path}",
         ["proposal", "decide", "{write_proposal_id}",
          "--permit-id", "{permit_id}",
          "--decided-by", s.operator_id,
          "--approve",
          "--note", "plan: write"]),

        ("propose commit",
         f'propose git_commit: "{message}"',
         ["propose", "commit", "{permit_id}",
          "--message", message]),

        ("approve commit",
         "execute git commit — hash extracted for push step",
         ["proposal", "decide", "{commit_proposal_id}",
          "--permit-id", "{permit_id}",
          "--decided-by", s.operator_id,
          "--approve",
          "--note", "plan: commit"]),

        ("propose preview",
         "create git_diff_preview proposal — verifies fast-forward before push",
         ["propose", "preview", "{permit_id}"]),

        ("approve preview",
         "execute preview — stops plan if push is not safe",
         ["proposal", "decide", "{preview_proposal_id}",
          "--permit-id", "{permit_id}",
          "--decided-by", s.operator_id,
          "--approve",
          "--note", "plan: preview"]),

        ("propose push",
         f"create git_push proposal for {branch}",
         ["propose", "push", "{permit_id}",
          "--branch", branch,
          "--commit-hash", "{commit_hash}",
          "--preview-snapshot", "{preview_proposal_id}"]),

        ("approve push",
         "execute git push to origin",
         ["proposal", "decide", "{push_proposal_id}",
          "--permit-id", "{permit_id}",
          "--decided-by", s.operator_id,
          "--approve",
          "--note", "plan: push"]),
    ]

    _print_plan(f'write {path} → commit → preview → push [{branch}]: "{message}"', steps)
    if _confirm():
        _run_plan(steps, s)


def do_plan(s: Session, tokens: list):
    if not tokens:
        print("  usage: plan <push | preview | commit [message]>")
        return
    intent = tokens[0].lower()
    if intent == "push":
        plan_push(s)
    elif intent == "preview":
        plan_preview(s)
    elif intent == "commit":
        plan_commit(s, tokens[1:])
    else:
        print(f"  plan: unknown intent '{intent}'")
        print("  recognized: push, preview, commit [message]")


# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------

HELP = """\
Commands:
  where                   show operator identity, current focus, pinned notes
  focus set <text>        set current focus
  focus clear             clear current focus
  note add <text>         add a pinned note
  note drop <N>           remove pinned note by number
  note clear              clear all pinned notes
  look                    full governance state (status + pending + active permits)
  pending                 list PENDING proposals
  approve <id>            approve + execute a proposal  (uses session permit)
  deny <id> [--note ..]   deny a proposal               (uses session permit)
  permit <reason>         request governed_git permit (git.preview + git.push, TTL 3600)
                          stored in session for approve / deny / plan
  plan push               5-step governed push: permit → preview → approve → push → approve
  plan preview            2-step preview using session permit
  plan commit [msg]       2-step commit using session permit
  intent <text>           LLM-assisted plan from natural-language intent
                          types: write_commit, write_commit_push, push, preview, unknown
                          write_commit_push = full 9-step: write→commit→preview→push
                          LLM proposes plan; you confirm before any execution
  run <hbar args>         pass-through to hbar.py  (e.g. run status  or  run permits)
  history [N]             last N audit events (default 10)
  help                    this message
  exit / quit             end session\
"""


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------

def main():
    s = Session()
    s.operator_id = _load_identity()   # 7A
    t_start = time.time()

    ok = _refresh(s)
    if not ok:
        print("warning: could not reach NodeOS — check HBAR_NODEOS_URL")

    _log_event(s, "session_start", node_id=s.node_id, branch=s.branch)  # 7B

    ctx = _load_context()  # 7D
    print(f"\nhbar-shell v0  |  {s.operator_id}  |  {s.node_id}  |  {s.branch}  |  {s.head}")
    if ctx["focus"]:
        print(f"focus: {ctx['focus']}")
    print(f"pending: {s.pending}  active permits: {s.active_permits}")
    print('type "help" for commands\n')

    def _end_session():
        elapsed = int(time.time() - t_start)
        summary = (f"{s.proposals_created} proposals, "
                   f"{s.proposals_approved} approved, "
                   f"{s.proposals_denied} denied, "
                   f"{elapsed}s")
        _log_event(s, "session_end", summary=summary, elapsed_s=elapsed,
                   proposals_created=s.proposals_created,
                   proposals_approved=s.proposals_approved,
                   proposals_denied=s.proposals_denied)
        print(f"  session: {summary}")

    while True:
        try:
            line = input(_prompt(s)).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nexiting.")
            _end_session()
            break

        if not line:
            continue

        tokens = line.split()
        cmd = tokens[0].lower()

        _log_event(s, "command", cmd=cmd, tokens=tokens)  # 7B

        if cmd in ("exit", "quit"):
            print("exiting.")
            _end_session()
            break

        elif cmd == "help":
            print(HELP)

        elif cmd == "look":
            do_look(s)

        elif cmd == "pending":
            do_pending(s)

        elif cmd == "approve":
            if len(tokens) < 2:
                print("usage: approve <proposal_id>")
            else:
                do_approve(s, tokens[1])

        elif cmd == "deny":
            note = None
            rest = tokens[1:]
            if "--note" in rest:
                ni = rest.index("--note")
                note = " ".join(rest[ni + 1:]) if ni + 1 < len(rest) else None
                rest = rest[:ni]
            if not rest:
                print("usage: deny <proposal_id> [--note <text>]")
            else:
                do_deny(s, rest[0], note)

        elif cmd == "permit":
            reason = " ".join(tokens[1:])
            if not reason:
                print("usage: permit <reason>")
            else:
                do_permit(s, reason)

        elif cmd == "plan":
            do_plan(s, tokens[1:])

        elif cmd == "intent":
            do_intent(s, tokens[1:])

        elif cmd == "run":
            if len(tokens) < 2:
                print("usage: run <hbar args>")
            else:
                do_run(s, tokens[1:])

        elif cmd == "history":
            n = int(tokens[1]) if len(tokens) > 1 and tokens[1].isdigit() else 10
            do_history(s, n)

        elif cmd == "where":
            do_where(s)

        elif cmd == "focus":
            do_focus(s, tokens[1:])

        elif cmd == "note":
            do_note(s, tokens[1:])

        else:
            print(f"unknown command: {cmd!r}  (type help)")


if __name__ == "__main__":
    main()
