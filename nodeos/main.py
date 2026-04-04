#!/usr/bin/env python3
"""
NodeOS Authority Service - Phase 1
Enforces memory and loop permit authority for BrainFoundryOS brain system
"""

from fastapi import FastAPI, HTTPException, Header, Depends

import os

# --- git_push branch policy ---
PROTECTED_BRANCHES = {"main"}
def _parse_prefix_allowlist(raw: str) -> tuple[str, ...]:
    return tuple([x.strip() for x in (raw or "").split(",") if x.strip()])

# PR-only: restrict pushes to branch prefixes (comma-separated)
ALLOWED_PUSH_PREFIXES = _parse_prefix_allowlist(os.getenv("NODEOS_PUSH_BRANCH_PREFIX_ALLOWLIST", "nodeos/,v0.17-"))

def _parse_allowlist(raw: str) -> set[str]:
    return {b.strip() for b in (raw or "").split(",") if b.strip()}

WRITE_PATH_PREFIX_ALLOWLIST = tuple(
    x.strip() for x in os.getenv(
        "NODEOS_WRITE_PATH_PREFIX_ALLOWLIST",
        "scratch/,notes/,generated/"
    ).split(",") if x.strip()
)

def _enforce_write_path_policy(rel_path: str) -> None:
    if not any(str(rel_path).startswith(prefix) for prefix in WRITE_PATH_PREFIX_ALLOWLIST):
        raise HTTPException(
            status_code=403,
            detail=f"write policy: path must start with one of {WRITE_PATH_PREFIX_ALLOWLIST}"
        )

def _enforce_push_policy(branch: str) -> None:
    # detached HEAD is handled earlier in execute_git_push; keep this for safety
    if not branch or branch == "HEAD":
        raise HTTPException(status_code=403, detail="push policy: detached HEAD is not allowed")

    if branch in PROTECTED_BRANCHES:
        raise HTTPException(status_code=403, detail=f"push policy: pushing {branch} is forbidden")

    if not any(branch.startswith(p) for p in ALLOWED_PUSH_PREFIXES):
        raise HTTPException(status_code=403, detail=f"push policy: branch {branch} must start with one of {ALLOWED_PUSH_PREFIXES}")


    raw = os.getenv("NODEOS_PUSH_BRANCH_ALLOWLIST")
    if not raw:
        raise HTTPException(status_code=403, detail="push policy: no allowlist configured")

    allowlist = _parse_allowlist(raw)
    if branch not in allowlist:
        raise HTTPException(status_code=403, detail=f"push policy: branch {branch} not in allowlist")

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import uuid
import hmac
import hashlib
import os
import yaml
import subprocess
import tempfile
import stat
from pathlib import Path


# Load brain identity
IDENTITY_PATH = Path(__file__).parent / "brain_identity.yaml"

app = FastAPI(
    title="NodeOS Authority Service",
    version="1.0.0",
    description="Phase 1: Memory and loop permit authority"
)

# CORS - internal service, but allow UI proxy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Internal service, UI proxy handles auth
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
SIGNING_SECRET = os.getenv("NODEOS_SIGNING_SECRET") or os.getenv("NODEOS_HMAC_SECRET", "dev-secret-change-in-production")
DB_PATH = os.getenv("NODEOS_DB_PATH", "/data/nodeos.db")
MEMORY_LOG_PATH = os.getenv("NODEOS_MEMORY_LOG_PATH", "/data/memory_log.jsonl")
ACTION_WORKSPACE_ROOT = os.getenv("NODEOS_WORKSPACE_ROOT", "/data/repos/hbar-brain")

# Ensure data directory exists
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


# =====================================================================# Database Schema & Initialization
# =====================================================================
def init_db():
    """Initialize SQLite database with schema"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    
    # Loop permits table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS loop_permits (
            permit_id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            loop_type TEXT NOT NULL,
            ttl_seconds INTEGER NOT NULL,
            scopes TEXT,
            reason TEXT NOT NULL,
            trace_id TEXT,
            expires_at_unix INTEGER NOT NULL,
            status TEXT DEFAULT 'ACTIVE',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            revoked_at TEXT,
            revoke_reason TEXT
        )
    """)
    
    # Memory proposals table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_proposals (
            proposal_id TEXT PRIMARY KEY,
            permit_id TEXT NOT NULL,
            memory_type TEXT NOT NULL,
            content TEXT NOT NULL,
            source_refs TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            decided_at TEXT,
            decided_by TEXT,
            decision_note TEXT
        )
    """)
    
    
    # Git preview records (for preview-before-push discipline)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS git_previews (
            preview_id TEXT PRIMARY KEY,
            proposal_id TEXT NOT NULL,
            permit_id TEXT NOT NULL,
            agent_id TEXT,
            repo TEXT NOT NULL,
            branch TEXT NOT NULL,
            local_head TEXT NOT NULL,
            remote_head TEXT,
            remote_branch_exists INTEGER NOT NULL,
            ahead INTEGER NOT NULL,
            behind INTEGER NOT NULL,
            will_fast_forward INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Audit events table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            agent_id TEXT,
            resource_id TEXT,
            action TEXT NOT NULL,
            outcome TEXT NOT NULL,
            metadata TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Action proposals table (repo edits etc.)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS action_proposals (
            proposal_id TEXT PRIMARY KEY,
            permit_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT DEFAULT 'PENDING',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            decided_at TEXT,
            decided_by TEXT,
            decision_note TEXT
        )
    """)

    conn.commit()

    conn.close()


# Initialize database on startup
@app.on_event("startup")
def startup_event():
    init_db()


