"""The member's Update door on a shared box (2026-10-21, docs/MULTI_INSTANCE.md "Update from the
console"): scripts/brain-member-update.sh (the root helper), scripts/member-update-door.sh (its
sudoers line), the bridge's /update routes and the add-member wiring. Every host effect is stubbed:
the helper runs as this user with its constants pointed into a temporary directory, and id, runuser,
systemd-run, systemctl and chgrp are fakes that log what they were asked."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "brain-member-update.sh"


def _clean_env(**extra) -> dict:
    e = {k: v for k, v in os.environ.items() if not k.startswith(("CC_", "SUDO_", "INVOCATION_"))}
    e.update(extra)
    return e


def _box(tmp_path, *, member="ada", registry=None, running=False):
    """A fake box: /srv/brains/<m> as a git checkout owned by this user, the helper copied with its
    constants pointed here, and fake root commands on its PATH."""
    brains = tmp_path / "srv"
    d = brains / member
    (d / "scripts").mkdir(parents=True)
    (d / "brain-apps").mkdir()
    (d / "scripts" / "update_brain.sh").write_text('#!/bin/bash\necho "fake update of $1"\n')
    (d / "scripts" / "backup_brain.sh").write_text("#!/bin/bash\n")
    (d / "docker-compose.yml").write_text("services: {}\n")
    (d / ".env").write_text("COMPOSE_PROJECT_NAME=brain-ada\n")
    (d / ".gitignore").write_text(".env\n")
    for f in ("update_brain.sh", "backup_brain.sh"):
        os.chmod(d / "scripts" / f, 0o755)
    os.chmod(d / "docker-compose.yml", 0o644)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(d), *c], check=True)
    os.chmod(d / ".env", 0o600)
    for p in [brains, d, d / ".git", d / ".git" / "hooks", d / "scripts"]:
        os.chmod(p, 0o755)
    os.chmod(d / ".git" / "config", 0o644)
    (brains / "members.tsv").write_text(registry if registry is not None else f"{member}\t1\t8110\t2026-10-21\n")
    fake = tmp_path / "fake"
    fake.mkdir()
    log = tmp_path / "log"
    stubs = {
        "id": 'if [ "$1" = -u ] && [ $# -eq 1 ]; then echo 0; else /usr/bin/id "$@"; fi',
        "runuser": 'echo "runuser $*" >> "$STUBLOG"; shift 3; exec "$@"',          # runuser -u <admin> -- cmd...
        "systemd-run": 'echo "systemd-run $*" >> "$STUBLOG"',
        "systemctl": f'echo "systemctl $*" >> "$STUBLOG"; [ "$1" = is-active ] && exit {0 if running else 3}; exit 0',
        "chgrp": 'echo "chgrp $*" >> "$STUBLOG"',
    }
    for name, body in stubs.items():
        (fake / name).write_text(f"#!/bin/bash\n{body}\n")
        (fake / name).chmod(0o755)
    src = HELPER.read_text()
    src = src.replace("PATH=/usr/local/sbin:", f"PATH={fake}:/usr/local/sbin:", 1)
    src = src.replace("BRAINS_ROOT=/srv/brains", f"BRAINS_ROOT={brains}", 1)
    src = src.replace("STATE_ROOT=/var/lib/brain-update", f"STATE_ROOT={tmp_path / 'state'}", 1)
    helper = tmp_path / "brain-member-update"
    helper.write_text(src)
    helper.chmod(0o755)
    return helper, d, log, tmp_path / "state"


def _run(helper, log, *args, sudo_user="ada-cc", **env):
    e = _clean_env(STUBLOG=str(log), **env)
    if sudo_user:
        e["SUDO_USER"] = sudo_user
    return subprocess.run(["bash", str(helper), *args], env=e, capture_output=True, text=True)


def test_constants_are_the_ones_the_tests_replace():
    src = HELPER.read_text()
    for line in ("PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n",
                 "BRAINS_ROOT=/srv/brains\n", "STATE_ROOT=/var/lib/brain-update\n"):
        assert line in src


def test_reserved_handles_match_member_sh():
    sh = (ROOT / "scripts" / "cc" / "member.sh").read_text()
    want = sh.split('M_RESERVED="', 1)[1].split('"', 1)[0]
    assert f'RESERVED="{want}"' in HELPER.read_text()


def test_update_starts_a_unit_of_its_own(tmp_path):
    helper, d, log, state = _box(tmp_path)
    r = _run(helper, log, "ada")
    assert r.returncode == 0, r.stderr
    calls = log.read_text()
    assert f"systemd-run --unit=brain-update-ada --collect --quiet -p RuntimeMaxSec=1800" in calls
    assert calls.strip().splitlines()[-1].endswith(f"{helper} ada run")              # its own body, nothing else
    assert "chgrp ada-brain" in calls
    assert (state / "ada" / "update.log").exists()
    assert oct((state / "ada" / "update.log").stat().st_mode & 0o777) == "0o640"


def test_check_fetches_as_the_admin(tmp_path):
    helper, d, log, _ = _box(tmp_path)
    subprocess.run(["git", "-C", str(d), "remote", "add", "origin", str(d)], check=True)
    r = _run(helper, log, "ada", "check")
    assert r.returncode == 0, r.stderr
    me = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
    assert f"runuser -u {me} -- env -i HOME=" in log.read_text() and "fetch origin --quiet" in log.read_text()
    assert "systemd-run" not in log.read_text()


def test_run_body_writes_the_log_and_rc(tmp_path):
    helper, d, log, state = _box(tmp_path)
    (state / "ada").mkdir(parents=True)
    r = _run(helper, log, "ada", "run", sudo_user=None, INVOCATION_ID="abc")
    assert r.returncode == 0
    out = (state / "ada" / "update.log").read_text()
    assert f"fake update of {d}" in out and out.strip().splitlines()[-1] == "brain-update rc=0"


@pytest.mark.parametrize("args,env,why", [
    (["ada", "run"], {}, "the unit's body"),                                   # sudo can never reach the body
    (["Ada"], {}, "bad handle"),
    (["admin"], {}, "reserved"),
    (["ada", "rm"], {}, "unknown mode"),
    (["ada", "check", "x"], {}, "usage"),
    (["bob"], {}, "not in"),
])
def test_refuses(tmp_path, args, env, why):
    helper, _, log, _ = _box(tmp_path)
    r = _run(helper, log, *args, **env)
    assert r.returncode == 2 and why in r.stderr, r.stderr


def test_refuses_another_members_bridge(tmp_path):
    helper, _, log, _ = _box(tmp_path)
    r = _run(helper, log, "ada", sudo_user="bob-cc")
    assert r.returncode == 2 and "bob-cc may not update ada" in r.stderr


def test_refuses_when_not_root(tmp_path):
    helper, _, log, _ = _box(tmp_path)
    (tmp_path / "fake" / "id").write_text("#!/bin/bash\necho 1000\n")
    r = _run(helper, log, "ada")
    assert r.returncode == 2 and "root only" in r.stderr


def test_refuses_a_second_run(tmp_path):
    helper, _, log, _ = _box(tmp_path, running=True)
    r = _run(helper, log, "ada")
    assert r.returncode == 2 and "already running" in r.stderr
    assert "systemd-run" not in log.read_text()


@pytest.mark.parametrize("spoil,why", [
    (lambda d: os.chmod(d / "scripts" / "update_brain.sh", 0o775), "group- or world-writable"),
    (lambda d: os.chmod(d / "docker-compose.yml", 0o666), "group- or world-writable"),
    (lambda d: os.chmod(d / ".git" / "hooks", 0o777), "group- or world-writable"),
    (lambda d: (d / "brain-apps" / "installed.json").symlink_to("/etc/passwd"), "symlink in a directory the api writes"),
    (lambda d: (d / "docker-compose.override.yml").symlink_to(d / "docker-compose.yml"), "is a symlink"),
    (lambda d: (d / "scripts" / "update_brain.sh").write_text("#!/bin/bash\necho mine\n"), "changed locally"),
    (lambda d: (d / "docker-compose.yml").write_text("services: {x: {}}\n"), "changed locally"),
])
def test_refuses_a_spoiled_checkout(tmp_path, spoil, why):
    helper, d, log, _ = _box(tmp_path)
    spoil(d)
    r = _run(helper, log, "ada")
    assert r.returncode == 2 and why in r.stderr, r.stderr
    assert "systemd-run" not in (log.read_text() if log.exists() else "")


def test_run_body_rechecks_and_does_not_update_a_spoiled_checkout(tmp_path):
    helper, d, log, state = _box(tmp_path)
    (state / "ada").mkdir(parents=True)
    (d / "brain-apps" / "x").symlink_to("/etc/passwd")
    r = _run(helper, log, "ada", "run", sudo_user=None, INVOCATION_ID="abc")
    out = (state / "ada" / "update.log").read_text()
    assert r.returncode == 2 and "fake update" not in out and out.strip().endswith("brain-update rc=2")


# ------------------------------------------------------------------------ the door ----
def test_door_dry_run_names_two_exact_command_lines(tmp_path):
    r = subprocess.run(["bash", str(ROOT / "scripts" / "member-update-door.sh"), "ada", "--dry-run"],
                       env=_clean_env(), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    line = ("ada-cc ALL=(root) NOPASSWD: /usr/local/sbin/brain-member-update ada, "
            "/usr/local/sbin/brain-member-update ada check")
    assert line in r.stdout and "*" not in line
    assert "+ sudo install -o root -g root -m 755" in r.stdout and "Dry run: nothing was changed" in r.stdout


def test_door_apply_writes_a_checked_sudoers_file(tmp_path):
    fake = tmp_path / "bin"
    fake.mkdir()
    sudo = r'''#!/bin/bash
echo "sudo $*" >> "$FAKE/log"
case "$1" in
  tee) mkdir -p "$FAKE/root$(dirname "$2")"; cat > "$FAKE/root$2" ;;
  mv) mkdir -p "$FAKE/root$(dirname "$4")"; mv "$FAKE/root$3" "$FAKE/root$4" ;;
  *) exit 0 ;;
esac
'''
    (fake / "sudo").write_text(sudo)
    for c in ("id", "getent"):
        (fake / c).write_text("#!/bin/bash\nexit 0\n")
    for f in fake.iterdir():
        f.chmod(0o755)
    env = _clean_env(FAKE=str(tmp_path), PATH=f"{fake}:{os.environ['PATH']}")
    r = subprocess.run(["bash", str(ROOT / "scripts" / "member-update-door.sh"), "ada", "--apply"], env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    got = (tmp_path / "root" / "etc" / "sudoers.d" / "brain-update-ada").read_text()
    assert got.splitlines()[-1] == ("ada-cc ALL=(root) NOPASSWD: /usr/local/sbin/brain-member-update ada, "
                                    "/usr/local/sbin/brain-member-update ada check")
    calls = (tmp_path / "log").read_text()
    assert "sudo visudo -cf /etc/sudoers.d/brain-update-ada.tmp" in calls and "sudo chmod 440" in calls


def test_door_refuses_a_bad_handle():
    r = subprocess.run(["bash", str(ROOT / "scripts" / "member-update-door.sh"), "root", "--apply"],
                       env=_clean_env(), capture_output=True, text=True)
    assert r.returncode == 2 and "bad member handle" in r.stderr


def test_add_member_opens_the_door(tmp_path):
    bins = tmp_path / "bin"
    bins.mkdir()
    (bins / "ss").write_text("#!/bin/sh\n")
    (bins / "ss").chmod(0o755)
    env = _clean_env(BRAINS_ROOT=str(tmp_path / "srv"), SYSTEMD_DIR=str(tmp_path / "systemd"),
                     PATH=f"{bins}:{os.environ['PATH']}", ADMIN_USER="hbar", BRAIN_REPO_URL="https://example.invalid/b.git")
    r = subprocess.run(["bash", str(ROOT / "scripts" / "add-member.sh"), "ada", "2", "--dry-run"], env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert f"+ bash {tmp_path / 'srv' / 'ada'}/scripts/member-update-door.sh ada --apply" in r.stdout


# ---------------------------------------------------------------------- the bridge ----
def _bridge(monkeypatch, tmp_path, **env):
    for k in list(os.environ):
        if k.startswith("CC_") or k in ("BRAIN_API_URL", "BRAIN_DIR"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.setenv("CC_UPDATE_STATE_ROOT", str(tmp_path / "state"))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    spec = importlib.util.spec_from_file_location("cc_bridge_mu", ROOT / "scripts" / "cc" / "cc-bridge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cc_bridge_mu"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_bridge_single_brain_has_no_door(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    assert m._update_state() == {"member": None, "door": False}
    status, body = m._update_door()
    assert status == 404


def test_bridge_member_asks_only_the_helper(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path, CC_MEMBER="ada", CC_MEMBER_N="2", BRAIN_DIR=str(tmp_path / "nobrain"))
    seen = []

    def fake(cmd, **kw):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0 if cmd[0] == "sudo" else 3, "", "")
    monkeypatch.setattr(m.subprocess, "run", fake)
    status, body = m._update_door()
    assert status == 200 and body["started"] is True
    assert seen[0] == ["sudo", "-n", "/usr/local/sbin/brain-member-update", "ada"]
    m._update_door(check=True)
    assert ["sudo", "-n", "/usr/local/sbin/brain-member-update", "ada", "check"] in seen
    assert all(c[0] != "sudo" or c[2] == "/usr/local/sbin/brain-member-update" for c in seen)


def test_bridge_member_reports_a_refusal(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path, CC_MEMBER="ada", CC_MEMBER_N="2", BRAIN_DIR=str(tmp_path / "nobrain"))
    monkeypatch.setattr(m.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 2 if cmd[0] == "sudo" else 3, "", "refused: an update of ada is already running (brain-update-ada)\n"))
    status, body = m._update_door()
    assert status == 409 and "already running" in body["error"]


def test_bridge_state_reads_the_checkout_and_the_rc(monkeypatch, tmp_path):
    repo = tmp_path / "ck"
    repo.mkdir()
    for c in (["init", "-q", "-b", "main"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "a"]):
        subprocess.run(["git", "-C", str(repo), *c], check=True)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", head], check=True)
    m = _bridge(monkeypatch, tmp_path, CC_MEMBER="ada", CC_MEMBER_N="2", BRAIN_DIR=str(repo))
    (tmp_path / "state" / "ada").mkdir(parents=True)
    (tmp_path / "state" / "ada" / "update.log").write_text("==> x\n✓ Update complete.\nbrain-update rc=0\n")
    d = m._update_state()
    assert (d["member"], d["checkout"], d["latest"], d["behind_by"], d["last_rc"]) == ("ada", head, head, 0, 0)
    assert m._update_rc("still going\n") is None and m._update_rc("x\nbrain-update rc=7\n") == 7


def test_bridge_log_frames_follow_from_an_offset(monkeypatch, tmp_path):
    import json
    m = _bridge(monkeypatch, tmp_path, CC_MEMBER="ada", CC_MEMBER_N="2")
    log = tmp_path / "update.log"
    log.write_text("one\ntwo\n")
    first = len("one\n")
    lines = []
    sleeps = []

    def sleep(s):                                   # the helper writes on while the page waits
        sleeps.append(s)
        with open(log, "a") as fh:
            fh.write("==> Rebuilding services\nbrain-update rc=0\n")
    frames = list(m._update_frames(log, first, running=lambda: True, sleep=sleep))
    for f in frames:
        if f.startswith("data: {"):
            lines.append(json.loads(f[6:]))
    assert lines[0]["type"] == "start" and lines[0]["offset"] == first
    assert [x["line"] for x in lines if x["type"] == "log"] == ["two", "==> Rebuilding services", "brain-update rc=0"]
    assert lines[-1] == {"type": "done", "returncode": 0} and frames[-1] == "data: [DONE]\n\n"
    assert lines[1]["offset"] == len("one\ntwo\n")


def test_bridge_log_frames_end_when_the_unit_stopped_without_a_result(monkeypatch, tmp_path):
    import json
    m = _bridge(monkeypatch, tmp_path, CC_MEMBER="ada", CC_MEMBER_N="2")
    log = tmp_path / "update.log"
    log.write_text("half\n")
    frames = list(m._update_frames(log, 0, running=lambda: False, sleep=lambda s: None))
    last = json.loads(frames[-2][6:])
    assert last == {"type": "done", "returncode": None}
