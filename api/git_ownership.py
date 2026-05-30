"""
api/git_ownership.py — keep the bind-mounted .git owned by the host user.

The api container runs as root and runs git against the bind-mounted brain repo
(BRAIN_HOST_DIR): `/admin/version-info` fetches origin on every console load,
`/admin/update` pulls. Those root-write `.git/FETCH_HEAD`, `ORIG_HEAD`, refs,
etc. — so the host SSH user (uid 1000) can no longer `git fetch`/`pull` from the
shell ("cannot open '.git/FETCH_HEAD': Permission denied") and deploys fall back
to rsync, which then diverges the checkout. (This is exactly what bit the hbar
brain 2026-05-30.)

Fix: re-own `.git` to the host owner after every root git op, plus a boot-time
migration that repairs brains already left in the broken state. Best-effort by
contract — a missed chown is an inconvenience, never a reason to fail a request
or block startup. Mirrors the brain-apps container-root-chown pattern
(api/apps.py `_chown_to_host_owner`).
"""
from __future__ import annotations

import os
from pathlib import Path


def _host_uid_gid(repo: Path):
    """Target owner for .git: explicit BRAIN_USER_UID/GID, else whoever owns the
    repo dir itself (on a normal brain that's the host operator, even when .git
    has been root-clobbered by container git ops)."""
    uid_env = os.environ.get("BRAIN_USER_UID")
    gid_env = os.environ.get("BRAIN_USER_GID")
    if uid_env and gid_env:
        return int(uid_env), int(gid_env)
    st = repo.stat()
    return st.st_uid, st.st_gid


def chown_git_to_host_owner(repo_dir: str | None = None) -> None:
    """Re-own `<repo>/.git` (recursively) to the host owner. No-op when there is
    no .git or no distinct owner to restore to."""
    repo = Path(repo_dir or os.environ.get("BRAIN_HOST_DIR", "/home/hbar/brain"))
    git_dir = repo / ".git"
    try:
        if not git_dir.exists():
            return
        uid, gid = _host_uid_gid(repo)
        # If the repo dir is itself root-owned (no host operator to restore to),
        # there is nothing meaningful to do — avoid pinning .git to root.
        if uid == 0 and not os.environ.get("BRAIN_USER_UID"):
            return
        try:
            os.chown(git_dir, uid, gid)
        except OSError:
            pass
        for root, dirs, files in os.walk(git_dir, followlinks=False):
            for name in list(dirs) + list(files):
                try:
                    os.chown(os.path.join(root, name), uid, gid, follow_symlinks=False)
                except OSError:
                    pass
    except Exception as e:  # never raise into a request or startup
        print(f"[git-ownership] chown skipped for {git_dir}: {e}", flush=True)