def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def log_audit_event(
    conn: sqlite3.Connection,
    event_type: str,
    action: str,
    outcome: str,
    agent_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """Log an audit event"""
    import json
    event_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO audit_events (event_id, event_type, agent_id, resource_id, action, outcome, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (event_id, event_type, agent_id, resource_id, action, outcome, json.dumps(metadata) if metadata else None)
    )
    conn.commit()


def generate_permit_token(permit_id: str, agent_id: str) -> str:
    """Generate HMAC-signed permit token"""
    message = f"{permit_id}:{agent_id}"
    signature = hmac.new(
        SIGNING_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return f"{permit_id}.{signature}"


def verify_permit_token(token: str, agent_id: str) -> Optional[str]:
    """Verify permit token and return permit_id if valid"""
    try:
        permit_id, signature = token.split(".", 1)
        expected_sig = hmac.new(
            SIGNING_SECRET.encode(),
            f"{permit_id}:{agent_id}".encode(),
            hashlib.sha256
        ).hexdigest()
        
        if hmac.compare_digest(signature, expected_sig):
            return permit_id
        return None
    except:
        return None


def append_memory_log_event(event: dict) -> None:
    """
    Append-only long-term memory log (jsonl).
    This must never rewrite history; only append.
    """
    import json
    p = Path(MEMORY_LOG_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")
        f.flush()


def commit_memory_proposal_to_log(
    proposal_id: str,
    permit_id: str,
    memory_type: str,
    content: str,
    source_refs: Optional[str],
    decided_by: str,
) -> None:
    """
    Commit an APPROVED proposal to the append-only memory log.
    """
    event = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "event": "memory.commit",
        "proposal_id": proposal_id,
        "permit_id": permit_id,
        "memory_type": memory_type,
        "content": content,
        "source_refs": source_refs,
        "decided_by": decided_by,
    }
    append_memory_log_event(event)


# =====================================================================# Action policy model (v0.20)
# Central source of truth for action enablement, scopes, and risk metadata.
# Current behavior intentionally unchanged: all existing actions still require
# explicit approval; this refactor only formalizes policy.
# =====================================================================
ACTION_POLICY: dict[str, dict[str, object]] = {
    "git_diff_preview": {
        "required_scopes": {"git.preview"},
        "risk": "LOW",
        "requires_approval": True,
        "enabled": True,
    },
    "write_file": {
        "required_scopes": {"fs.write"},
        "risk": "MEDIUM",
        "requires_approval": True,
        "enabled": True,
    },
    "git_commit": {
        "required_scopes": {"git.commit"},
        "risk": "HIGH",
        "requires_approval": True,
        "enabled": True,
    },
    "git_push": {
        "required_scopes": {"git.push"},
        "risk": "HIGH",
        "requires_approval": True,
        "enabled": True,
    },
}

def get_action_policy(action_type: str) -> dict[str, object]:
    policy = ACTION_POLICY.get(action_type)
    if policy is None:
        raise HTTPException(status_code=403, detail=f"permit scope missing: unmapped action_type {action_type}")
    return policy

def require_action_enabled(action_type: str) -> dict[str, object]:
    policy = get_action_policy(action_type)
    if not bool(policy.get("enabled", False)):
        raise HTTPException(status_code=403, detail=f"action disabled by policy: {action_type}")
    return policy

def required_scopes_for_action(action_type: str) -> set[str]:
    policy = require_action_enabled(action_type)
    scopes = policy.get("required_scopes", set())
    if isinstance(scopes, set):
        return set(scopes)
    if isinstance(scopes, (list, tuple)):
        return {str(x).strip() for x in scopes if str(x).strip()}
    return set()

def _parse_scopes_field(raw: object) -> set[str]:
    """
    Parse loop_permits.scopes into a set[str].
    Supports:
      - JSON list in TEXT (preferred): '["git.preview","git.push"]'
      - legacy comma-separated: 'git.preview,git.push'
      - empty/None -> empty set (fail-closed for actions that require scopes)
    """
    if raw is None:
        return set()
    if isinstance(raw, (list, tuple, set)):
        return {str(x).strip() for x in raw if str(x).strip()}
    if not isinstance(raw, str):
        return set()
    s = raw.strip()
    if not s:
        return set()

    # Try JSON first
    if s.startswith("[") and s.endswith("]"):
        try:
            import json
            arr = json.loads(s)
            if isinstance(arr, list):
                return {str(x).strip() for x in arr if str(x).strip()}
        except Exception:
            return set()

    # Fallback: comma-separated
    return {x.strip() for x in s.split(",") if x.strip()}

def _enforce_permit_scopes_from_row(permit_row, action_type: str) -> None:
    """
    Enforce that permit_row includes required scopes for action_type.
    permit_row is a sqlite Row with a 'scopes' column.
    """
    required = required_scopes_for_action(action_type)
    have = _parse_scopes_field(permit_row["scopes"] if "scopes" in permit_row.keys() else None)
    missing = sorted(required - have)
    if missing:
        raise HTTPException(status_code=403, detail=f"permit scope missing: {missing[0]}")

def enforce_permit_scope(conn, permit_id: str, action_type: str) -> None:
    """
    Execute-time lookup of permit scopes and enforcement.
    This is belt+suspenders: we also enforce at propose-time.
    """
    cur = conn.execute(
        "SELECT permit_id, status, expires_at_unix, scopes FROM loop_permits WHERE permit_id = ?",
        (permit_id,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Permit not found")
    if row["status"] != "ACTIVE":
        raise HTTPException(status_code=403, detail="Permit is not active")
    import time
    if row["expires_at_unix"] < int(time.time()):
        raise HTTPException(status_code=403, detail="Permit has expired")
    _enforce_permit_scopes_from_row(row, action_type)

ACTION_LOG_PATH = os.getenv("NODEOS_ACTION_LOG_PATH", "/data/action_log.jsonl")


def append_action_log_event(event: dict) -> None:
    import json
    p = Path(ACTION_LOG_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")
        f.flush()


def resolve_workspace_path(rel_path: str) -> Path:
    """
    Resolve a relative path under ACTION_WORKSPACE_ROOT safely.
    - rejects absolute paths
    - rejects path traversal
    """
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise HTTPException(status_code=400, detail="Invalid path")

    if "\x00" in rel_path:
        raise HTTPException(status_code=400, detail="Invalid path")

    p = Path(rel_path)

    if p.is_absolute():
        raise HTTPException(status_code=400, detail="Path must be relative")

    root = Path(ACTION_WORKSPACE_ROOT).resolve()
    target = (root / p).resolve()

    # ensure target is inside root
    if root != target and root not in target.parents:
        raise HTTPException(status_code=400, detail="Path escapes workspace root")

    return target



def _run_git(args: list[str], cwd: str, *, allow_token: bool = False) -> subprocess.CompletedProcess:
    """
    Run git deterministically with captured output.
    If allow_token=True, uses GITHUB_TOKEN via GIT_ASKPASS without placing token in argv.
    """
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    askpass_path = None
    try:
        if allow_token:
            token = (os.getenv("GITHUB_TOKEN") or "").strip()
            if not token:
                raise HTTPException(status_code=403, detail="GITHUB_TOKEN not set")

            fd, askpass_path = tempfile.mkstemp(prefix="nodeos-askpass-", text=True)
            os.close(fd)


            Path(askpass_path).write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  *Username*) exec printf '%s' \"x-access-token\" ;;\n"
                "  *Password*) exec printf '%s' \"$GITHUB_TOKEN\" ;;\n"
                "  *) exec printf '%s' \"$GITHUB_TOKEN\" ;;\n"
                "esac\n",
                encoding="utf-8"
            )


            os.chmod(askpass_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

            env["GIT_ASKPASS"] = askpass_path
            env["GITHUB_TOKEN"] = token

        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            env=env,
        )
    finally:
        if askpass_path:
            try:
                os.remove(askpass_path)
            except Exception:
                pass


def resolve_repo_path(repo_rel: str) -> Path:
    """
    Resolve a repo path under NODEOS_WORKSPACE_ROOT safely.
    repo_rel must be relative (e.g. ".", "hbar-brain").
    """
    if not isinstance(repo_rel, str) or not repo_rel.strip():
        raise HTTPException(status_code=400, detail="Invalid repo path")
    if "\x00" in repo_rel:
        raise HTTPException(status_code=400, detail="Invalid repo path")

    root = Path(ACTION_WORKSPACE_ROOT).resolve()

    p = Path(repo_rel)
    if p.is_absolute():
        raise HTTPException(status_code=400, detail="repo must be relative")

    target = (root / p).resolve()
    if root != target and root not in target.parents:
        raise HTTPException(status_code=400, detail="repo escapes workspace root")

    if not (target / ".git").exists():
        raise HTTPException(status_code=404, detail="repo not found (missing .git)")

    return target



def execute_git_diff_preview(payload: dict) -> dict:
    """Read-only preview of what would be pushed.

    payload:
      - repo: relative repo path under ACTION_WORKSPACE_ROOT (default ".")
      - max_bytes: max bytes returned across all text fields (default 20000)
    """
    repo_rel = payload.get("repo", ".")
    max_bytes = payload.get("max_bytes", 20000)
    try:
        max_bytes = int(max_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid max_bytes")
    if max_bytes < 1000 or max_bytes > 200000:
        raise HTTPException(status_code=400, detail="max_bytes out of range (1000..200000)")

    repo = resolve_repo_path(repo_rel)

    cp_status = _run_git(["status", "--porcelain"], cwd=str(repo), allow_token=False)
    status = (cp_status.stdout or "")

    cp_stat = _run_git(["diff", "--stat"], cwd=str(repo), allow_token=False)
    diff_stat = (cp_stat.stdout or "")

    cp_diff = _run_git(["diff"], cwd=str(repo), allow_token=False)
    diff_text = (cp_diff.stdout or "")

    def _cap(txt: str, n: int) -> str:
        if not txt:
            return ""
        if len(txt) <= n:
            return txt
        return txt[:n] + "\n...TRUNCATED...\n"

    b_status = max_bytes // 5
    b_stat = max_bytes // 5
    b_diff = max_bytes - b_status - b_stat

    branch = (_run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo), allow_token=False).stdout or "").strip()

    local_head = (_run_git(["rev-parse", "HEAD"], cwd=str(repo), allow_token=False).stdout or "").strip()

    remote_head = ""
    remote_branch_exists = False
    ahead = 0
    behind = 0
    will_fast_forward = False

    if branch and branch != "HEAD":
        # Fetch the remote branch so its objects are in the local store.
        # ls-remote gives the remote SHA but rev-list then fails because the
        # object isn't local. git fetch is the correct and necessary operation.
        cp_fetch = _run_git(["fetch", "origin", branch], cwd=str(repo), allow_token=True)
        if cp_fetch.returncode == 0:
            # fetch succeeded: remote branch exists, tracking ref is now current
            remote_branch_exists = True
            cp_rhead = _run_git(["rev-parse", f"origin/{branch}"], cwd=str(repo), allow_token=False)
            if cp_rhead.returncode == 0:
                remote_head = (cp_rhead.stdout or "").strip()

            cp_cnt = _run_git(["rev-list", "--left-right", "--count", f"origin/{branch}...HEAD"], cwd=str(repo), allow_token=False)
            cnt_out = (cp_cnt.stdout or "").strip()
            if cp_cnt.returncode == 0 and cnt_out:
                parts = cnt_out.replace("\t", " ").split()
                if len(parts) >= 2:
                    behind = int(parts[0])
                    ahead = int(parts[1])
                    will_fast_forward = (behind == 0)
                else:
                    will_fast_forward = False  # malformed rev-list output — fail-closed
            else:
                will_fast_forward = False  # rev-list failed — fail-closed
        else:
            fetch_err = (cp_fetch.stderr or "").lower()
            if "couldn't find remote ref" in fetch_err or "no such ref" in fetch_err:
                # New branch not yet on origin — safe to push
                remote_branch_exists = False
                remote_head = ""
                ahead = 0
                behind = 0
                will_fast_forward = True
            else:
                # Auth failure, network error, or unknown — fail-closed
                remote_branch_exists = False
                remote_head = ""
                ahead = 0
                behind = 0
                will_fast_forward = False

    return {
        "ok": True,
        "repo": str(repo),
        "branch": branch,
        "local_head": local_head,
        "remote_branch_exists": remote_branch_exists,
        "remote_head": (remote_head or None),
        "ahead": ahead,
        "behind": behind,
        "will_fast_forward": will_fast_forward,
        "status_porcelain": _cap(status, b_status),
        "diff_stat": _cap(diff_stat, b_stat),
        "diff": _cap(diff_text, b_diff),
        "max_bytes": max_bytes,
    }

def execute_git_push(payload: dict) -> dict:
    """
    Safe git_push:
      payload: {"repo": ".", "remote": "origin"}
    Constraints:
      - remote must be origin
      - push current branch only
      - no arbitrary refspec
      - no force
      - token only via GIT_ASKPASS
    """
    repo_rel = payload.get("repo", ".")
    remote = (payload.get("remote") or "origin").strip()
    if remote != "origin":
        raise HTTPException(status_code=400, detail="Only remote 'origin' is allowed")

    repo = resolve_repo_path(repo_rel)

    # Determine current branch (must not be detached)
    cp_branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo))
    if cp_branch.returncode != 0:
        raise HTTPException(status_code=500, detail="git rev-parse failed")

    branch = (cp_branch.stdout or "").strip()
    if branch in ("", "HEAD"):
        raise HTTPException(status_code=400, detail="Detached HEAD; cannot push")


    _enforce_push_policy(branch)

    # Two-phase discipline: require a git_diff_preview on this exact HEAD
    # and bind push to the preview's view of origin/<branch> to prevent races.
    local_head = (_run_git(["rev-parse", "HEAD"], cwd=str(repo), allow_token=False).stdout or "").strip()

    # Current remote head (token-safe, non-interactive)
    current_remote_head = ""
    current_remote_exists = False
    cp_ls = _run_git(["ls-remote", "--heads", "origin", branch], cwd=str(repo), allow_token=True)
    ls_out = (cp_ls.stdout or "").strip()
    if cp_ls.returncode == 0 and ls_out:
        current_remote_head = ls_out.splitlines()[0].split()[0].strip()
        current_remote_exists = True

    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute(
            """
            SELECT remote_head, remote_branch_exists, created_at
            FROM git_previews
            WHERE branch = ? AND local_head = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (branch, local_head)
        )
        rowp = cur.fetchone()
    finally:
        try:
            con.close()
        except Exception:
            pass

    if not rowp:
        raise HTTPException(status_code=403, detail="push policy: preview required (run git_diff_preview first)")

    preview_remote_head, preview_remote_exists, _created_at = rowp
    preview_remote_head = (preview_remote_head or "").strip()
    preview_remote_exists = bool(preview_remote_exists)

    # Snapshot binding:
    # - If remote exists now, preview must have seen same remote head.
    # - If remote does not exist now, preview must have recorded remote absent.
    if current_remote_exists:
        if (not preview_remote_exists) or (preview_remote_head != current_remote_head):
            raise HTTPException(status_code=409, detail="push policy: origin changed since preview (run git_diff_preview again)")
    else:
        if preview_remote_exists:
            raise HTTPException(status_code=409, detail="push policy: origin changed since preview (run git_diff_preview again)")


    # Push HEAD to same branch on origin. No force.
    cp_push = _run_git(
        ["push", "origin", f"HEAD:refs/heads/{branch}"],
        cwd=str(repo),
        allow_token=True,
    )

    stdout = (cp_push.stdout or "").strip()
    stderr = (cp_push.stderr or "").strip()

    if cp_push.returncode == 0:
        return {
            "ok": True,
            "repo": str(repo),
            "branch": branch,
            "remote": "origin",
            "stdout": stdout,
        }

    # Deterministic error mapping (no secrets)
    msg = (stderr + "\n" + stdout).strip()

    if ("Authentication failed" in msg) or ("Permission denied" in msg) or ("could not read Username" in msg):
        raise HTTPException(status_code=403, detail="git push auth failed")

    if ("non-fast-forward" in msg) or ("rejected" in msg):
        raise HTTPException(status_code=409, detail="git push rejected (non-fast-forward or remote policy)")

    raise HTTPException(status_code=502, detail="git push failed")



def execute_write_file(payload: dict) -> dict:
    """
    Execute a write_file action:
      payload: {"path": "...", "content": "...", "mode": "create_or_overwrite"}
    """
    path = payload.get("path")
    content = payload.get("content", "")
    mode = payload.get("mode", "create_or_overwrite")

    if mode not in ("create_or_overwrite",):
        raise HTTPException(status_code=400, detail="Unsupported write mode")

    if not isinstance(content, str):
        raise HTTPException(status_code=400, detail="content must be string")

    # size guard (256KB)
    if len(content.encode("utf-8")) > 256 * 1024:
        raise HTTPException(status_code=400, detail="content too large")

    _enforce_write_path_policy(path)
    target = resolve_workspace_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        target.write_text(content, encoding="utf-8")
    except OSError as e:
        # Common in dev: /workspace mounted read-only
        if getattr(e, "errno", None) == 30:
            raise HTTPException(status_code=409, detail="workspace is read-only (mount as :rw to execute actions)")
        raise


    return {"ok": True, "written_path": str(target)}


def execute_git_commit(payload: dict) -> dict:
    """
    Execute a git commit inside ACTION_WORKSPACE_ROOT.
      payload: {"message": "...", "paths": ["file1", ...] | null}
    """
    import subprocess
    import subprocess
    import tempfile
    import stat
    from pathlib import Path



    msg = payload.get("message")
    paths = payload.get("paths")

    if not isinstance(msg, str) or not msg.strip():
        raise HTTPException(status_code=400, detail="git_commit requires non-empty message")

    if paths is not None:
        if not isinstance(paths, list) or not all(isinstance(p, str) and p.strip() for p in paths):
            raise HTTPException(status_code=400, detail="paths must be a list of non-empty strings or null")

    cwd = Path(ACTION_WORKSPACE_ROOT)

    # Ensure repo-local identity is set (do NOT use --global)
    git_name = os.getenv("NODEOS_GIT_USER_NAME", "").strip()
    git_email = os.getenv("NODEOS_GIT_USER_EMAIL", "").strip()

    if git_name and git_email:
        r_cfg1 = subprocess.run(["git", "config", "user.name", git_name], cwd=str(cwd), capture_output=True, text=True)
        r_cfg2 = subprocess.run(["git", "config", "user.email", git_email], cwd=str(cwd), capture_output=True, text=True)
        if r_cfg1.returncode != 0 or r_cfg2.returncode != 0:
            msg_cfg = ((r_cfg1.stdout or "") + (r_cfg1.stderr or "") + (r_cfg2.stdout or "") + (r_cfg2.stderr or "")).strip()
            raise HTTPException(status_code=500, detail=f"git config failed: {msg_cfg}")


    # Ensure it's a git repo
    if not (cwd / ".git").exists():
        raise HTTPException(status_code=409, detail="workspace is not a git repo")

    # Stage
    if paths is None:
        r_add = subprocess.run(["git", "add", "-A"], cwd=str(cwd), capture_output=True, text=True)
    else:
        # validate each path stays inside repo
        safe_paths = []
        for p in paths:
            safe_paths.append(str(resolve_workspace_path(p).relative_to(cwd)))
        r_add = subprocess.run(["git", "add", "--", *safe_paths], cwd=str(cwd), capture_output=True, text=True)

    if r_add.returncode != 0:
        msg_add = ((r_add.stdout or "") + (r_add.stderr or "")).strip()
        raise HTTPException(status_code=500, detail=f"git add failed: {msg_add}")

    # Commit
    r_commit = subprocess.run(["git", "commit", "-m", msg.strip()], cwd=str(cwd), capture_output=True, text=True)
    out = ((r_commit.stdout or "") + (r_commit.stderr or "")).strip()

    # No changes is not an error; return cleanly
    if r_commit.returncode != 0:
        if "nothing to commit" in out.lower() or "no changes added" in out.lower():
            return {"ok": True, "status": "no_changes", "output": out}
        raise HTTPException(status_code=500, detail=f"git commit failed: {out}")

    return {"ok": True, "status": "committed", "output": out}



# =====================================================================# Pydantic Models
# =====================================================================
class LoopPermitRequest(BaseModel):
    node_id: str
    agent_id: str
    loop_type: str = Field(..., description="inbox_sweep|research|music_assist|admin")
    ttl_seconds: int
    scopes: List[str] = Field(default_factory=list)
    reason: str
    trace_id: Optional[str] = None


class LoopPermitResponse(BaseModel):
    permit_id: str
    permit_token: str
    expires_at_unix: int


class LoopRevokeRequest(BaseModel):
    permit_id: str
    reason: Optional[str] = None


class MemoryProposal(BaseModel):
    permit_id: str
    memory_type: str = Field(..., description="fact|preference|task|note")
    content: str
    source_refs: Optional[Dict[str, Any]] = None


class MemoryDecision(BaseModel):
    decision: str = Field(..., description="APPROVE|DENY")
    decided_by: str
    note: Optional[str] = None

class ActionProposal(BaseModel):
    permit_id: str
    action_type: str  # e.g. "write_file"
    payload: Dict[str, Any]  # structured action payload


class ActionDecision(BaseModel):
    permit_id: str
    decision: str  # APPROVE or DENY
    decided_by: str
    note: Optional[str] = None

class AuditEvent(BaseModel):
    event_id: str
    event_type: str
    agent_id: Optional[str]
    resource_id: Optional[str]
    action: str
    outcome: str
    metadata: Optional[Dict[str, Any]]
    timestamp: str


# =====================================================================# API Endpoints
# =====================================================================
@app.get("/v1/identity")
def get_identity():
    """Return NodeOS identity"""
    try:
        with open(IDENTITY_PATH, "r") as f:
            data = yaml.safe_load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load identity: {str(e)}")


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "nodeos",
        "version": "1.0.0",
        "db_path": DB_PATH
    }


@app.get("/v1/audit")
def list_audit_events(
    limit: int = 100,
    conn: sqlite3.Connection = Depends(get_db)
):
    """Read-only: list recent audit events."""
    try:
        limit = int(limit)
    except Exception:
        raise HTTPException(status_code=400, detail="limit must be int")
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit out of range (1..500)")

    cur = conn.execute(
        """
        SELECT event_id, event_type, agent_id, resource_id, action, outcome, metadata, timestamp
        FROM audit_events
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (limit,)
    )
    rows = [dict(r) for r in cur.fetchall()]
    return {"ok": True, "count": len(rows), "events": rows}


