"""
Tests for api/git_ownership — the .git re-own helper.

The actual cross-user chown needs root, so these cover the logic that runs
without privilege: owner resolution, the no-.git no-op, the root-owned-repo
guard, and that a normal call never raises (chowning to our own uid is allowed).
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api import git_ownership  # noqa: E402


def test_no_git_dir_is_noop(tmp_path):
    # No .git under the repo → returns cleanly, no exception.
    git_ownership.chown_git_to_host_owner(str(tmp_path))


def test_host_uid_gid_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_USER_UID", "1000")
    monkeypatch.setenv("BRAIN_USER_GID", "1000")
    assert git_ownership._host_uid_gid(tmp_path) == (1000, 1000)


def test_host_uid_gid_from_repo_owner(tmp_path, monkeypatch):
    monkeypatch.delenv("BRAIN_USER_UID", raising=False)
    monkeypatch.delenv("BRAIN_USER_GID", raising=False)
    st = tmp_path.stat()
    assert git_ownership._host_uid_gid(tmp_path) == (st.st_uid, st.st_gid)


def test_chown_walks_without_error(tmp_path, monkeypatch):
    # Build a .git tree; target our own uid/gid so the chown is permitted
    # without root and the walk path is exercised end to end.
    git_dir = tmp_path / ".git"
    (git_dir / "refs").mkdir(parents=True)
    (git_dir / "FETCH_HEAD").write_text("x")
    (git_dir / "refs" / "main").write_text("y")
    monkeypatch.setenv("BRAIN_USER_UID", str(os.getuid()))
    monkeypatch.setenv("BRAIN_USER_GID", str(os.getgid()))
    git_ownership.chown_git_to_host_owner(str(tmp_path))  # must not raise


def test_root_owned_repo_guard(tmp_path, monkeypatch):
    # If the repo dir resolves to root-owned and no explicit UID is set, the
    # helper must NOT pin .git to root — it should bail. We simulate by forcing
    # _host_uid_gid to report root, with no BRAIN_USER_UID override.
    (tmp_path / ".git").mkdir()
    monkeypatch.delenv("BRAIN_USER_UID", raising=False)
    monkeypatch.setattr(git_ownership, "_host_uid_gid", lambda repo: (0, 0))
    # Should return without attempting chown (no exception, no-op).
    git_ownership.chown_git_to_host_owner(str(tmp_path))
