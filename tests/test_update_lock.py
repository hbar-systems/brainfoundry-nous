"""
One update or revert at a time per checkout (scripts/update_lock.sh, 2026-11-01).

Real processes against a scratch checkout: a holder takes the lock and waits; a
second run must exit 75 before doing anything. Covers: kill releases the lock,
another checkout is not blocked, a read-only lock file still locks, an
unopenable lock never blocks the update, the real update_brain.sh and
revert_brain.sh stop before git, and the console and bridge report "busy".
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# api.main is imported by two tests; it needs these before import (as tests/test_ask.py).
os.environ.setdefault("BRAIN_IDENTITY_SECRET", "test-only-secret")
os.environ.setdefault("BRAIN_RUNTIME_DIR", tempfile.mkdtemp(prefix="update-lock-rt-"))
LOCK_SH = ROOT / "scripts" / "update_lock.sh"

pytestmark = pytest.mark.skipif(shutil.which("flock") is None, reason="flock not installed")


def _driver(brain_dir: Path, marker: Path, hold_s: float = 0) -> list:
    # Source the helper, take the lock, then leave a mark (proof the run went on).
    script = (f'set -e; BRAIN_DIR="{brain_dir}"; . "{LOCK_SH}"; take_update_lock update; '
              f'echo ran >> "{marker}"; echo held; sleep {hold_s}')
    return ["bash", "-c", script]


class _Holder:
    """The holder runs in its own process group; kill() takes the whole group, so a
    child that inherited fd 9 cannot keep the lock alive behind the test's back."""
    def __init__(self, p):
        self.p = p

    def kill(self, sig=signal.SIGKILL):
        try:
            os.killpg(self.p.pid, sig)
        except ProcessLookupError:
            pass

    def wait(self):
        return self.p.wait(timeout=10)


def _holder(brain_dir: Path, marker: Path):
    p = subprocess.Popen(_driver(brain_dir, marker, hold_s=30), stdout=subprocess.PIPE, text=True,
                         start_new_session=True)
    assert p.stdout.readline().strip() == "held"
    return _Holder(p)


def _second(brain_dir: Path, marker: Path, env=None):
    return subprocess.run(_driver(brain_dir, marker), capture_output=True, text=True, timeout=20, env=env)


@pytest.fixture
def checkout(tmp_path):
    d = tmp_path / "brain"
    d.mkdir()
    return d


def test_second_run_stops_with_75_and_changes_nothing(checkout, tmp_path):
    marker = tmp_path / "marker"
    h = _holder(checkout, marker)
    try:
        r = _second(checkout, marker)
        assert r.returncode == 75
        assert "already running" in r.stdout
        assert marker.read_text().splitlines() == ["ran"]   # only the holder ran
    finally:
        h.kill(); h.wait()


def test_killed_holder_leaves_no_lock(checkout, tmp_path):
    marker = tmp_path / "marker"
    h = _holder(checkout, marker)
    h.kill(); h.wait()
    r = _second(checkout, marker)
    assert r.returncode == 0 and marker.read_text().splitlines() == ["ran", "ran"]


def test_lock_released_after_normal_exit(checkout, tmp_path):
    marker = tmp_path / "marker"
    assert _second(checkout, marker).returncode == 0
    assert _second(checkout, marker).returncode == 0


def test_other_checkout_not_blocked(checkout, tmp_path):
    other = tmp_path / "member2"
    other.mkdir()
    h = _holder(checkout, tmp_path / "m1")
    try:
        assert _second(other, tmp_path / "m2").returncode == 0
    finally:
        h.kill(); h.wait()


def test_read_only_lock_file_still_locks(checkout, tmp_path):
    # Root may create the file from the container; the host user opens it read-only.
    lock = checkout / ".update.lock"
    lock.write_text("")
    lock.chmod(0o444)
    marker = tmp_path / "marker"
    h = _holder(checkout, marker)
    try:
        assert _second(checkout, marker).returncode == 75
    finally:
        h.kill(); h.wait()


def test_unopenable_lock_never_blocks(tmp_path):
    missing = tmp_path / "no" / "such" / "dir"
    marker = tmp_path / "marker"
    r = _second(missing, marker)
    assert r.returncode == 0 and "without the one-at-a-time guard" in r.stdout
    assert marker.read_text() == "ran\n"