@app.post("/v1/loops/request", response_model=LoopPermitResponse)
def request_loop_permit(
    request: LoopPermitRequest,
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Request a loop permit for autonomous operation.
    Returns HMAC-signed permit token.
    """
    import json
    import time
    
    permit_id = str(uuid.uuid4())
    expires_at_unix = int(time.time()) + request.ttl_seconds
    
    # Insert permit
    conn.execute(
        """
        INSERT INTO loop_permits 
        (permit_id, node_id, agent_id, loop_type, ttl_seconds, scopes, reason, trace_id, expires_at_unix, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
        """,
        (
            permit_id,
            request.node_id,
            request.agent_id,
            request.loop_type,
            request.ttl_seconds,
            json.dumps(request.scopes),
            request.reason,
            request.trace_id,
            expires_at_unix
        )
    )
    conn.commit()
    
    # Generate signed token
    permit_token = generate_permit_token(permit_id, request.agent_id)
    
    # Log audit event
    log_audit_event(
        conn,
        event_type="LOOP_PERMIT",
        action="REQUEST",
        outcome="GRANTED",
        agent_id=request.agent_id,
        resource_id=permit_id,
        metadata={
            "node_id": request.node_id,
            "loop_type": request.loop_type,
            "reason": request.reason,
            "trace_id": request.trace_id
        }
    )
    
    return LoopPermitResponse(
        permit_id=permit_id,
        permit_token=permit_token,
        expires_at_unix=expires_at_unix
    )


@app.post("/v1/loops/revoke")
def revoke_loop_permit(
    request: LoopRevokeRequest,
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Revoke a loop permit by permit_id.
    """
    # Check if permit exists and is active
    cursor = conn.execute(
        "SELECT status, agent_id FROM loop_permits WHERE permit_id = ?",
        (request.permit_id,)
    )
    row = cursor.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Permit not found")
    
    if row["status"] != "ACTIVE":
        raise HTTPException(status_code=400, detail="Permit already revoked")
    
    # Revoke permit
    conn.execute(
        """
        UPDATE loop_permits
        SET status = 'REVOKED', revoked_at = CURRENT_TIMESTAMP, revoke_reason = ?
        WHERE permit_id = ?
        """,
        (request.reason, request.permit_id)
    )
    conn.commit()
    
    # Log audit event
    log_audit_event(
        conn,
        event_type="LOOP_PERMIT",
        action="REVOKE",
        outcome="SUCCESS",
        agent_id=row["agent_id"],
        resource_id=request.permit_id,
        metadata={"reason": request.reason}
    )
    
    return {"status": "revoked", "permit_id": request.permit_id}


@app.post("/v1/memory/propose")
def propose_memory(
    proposal: MemoryProposal,
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Propose a memory for long-term storage.
    Default status: PENDING (requires NodeOS approval).
    """
    import json
    
    # Verify permit exists, is active, and not expired
    cursor = conn.execute(
        "SELECT agent_id, status, expires_at_unix, scopes FROM loop_permits WHERE permit_id = ?",
        (proposal.permit_id,)
    )
    permit_row = cursor.fetchone()
    
    if not permit_row:
        raise HTTPException(status_code=404, detail="Permit not found")
    
    if permit_row["status"] != "ACTIVE":
        raise HTTPException(status_code=403, detail="Permit is not active")
    
    import time
    if permit_row["expires_at_unix"] < int(time.time()):
        raise HTTPException(status_code=403, detail="Permit has expired")
    
    proposal_id = str(uuid.uuid4())
    
    conn.execute(
        """
        INSERT INTO memory_proposals (proposal_id, permit_id, memory_type, content, source_refs, status)
        VALUES (?, ?, ?, ?, ?, 'PENDING')
        """,
        (
            proposal_id,
            proposal.permit_id,
            proposal.memory_type,
            proposal.content,
            json.dumps(proposal.source_refs) if proposal.source_refs else None
        )
    )
    conn.commit()
    
    # Log audit event
    log_audit_event(
        conn,
        event_type="MEMORY_PROPOSAL",
        action="PROPOSE",
        outcome="PENDING",
        agent_id=permit_row["agent_id"],
        resource_id=proposal_id,
        metadata={"memory_type": proposal.memory_type, "permit_id": proposal.permit_id}
    )
    
    return {
        "proposal_id": proposal_id,
        "status": "PENDING"
    }


@app.get("/v1/actions/policy")
def get_action_policy_index():
    """
    Read-only: expose NodeOS action policy so operators/console can inspect
    enabled actions, required scopes, risk tier, and approval semantics.
    """
    actions = {}
    for action_type, policy in ACTION_POLICY.items():
        required_scopes = policy.get("required_scopes", set())
        if isinstance(required_scopes, set):
            required_scopes = sorted(required_scopes)
        elif isinstance(required_scopes, (list, tuple)):
            required_scopes = sorted(str(x).strip() for x in required_scopes if str(x).strip())
        else:
            required_scopes = []

        actions[action_type] = {
            "required_scopes": required_scopes,
            "risk": policy.get("risk"),
            "requires_approval": bool(policy.get("requires_approval", True)),
            "enabled": bool(policy.get("enabled", False)),
        }

    return {"ok": True, "actions": actions}







@app.get("/v1/operator/overview")
def operator_overview(conn: sqlite3.Connection = Depends(get_db)):
    """
    Read-only operator landing view.

    Aggregates:
    - node identity
    - repo branch/HEAD/remote tracking summary
    - proposal / permit / audit counts
    - service health / paths

    This endpoint must not mutate state.
    """
    import time

    # ----------------------------
    # Node / path basics
    # ----------------------------
    node_id = os.getenv("NODEOS_NODE_ID", "nodeos-dev")
    workspace_root = ACTION_WORKSPACE_ROOT
    db_path = DB_PATH

    # Prefer explicit repo env if present; otherwise default to the governed repo used in practice.
    repo_path = os.getenv("NODEOS_GOVERNED_REPO_PATH", "/data/repos/hbar-brain")

    repo_summary = {
        "repo_path": repo_path,
        "branch": None,
        "head": None,
        "remote_branch": None,
        "remote_head": None,
        "ahead": None,
        "behind": None,
        "allowlisted_push_branches": [],
    }

    # ----------------------------
    # Push allowlist
    # ----------------------------
    raw_allowlist = (os.getenv("NODEOS_PUSH_BRANCH_ALLOWLIST") or "").strip()
    allowlisted_push_branches = [x.strip() for x in raw_allowlist.split(",") if x.strip()]
    repo_summary["allowlisted_push_branches"] = allowlisted_push_branches

    # ----------------------------
    # Repo state (read-only)
    # ----------------------------
    try:
        repo = Path(repo_path)
        if (repo / ".git").exists():
            cp_branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo), allow_token=False)
            if cp_branch.returncode == 0:
                branch = (cp_branch.stdout or "").strip()
                if branch and branch != "HEAD":
                    repo_summary["branch"] = branch
                    repo_summary["remote_branch"] = f"origin/{branch}"

            cp_head = _run_git(["rev-parse", "HEAD"], cwd=str(repo), allow_token=False)
            if cp_head.returncode == 0:
                repo_summary["head"] = (cp_head.stdout or "").strip()

            if repo_summary["branch"]:
                branch = repo_summary["branch"]

                cp_fetch_head = _run_git(
                    ["rev-parse", f"origin/{branch}"],
                    cwd=str(repo),
                    allow_token=False,
                )
                if cp_fetch_head.returncode == 0:
                    repo_summary["remote_head"] = (cp_fetch_head.stdout or "").strip()

                cp_lr = _run_git(
                    ["rev-list", "--left-right", "--count", f"HEAD...origin/{branch}"],
                    cwd=str(repo),
                    allow_token=False,
                )
                if cp_lr.returncode == 0:
                    parts = (cp_lr.stdout or "").strip().split()
                    if len(parts) == 2:
                        ahead_s, behind_s = parts
                        repo_summary["ahead"] = int(ahead_s)
                        repo_summary["behind"] = int(behind_s)
    except Exception:
        # Fail soft for overview reads; surface nulls rather than crashing overview.
        pass

    # ----------------------------
    # Proposal counts
    # ----------------------------
    pending_proposals = conn.execute(
        "SELECT COUNT(*) FROM action_proposals WHERE status = 'PENDING'"
    ).fetchone()[0]

    approved_proposals = conn.execute(
        "SELECT COUNT(*) FROM action_proposals WHERE status = 'APPROVED'"
    ).fetchone()[0]

    failed_actions = 0
    try:
        failed_actions = conn.execute(
            """
            SELECT COUNT(*)
            FROM audit_events
            WHERE outcome IN ('FAILED', 'ERROR', 'DENIED')
            """
        ).fetchone()[0]
    except Exception:
        # Some deployments may have audit data structured differently.
        failed_actions = 0

    # ----------------------------
    # Permit counts
    # ----------------------------
    now_unix = int(time.time())

    active_permits = conn.execute(
        """
        SELECT COUNT(*)
        FROM loop_permits
        WHERE status = 'ACTIVE' AND expires_at_unix > ?
        """,
        (now_unix,),
    ).fetchone()[0]

    # ----------------------------
    # Recent approvals (audit-first if available, fallback to proposals)
    # ----------------------------
    recent_approvals = 0
    try:
        recent_approvals = conn.execute(
            """
            SELECT COUNT(*)
            FROM audit_events
            WHERE outcome = 'APPROVED'
            """
        ).fetchone()[0]
    except Exception:
        recent_approvals = approved_proposals

    return {
        "ok": True,
        "node": {
            "node_id": node_id,
            "health": "ok",
        },
        "repo": repo_summary,
        "counts": {
            "pending_proposals": pending_proposals,
            "active_permits": active_permits,
            "recent_failures": failed_actions,
            "recent_approvals": recent_approvals,
        },
        "paths": {
            "db_path": db_path,
            "workspace_root": workspace_root,
        },
    }









@app.get("/v1/operator/proposals")
def operator_proposals(
    status: Optional[List[str]] = None,
    limit: int = 50,
    offset: int = 0,
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Read-only operator proposals view.

    Returns proposal ledger rows enriched with:
    - latest preview snapshot (if any)
    - latest commit hash from action log (if any)

    This endpoint must not mutate state.
    """
    import json
    from pathlib import Path

    allowed_statuses = {"PENDING", "EXECUTING", "APPROVED", "DENIED", "EXECUTION_FAILED"}

    if status is None:
        statuses = []
    else:
        statuses = [str(s).strip().upper() for s in status if str(s).strip()]

    bad = [s for s in statuses if s not in allowed_statuses]
    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status filter (allowed: {sorted(allowed_statuses)})"
        )

    try:
        limit = int(limit)
        offset = int(offset)
    except Exception:
        raise HTTPException(status_code=400, detail="limit/offset must be integers")

    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit out of range (1..200)")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")

    where_sql = ""
    params = []

    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        where_sql = f"WHERE ap.status IN ({placeholders})"
        params.extend(statuses)

    count_row = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM action_proposals ap
        {where_sql}
        """,
        params,
    ).fetchone()
    total = count_row[0] if count_row else 0

    rows = conn.execute(
        f"""
        WITH latest_previews AS (
            SELECT
                gp.proposal_id,
                gp.preview_id,
                gp.branch,
                gp.local_head,
                gp.remote_head,
                gp.ahead,
                gp.behind,
                gp.will_fast_forward,
                gp.created_at,
                ROW_NUMBER() OVER (
                    PARTITION BY gp.proposal_id
                    ORDER BY gp.created_at DESC, gp.preview_id DESC
                ) AS rn
            FROM git_previews gp
        )
        SELECT
            ap.proposal_id,
            ap.permit_id,
            ap.action_type,
            ap.status,
            ap.created_at,
            lp.preview_id,
            lp.branch,
            lp.local_head,
            lp.remote_head,
            lp.ahead,
            lp.behind,
            lp.will_fast_forward,
            lp.created_at AS preview_created_at
        FROM action_proposals ap
        LEFT JOIN latest_previews lp
            ON lp.proposal_id = ap.proposal_id
           AND lp.rn = 1
        {where_sql}
        ORDER BY ap.created_at DESC, ap.proposal_id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()

    commit_hash_by_proposal = {}
    log_path = Path(ACTION_LOG_PATH)
    if log_path.exists():
        try:
            with log_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if obj.get("event") != "action.commit":
                        continue
                    proposal_id = obj.get("proposal_id")
                    action_type = obj.get("action_type")
                    result = obj.get("result") or {}
                    if proposal_id and isinstance(result, dict):
                        commit_hash = result.get("commit_hash")

                        if (not commit_hash) and action_type == "git_commit":
                            output = result.get("output") or ""
                            if isinstance(output, str):
                                import re
                                m = re.search(r"^\[[^\]]+ ([0-9a-f]{7,40})\]", output, re.MULTILINE)
                                if m:
                                    commit_hash = m.group(1)

                        if commit_hash:
                            commit_hash_by_proposal[proposal_id] = commit_hash
        except Exception:
            commit_hash_by_proposal = {}

    items = []
    for r in rows:
        preview_snapshot = None
        if r["preview_id"]:
            preview_snapshot = {
                "preview_id": r["preview_id"],
                "branch": r["branch"],
                "local_head": r["local_head"],
                "remote_head": r["remote_head"],
                "ahead": r["ahead"],
                "behind": r["behind"],
                "will_fast_forward": bool(r["will_fast_forward"]) if r["will_fast_forward"] is not None else None,
                "created_at": r["preview_created_at"],
            }

        items.append(
            {
                "proposal_id": r["proposal_id"],
                "action_type": r["action_type"],
                "status": r["status"],
                "created_at": r["created_at"],
                "permit_id": r["permit_id"],
                "preview_snapshot": preview_snapshot,
                "commit_hash": commit_hash_by_proposal.get(r["proposal_id"]),
            }
        )

    return {
        "ok": True,
        "count": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }





@app.get("/v1/operator/proposals/{proposal_id}")
def operator_proposal_detail(
    proposal_id: str,
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Read-only operator proposal detail view.

    Returns one proposal enriched with:
    - latest preview snapshot (if any)
    - latest commit hash from action log (if any)

    This endpoint must not mutate state.
    """
    import json
    import re
    from pathlib import Path

    row = conn.execute(
        """
        WITH latest_previews AS (
            SELECT
                gp.proposal_id,
                gp.preview_id,
                gp.branch,
                gp.local_head,
                gp.remote_head,
                gp.ahead,
                gp.behind,
                gp.will_fast_forward,
                gp.created_at,
                ROW_NUMBER() OVER (
                    PARTITION BY gp.proposal_id
                    ORDER BY gp.created_at DESC, gp.preview_id DESC
                ) AS rn
            FROM git_previews gp
        )
        SELECT
            ap.proposal_id,
            ap.permit_id,
            ap.action_type,
            ap.payload,
            ap.status,
            ap.created_at,
            ap.decided_at,
            ap.decided_by,
            ap.decision_note,
            lp.preview_id,
            lp.branch,
            lp.local_head,
            lp.remote_head,
            lp.ahead,
            lp.behind,
            lp.will_fast_forward,
            lp.created_at AS preview_created_at
        FROM action_proposals ap
        LEFT JOIN latest_previews lp
            ON lp.proposal_id = ap.proposal_id
           AND lp.rn = 1
        WHERE ap.proposal_id = ?
        """,
        (proposal_id,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Proposal not found")

    payload = row["payload"]
    try:
        payload = json.loads(payload) if isinstance(payload, str) else payload
    except Exception:
        payload = {"_raw": row["payload"]}

    commit_hash = None
    log_path = Path(ACTION_LOG_PATH)
    if log_path.exists():
        try:
            with log_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if obj.get("event") != "action.commit":
                        continue
                    if obj.get("proposal_id") != proposal_id:
                        continue

                    action_type = obj.get("action_type")
                    result = obj.get("result") or {}
                    if isinstance(result, dict):
                        commit_hash = result.get("commit_hash")

                        if (not commit_hash) and action_type == "git_commit":
                            output = result.get("output") or ""
                            if isinstance(output, str):
                                m = re.search(r"^\[[^\]]+ ([0-9a-f]{7,40})\]", output, re.MULTILINE)
                                if m:
                                    commit_hash = m.group(1)
        except Exception:
            commit_hash = None

    preview_snapshot = None
    if row["preview_id"]:
        preview_snapshot = {
            "preview_id": row["preview_id"],
            "branch": row["branch"],
            "local_head": row["local_head"],
            "remote_head": row["remote_head"],
            "ahead": row["ahead"],
            "behind": row["behind"],
            "will_fast_forward": bool(row["will_fast_forward"]) if row["will_fast_forward"] is not None else None,
            "created_at": row["preview_created_at"],
        }

    return {
        "ok": True,
        "item": {
            "proposal_id": row["proposal_id"],
            "permit_id": row["permit_id"],
            "action_type": row["action_type"],
            "payload": payload,
            "status": row["status"],
            "created_at": row["created_at"],
            "decided_at": row["decided_at"],
            "decided_by": row["decided_by"],
            "decision_note": row["decision_note"],
            "preview_snapshot": preview_snapshot,
            "commit_hash": commit_hash,
        },
    }



@app.get("/v1/operator/permits")
def operator_permits(
    status: Optional[List[str]] = None,
    limit: int = 50,
    offset: int = 0,
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Read-only operator permits view.

    Returns loop permit rows with derived lifecycle state:
    - ACTIVE
    - EXPIRED
    - REVOKED

    This endpoint must not mutate state.
    """
    import time
    import json

    allowed_statuses = {"ACTIVE", "EXPIRED", "REVOKED"}

    if status is None:
        statuses = []
    else:
        statuses = [str(s).strip().upper() for s in status if str(s).strip()]

    bad = [s for s in statuses if s not in allowed_statuses]
    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status filter (allowed: {sorted(allowed_statuses)})"
        )

    try:
        limit = int(limit)
        offset = int(offset)
    except Exception:
        raise HTTPException(status_code=400, detail="limit/offset must be integers")

    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit out of range (1..200)")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")

    now_unix = int(time.time())

    rows = conn.execute(
        """
        SELECT
            permit_id,
            node_id,
            agent_id,
            loop_type,
            ttl_seconds,
            scopes,
            reason,
            trace_id,
            expires_at_unix,
            status,
            created_at,
            revoked_at,
            revoke_reason
        FROM loop_permits
        ORDER BY created_at DESC, permit_id DESC
        """
    ).fetchall()

    items = []
    for r in rows:
        stored_status = (r["status"] or "").upper()

        if stored_status == "REVOKED":
            derived_status = "REVOKED"
        elif r["expires_at_unix"] <= now_unix:
            derived_status = "EXPIRED"
        else:
            derived_status = "ACTIVE"

        if statuses and derived_status not in statuses:
            continue

        scopes_raw = r["scopes"]
        scopes = []
        if isinstance(scopes_raw, str) and scopes_raw.strip():
            s = scopes_raw.strip()
            if s.startswith("[") and s.endswith("]"):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        scopes = [str(x).strip() for x in parsed if str(x).strip()]
                except Exception:
                    scopes = []
            else:
                scopes = [x.strip() for x in s.split(",") if x.strip()]

        items.append(
            {
                "permit_id": r["permit_id"],
                "node_id": r["node_id"],
                "agent_id": r["agent_id"],
                "loop_type": r["loop_type"],
                "ttl_seconds": r["ttl_seconds"],
                "scopes": scopes,
                "reason": r["reason"],
                "trace_id": r["trace_id"],
                "status": derived_status,
                "stored_status": stored_status,
                "expires_at_unix": r["expires_at_unix"],
                "created_at": r["created_at"],
                "revoked_at": r["revoked_at"],
                "revoke_reason": r["revoke_reason"],
            }
        )

    total = len(items)
    paged = items[offset:offset + limit]

    return {
        "ok": True,
        "count": total,
        "limit": limit,
        "offset": offset,
        "items": paged,
    }





@app.get("/v1/operator/permits/{permit_id}")
def operator_permit_detail(
    permit_id: str,
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Read-only operator permit detail view.

    Returns one permit with derived lifecycle state:
    - ACTIVE
    - EXPIRED
    - REVOKED

    This endpoint must not mutate state.
    """
    import time
    import json

    row = conn.execute(
        """
        SELECT
            permit_id,
            node_id,
            agent_id,
            loop_type,
            ttl_seconds,
            scopes,
            reason,
            trace_id,
            expires_at_unix,
            status,
            created_at,
            revoked_at,
            revoke_reason
        FROM loop_permits
        WHERE permit_id = ?
        """,
        (permit_id,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Permit not found")

    now_unix = int(time.time())
    stored_status = (row["status"] or "").upper()

    if stored_status == "REVOKED":
        derived_status = "REVOKED"
    elif row["expires_at_unix"] <= now_unix:
        derived_status = "EXPIRED"
    else:
        derived_status = "ACTIVE"

    scopes_raw = row["scopes"]
    scopes = []
    if isinstance(scopes_raw, str) and scopes_raw.strip():
        s = scopes_raw.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    scopes = [str(x).strip() for x in parsed if str(x).strip()]
            except Exception:
                scopes = []
        else:
            scopes = [x.strip() for x in s.split(",") if x.strip()]

    return {
        "ok": True,
        "item": {
            "permit_id": row["permit_id"],
            "node_id": row["node_id"],
            "agent_id": row["agent_id"],
            "loop_type": row["loop_type"],
            "ttl_seconds": row["ttl_seconds"],
            "scopes": scopes,
            "reason": row["reason"],
            "trace_id": row["trace_id"],
            "status": derived_status,
            "stored_status": stored_status,
            "expires_at_unix": row["expires_at_unix"],
            "created_at": row["created_at"],
            "revoked_at": row["revoked_at"],
            "revoke_reason": row["revoke_reason"],
        },
    }



@app.get("/v1/operator/audit")
def operator_audit(
    event_type: Optional[List[str]] = None,
    outcome: Optional[List[str]] = None,
    agent_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Read-only operator audit view.

    Supports filtering by:
    - event_type (repeatable)
    - outcome (repeatable)
    - agent_id (exact match)

    This endpoint must not mutate state.
    """
    import json

    try:
        limit = int(limit)
        offset = int(offset)
    except Exception:
        raise HTTPException(status_code=400, detail="limit/offset must be integers")

    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit out of range (1..500)")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")

    where = []
    params = []

    event_types = []
    if event_type is not None:
        event_types = [str(x).strip() for x in event_type if str(x).strip()]
        if event_types:
            placeholders = ",".join("?" for _ in event_types)
            where.append(f"event_type IN ({placeholders})")
            params.extend(event_types)

    outcomes = []
    if outcome is not None:
        outcomes = [str(x).strip().upper() for x in outcome if str(x).strip()]
        if outcomes:
            placeholders = ",".join("?" for _ in outcomes)
            where.append(f"outcome IN ({placeholders})")
            params.extend(outcomes)

    agent = None
    if agent_id is not None and str(agent_id).strip():
        agent = str(agent_id).strip()
        where.append("agent_id = ?")
        params.append(agent)

    where_sql = ""
    if where:
        where_sql = "WHERE " + " AND ".join(where)

    count_row = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM audit_events
        {where_sql}
        """,
        params,
    ).fetchone()
    total = count_row[0] if count_row else 0

    rows = conn.execute(
        f"""
        SELECT event_id, event_type, agent_id, resource_id, action, outcome, metadata, timestamp
        FROM audit_events
        {where_sql}
        ORDER BY timestamp DESC, event_id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()

    items = []
    for r in rows:
        metadata = r["metadata"]
        if isinstance(metadata, str) and metadata.strip():
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {"_raw": metadata}
        else:
            metadata = None

        items.append(
            {
                "event_id": r["event_id"],
                "event_type": r["event_type"],
                "agent_id": r["agent_id"],
                "resource_id": r["resource_id"],
                "action": r["action"],
                "outcome": r["outcome"],
                "metadata": metadata,
                "timestamp": r["timestamp"],
            }
        )

    return {
        "ok": True,
        "count": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }



@app.get("/v1/actions")
def list_action_proposals(
    status: str = "PENDING",
    limit: int = 50,
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    List action proposals (read-only operator surface).
    Defaults to PENDING. Bounded limit for determinism.
    """
    import json

    status = (status or "PENDING").strip().upper()
    allowed = {"PENDING", "EXECUTING", "APPROVED", "DENIED", "EXECUTION_FAILED"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid status (allowed: {sorted(allowed)})")

    try:
        limit = int(limit)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid limit")
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit out of range (1..200)")

    cur = conn.execute(
        """
        SELECT proposal_id, permit_id, action_type, payload, status, created_at, decided_at, decided_by, decision_note
        FROM action_proposals
        WHERE status = ?
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (status, limit),
    )
    rows = cur.fetchall()

    out = []
    for r in rows:
        payload = r["payload"]
        try:
            payload = json.loads(payload) if isinstance(payload, str) else payload
        except Exception:
            payload = {"_error": "invalid_json_payload"}

        out.append(
            {
                "proposal_id": r["proposal_id"],
                "permit_id": r["permit_id"],
                "action_type": r["action_type"],
                "payload": payload,
                "status": r["status"],
                "created_at": r["created_at"],
                "decided_at": r["decided_at"],
                "decided_by": r["decided_by"],
                "decision_note": r["decision_note"],
            }
        )

    return {"ok": True, "status": status, "count": len(out), "proposals": out}