def test_no_flock_runs_with_warning(checkout, tmp_path):
    marker = tmp_path / "marker"
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("sleep",):
        os.symlink(shutil.which(tool), bindir / tool)
    r = subprocess.run(["/bin/bash", "-c", _driver(checkout, marker)[2]], capture_output=True,
                       text=True, timeout=20, env={"PATH": str(bindir)})
    assert r.returncode == 0 and "no flock" in r.stdout


@pytest.mark.parametrize("script", ["update_brain.sh", "revert_brain.sh"])
def test_real_scripts_stop_before_git(script, checkout, tmp_path):
    # The scratch checkout is not a git repo: an unguarded run fails at git (rc 1);
    # a guarded run must stop at the lock (rc 75) first, touching nothing.
    env = {**os.environ, "HOME": str(tmp_path), "BRAIN_DIR": str(checkout)}
    h = _holder(checkout, tmp_path / "marker")
    try:
        r = subprocess.run(["bash", str(ROOT / "scripts" / script), str(checkout)],
                           capture_output=True, text=True, timeout=30, env=env)
        assert r.returncode == 75, r.stdout + r.stderr
        assert "git" not in r.stdout.split("already running")[0].lower()
        assert not (tmp_path / ".gitconfig").exists()    # stopped before the safe.directory line
    finally:
        h.kill(); h.wait()
    if script == "update_brain.sh":
        r = subprocess.run(["bash", str(ROOT / "scripts" / script), str(checkout)],
                           capture_output=True, text=True, timeout=30, env=env)
        assert r.returncode == 1 and "git cannot operate" in r.stdout   # free lock: goes on to git


def test_lock_file_created_world_readable_under_member_umask(checkout, tmp_path):
    script = f'umask 027; BRAIN_DIR="{checkout}"; . "{LOCK_SH}"; take_update_lock update'
    assert subprocess.run(["bash", "-c", script], timeout=20).returncode == 0
    assert (checkout / ".update.lock").stat().st_mode & 0o777 == 0o644


def test_auto_update_record():
    from api import main as m
    assert m._auto_update_record(0, "2026-10-31T04:00:00Z") == {"last_result": "rc=0"}
    assert m._auto_update_record(1, None) == {"last_result": "rc=1"}
    busy = m._auto_update_record(75, "2026-10-31T04:00:00Z")
    assert busy == {"last_run": "2026-10-31T04:00:00Z", "last_result": "skipped: another update was running"}
    # first ever run skipped: last_run cleared, so the rule sees "not run today" and retries
    assert m._auto_update_record(75, None)["last_run"] == ""
    from api.settings_store import auto_update_due
    from datetime import datetime
    cfg = {"enabled": True, "hour": 4, "last_run": ""}
    assert auto_update_due(cfg, datetime(2026, 11, 1, 5, 0), 2) is True


def test_lock_file_is_ignored_by_git():
    out = subprocess.run(["git", "check-ignore", ".update.lock"], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0


# ── console and bridge report busy ─────────────────────────────────────────

def test_admin_update_frame_says_busy(monkeypatch, tmp_path):
    import asyncio
    from api import main as m
    (tmp_path / "scripts").mkdir()
    for name in ("update_brain.sh", "revert_brain.sh"):
        (tmp_path / "scripts" / name).write_text("echo 'another update or revert is already running'; exit 75\n")
    monkeypatch.setattr(m, "BRAIN_HOST_DIR", str(tmp_path))
    monkeypatch.setattr(m, "_update_preflight", lambda: None)

    async def collect(resp):
        return [c async for c in resp.body_iterator]

    for endpoint in (m.admin_update, m.admin_revert):
        chunks = asyncio.run(collect(endpoint(api_key="k")))
        done = [json.loads(c[6:]) for c in chunks if c.startswith("data: {") and '"done"' in c]
        assert done == [{"type": "done", "returncode": 75, "busy": True}]


def test_bridge_frame_says_busy(monkeypatch, tmp_path):
    from tests.test_member_update import _bridge
    m = _bridge(monkeypatch, tmp_path, CC_MEMBER="ada", CC_MEMBER_N="2")
    log = tmp_path / "update.log"
    log.write_text("another update or revert is already running\nbrain-update rc=75\n")
    frames = list(m._update_frames(log, 0, running=lambda: True, sleep=lambda s: None))
    done = json.loads(frames[-2][6:])
    assert done == {"type": "done", "returncode": 75, "busy": True}