@app.get("/v1/actions/{proposal_id}")
def get_action_proposal(
    proposal_id: str,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Get a single action proposal (read-only operator surface)."""
    import json

    cur = conn.execute(
        """
        SELECT proposal_id, permit_id, action_type, payload, status, created_at, decided_at, decided_by, decision_note
        FROM action_proposals
        WHERE proposal_id = ?
        """,
        (proposal_id,),
    )
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Action proposal not found")

    payload = r["payload"]
    try:
        payload = json.loads(payload) if isinstance(payload, str) else payload
    except Exception:
        payload = {"_error": "invalid_json_payload"}

    return {
        "ok": True,
        "proposal": {
            "proposal_id": r["proposal_id"],
            "permit_id": r["permit_id"],
            "action_type": r["action_type"],
            "payload": payload,
            "status": r["status"],
            "created_at": r["created_at"],
            "decided_at": r["decided_at"],
            "decided_by": r["decided_by"],
            "decision_note": r["decision_note"],
        },
    }



@app.get("/v1/actions/{proposal_id}/commit")
def get_action_commit(
    proposal_id: str,
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Read-only: return the latest action.commit event for a proposal_id
    from /data/action_log.jsonl (the execution result).
    """
    import json
    from pathlib import Path

    log_path = Path("/data/action_log.jsonl")
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="action log not found")

    last = None
    try:
        with log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("event") == "action.commit" and obj.get("proposal_id") == proposal_id:
                    last = obj
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to read action log: {e}")

    if not last:
        raise HTTPException(status_code=404, detail="commit event not found for proposal_id")

    return {"ok": True, "commit": last}



@app.post("/v1/actions/propose")
def propose_action(
    proposal: ActionProposal,
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Propose an action for execution (e.g., repo file write).
    Default status: PENDING (requires NodeOS approval).
    """
    import json
    # Validate permit exists + active + not expired (reuse same pattern as memory)
    cursor = conn.execute(
        "SELECT agent_id, status, expires_at_unix, scopes FROM loop_permits WHERE permit_id = ?",
        (proposal.permit_id,)
    )
    permit_row = cursor.fetchone()

    if not permit_row:
        raise HTTPException(status_code=404, detail="Permit not found")
    if permit_row["status"] != "ACTIVE":
        raise HTTPException(status_code=403, detail="Permit is not active")

    import time
    if permit_row["expires_at_unix"] < int(time.time()):
        raise HTTPException(status_code=403, detail="Permit has expired")

    proposal_id = str(uuid.uuid4())

    # v0.20 action policy: fail-closed if action disabled/unmapped
    require_action_enabled(proposal.action_type)

    # Action-specific propose-time validation
    if proposal.action_type == "write_file":
        path = proposal.payload.get("path")
        _enforce_write_path_policy(path)
        resolve_workspace_path(path)

    # Scoped permits: enforce at propose-time (fail-closed)
    _enforce_permit_scopes_from_row(permit_row, proposal.action_type)

    conn.execute(
        """
        INSERT INTO action_proposals (proposal_id, permit_id, action_type, payload, status)
        VALUES (?, ?, ?, ?, 'PENDING')
        """,
        (
            proposal_id,
            proposal.permit_id,
            proposal.action_type,
            json.dumps(proposal.payload, sort_keys=True),
        )
    )
    conn.commit()

    log_audit_event(
        conn,
        event_type="ACTION_PROPOSAL",
        action="PROPOSE",
        outcome="PENDING",
        agent_id=permit_row["agent_id"],
        resource_id=proposal_id,
        metadata={"action_type": proposal.action_type, "permit_id": proposal.permit_id},
    )

    return {"proposal_id": proposal_id, "status": "PENDING"}




@app.post("/v1/actions/{proposal_id}/decide")
def decide_action_proposal(
    proposal_id: str,
    decision: ActionDecision,
    conn: sqlite3.Connection = Depends(get_db)
):
    import json

    cursor = conn.execute(
        "SELECT permit_id, status, action_type, payload FROM action_proposals WHERE proposal_id = ?",
        (proposal_id,)
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if row["status"] != "PENDING":
        raise HTTPException(status_code=400, detail="Proposal already decided")

    if decision.decision not in ["APPROVE", "DENY"]:
        raise HTTPException(status_code=400, detail="Decision must be APPROVE or DENY")

    # ----------------------------
    # DENY PATH
    # ----------------------------
    if decision.decision == "DENY":
        conn.execute(
            """UPDATE action_proposals
               SET status = 'DENIED',
                   decided_at = CURRENT_TIMESTAMP,
                   decided_by = ?,
                   decision_note = ?
               WHERE proposal_id = ?""",
            (decision.decided_by, decision.note, proposal_id),
        )
        conn.commit()

        return {
            "proposal_id": proposal_id,
            "status": "DENIED"
        }

    # ----------------------------
    # APPROVE PATH (EXECUTE FIRST)
    # ----------------------------

    # Transition to EXECUTING
    conn.execute(
        """UPDATE action_proposals
           SET status = 'EXECUTING',
               decided_at = CURRENT_TIMESTAMP,
               decided_by = ?,
               decision_note = ?
           WHERE proposal_id = ?""",
        (decision.decided_by, decision.note, proposal_id),
    )
    conn.commit()

    try:
        try:
            payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid action payload JSON")

        # v0.20 action policy: fail-closed if action disabled/unmapped
        require_action_enabled(row["action_type"])

        # Scoped permits: enforce at execute-time (belt+suspenders)
        enforce_permit_scope(conn, decision.permit_id, row["action_type"])

        # Execute allowed actions only


        # Execute allowed actions only
        if row["action_type"] == "write_file":
            result = execute_write_file(payload)
        elif row["action_type"] == "git_push":
            result = execute_git_push(payload)
        elif row["action_type"] == "git_diff_preview":
            result = execute_git_diff_preview(payload)
        elif row["action_type"] == "git_commit":
            result = execute_git_commit(payload)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action_type: {row['action_type']}")

        # Record preview for preview-before-push discipline
        if row["action_type"] == "git_diff_preview":
            try:
                cur2 = conn.execute(
                    "SELECT agent_id FROM loop_permits WHERE permit_id = ?",
                    (row["permit_id"],)
                )
                pr = cur2.fetchone()
                agent_id = pr["agent_id"] if pr else None

                conn.execute(
                    """
                    INSERT INTO git_previews (
                        preview_id, proposal_id, permit_id, agent_id,
                        repo, branch, local_head, remote_head, remote_branch_exists,
                        ahead, behind, will_fast_forward
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        proposal_id,
                        row["permit_id"],
                        agent_id,
                        result.get("repo") or "",
                        result.get("branch") or "",
                        result.get("local_head") or "",
                        result.get("remote_head"),
                        1 if result.get("remote_branch_exists") else 0,
                        int(result.get("ahead") or 0),
                        int(result.get("behind") or 0),
                        1 if result.get("will_fast_forward") else 0,
                    )
                )
                conn.commit()
            except Exception:
                # Do not fail the preview action if recording fails; keep preview read-only UX stable.
                pass


        # SUCCESS → mark APPROVED
        conn.execute(
            "UPDATE action_proposals SET status = 'APPROVED' WHERE proposal_id = ?",
            (proposal_id,),
        )
        conn.commit()

        append_action_log_event({
            "schema_version": 1,
            "ts": datetime.utcnow().isoformat() + "Z",
            "event": "action.commit",
            "proposal_id": proposal_id,
            "permit_id": row["permit_id"],
            "action_type": row["action_type"],
            "result": result,
            "decided_by": decision.decided_by,
        })

        return {
            "proposal_id": proposal_id,
            "status": "APPROVED",
            "result": result
        }

    except HTTPException as e:
        # Execution failed deterministically
        conn.execute(
            "UPDATE action_proposals SET status = 'EXECUTION_FAILED' WHERE proposal_id = ?",
            (proposal_id,),
        )
        conn.commit()
        raise e

    except Exception:
        conn.execute(
            "UPDATE action_proposals SET status = 'EXECUTION_FAILED' WHERE proposal_id = ?",
            (proposal_id,),
        )
        conn.commit()
        raise HTTPException(status_code=500, detail="Action execution failed")






@app.post("/v1/memory/{proposal_id}/decide")
def decide_memory_proposal(
    proposal_id: str,
    decision: MemoryDecision,
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Decide on a memory proposal (APPROVE or DENY).
    Only NodeOS authority can call this (auth TBD in phase 2).
    """
    # Check if proposal exists
    cursor = conn.execute(
        "SELECT permit_id, status, memory_type, content, source_refs FROM memory_proposals WHERE proposal_id = ?",
        (proposal_id,)
    )
    row = cursor.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Proposal not found")
    
    if row["status"] != "PENDING":
        raise HTTPException(status_code=400, detail="Proposal already decided")
    
    # Validate decision
    if decision.decision not in ["APPROVE", "DENY"]:
        raise HTTPException(status_code=400, detail="Decision must be APPROVE or DENY")
    
    # Map to status
    status = "APPROVED" if decision.decision == "APPROVE" else "DENIED"
    
    # Update proposal
    conn.execute(
        """
        UPDATE memory_proposals
        SET status = ?, decided_at = CURRENT_TIMESTAMP, decided_by = ?, decision_note = ?
        WHERE proposal_id = ?
        """,
        (status, decision.decided_by, decision.note, proposal_id)
    )
    conn.commit()

    if status == "APPROVED":
        commit_memory_proposal_to_log(
            proposal_id=proposal_id,
            permit_id=row["permit_id"],
            memory_type=row["memory_type"],
            content=row["content"],
            source_refs=row["source_refs"],
            decided_by=decision.decided_by,
        )

    
    # Get agent_id from permit
    cursor = conn.execute(
        "SELECT agent_id FROM loop_permits WHERE permit_id = ?",
        (row["permit_id"],)
    )
    permit_row = cursor.fetchone()
    agent_id = permit_row["agent_id"] if permit_row else None
    
    # Log audit event
    log_audit_event(
        conn,
        event_type="MEMORY_PROPOSAL",
        action="DECIDE",
        outcome=status,
        agent_id=agent_id,
        resource_id=proposal_id,
        metadata={"decided_by": decision.decided_by, "note": decision.note}
    )
    
    return {
        "proposal_id": proposal_id,
        "status": status
    }


@app.get("/v1/audit/events", response_model=List[AuditEvent])
def get_audit_events(
    since_unix: Optional[int] = None,
    limit: int = 100,
    event_type: Optional[str] = None,
    agent_id: Optional[str] = None,
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Retrieve audit events.
    Supports filtering by since_unix, event_type and agent_id.
    """
    import json
    
    query = "SELECT * FROM audit_events WHERE 1=1"
    params = []
    
    if since_unix:
        query += " AND strftime('%s', timestamp) >= ?"
        params.append(str(since_unix))
    
    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)
    
    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
    
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    
    events = []
    for row in rows:
        events.append(AuditEvent(
            event_id=row["event_id"],
            event_type=row["event_type"],
            agent_id=row["agent_id"],
            resource_id=row["resource_id"],
            action=row["action"],
            outcome=row["outcome"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
            timestamp=row["timestamp"]
        ))
    
    return events


@app.get("/v1/loops/status/{permit_id}")
def get_permit_status(
    permit_id: str,
    conn: sqlite3.Connection = Depends(get_db)
):
    """Get the status of a loop permit"""
    cursor = conn.execute(
        "SELECT * FROM loop_permits WHERE permit_id = ?",
        (permit_id,)
    )
    row = cursor.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Permit not found")
    
    return {
        "permit_id": row["permit_id"],
        "node_id": row["node_id"],
        "agent_id": row["agent_id"],
        "loop_type": row["loop_type"],
        "reason": row["reason"],
        "status": row["status"],
        "ttl_seconds": row["ttl_seconds"],
        "expires_at_unix": row["expires_at_unix"],
        "created_at": row["created_at"],
        "revoked_at": row["revoked_at"],
        "revoke_reason": row["revoke_reason"]
    }


@app.get("/v1/memory/proposals/{proposal_id}")
def get_memory_proposal(
    proposal_id: str,
    conn: sqlite3.Connection = Depends(get_db)
):
    """Get a single memory proposal by ID"""
    import json
    
    cursor = conn.execute(
        """
        SELECT mp.proposal_id, mp.permit_id, mp.memory_type, mp.content,
               mp.source_refs, mp.status, mp.created_at, mp.decided_at,
               mp.decided_by, mp.decision_note,
               lp.agent_id
        FROM memory_proposals mp
        LEFT JOIN loop_permits lp ON mp.permit_id = lp.permit_id
        WHERE mp.proposal_id = ?
        """,
        (proposal_id,)
    )
    row = cursor.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Proposal not found")
    
    return {
        "proposal_id": row["proposal_id"],
        "permit_id": row["permit_id"],
        "agent_id": row["agent_id"],
        "memory_type": row["memory_type"],
        "content": row["content"],
        "source_refs": json.loads(row["source_refs"]) if row["source_refs"] else None,
        "status": row["status"],
        "created_at": row["created_at"],
        "decided_at": row["decided_at"],
        "decided_by": row["decided_by"],
        "decision_note": row["decision_note"]
    }


@app.get("/v1/memory/proposals")
def list_memory_proposals(
    status: Optional[str] = None,
    agent_id: Optional[str] = None,
    limit: int = 100,
    conn: sqlite3.Connection = Depends(get_db)
):
    """List memory proposals with optional filtering"""
    import json
    
    query = """
        SELECT mp.proposal_id, mp.permit_id, mp.memory_type, mp.content,
               mp.source_refs, mp.status, mp.created_at, mp.decided_at,
               mp.decided_by, mp.decision_note,
               lp.agent_id
        FROM memory_proposals mp
        LEFT JOIN loop_permits lp ON mp.permit_id = lp.permit_id
        WHERE 1=1
    """
    params = []
    
    if status:
        query += " AND mp.status = ?"
        params.append(status)
    
    if agent_id:
        query += " AND lp.agent_id = ?"
        params.append(agent_id)
    
    query += " ORDER BY mp.created_at DESC LIMIT ?"
    params.append(limit)
    
    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    
    proposals = []
    for row in rows:
        proposals.append({
            "proposal_id": row["proposal_id"],
            "permit_id": row["permit_id"],
            "agent_id": row["agent_id"],
            "memory_type": row["memory_type"],
            "content": row["content"],
            "source_refs": json.loads(row["source_refs"]) if row["source_refs"] else None,
            "status": row["status"],
            "created_at": row["created_at"],
            "decided_at": row["decided_at"],
            "decided_by": row["decided_by"],
            "decision_note": row["decision_note"]
        })
    
    return {"proposals": proposals, "count": len(proposals)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
