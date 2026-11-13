"""scripts/spoke/spoke.sh join (audit 2026-11-13): the Tailscale package goes to a fresh private
folder, never a fixed shared /tmp name, and a failed download stops before sudo. Stubs only:
no network, no sudo, no installer."""
import os
import pathlib
import re
import stat
import subprocess

SPOKE = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "spoke" / "spoke.sh"

STUBS = {
    "uname": 'case "$1" in -s) echo Darwin;; -m) echo arm64;; *) echo Darwin;; esac',
    "sw_vers": "echo 15.3",
    "curl": 'echo "curl $*" >> "$CALLS"; exit 23',
    "pkgutil": 'echo "pkgutil $*" >> "$CALLS"; echo "Developer ID Installer: Tailscale Inc. (W5364U7YZB)"',
    "sudo": 'echo "sudo $*" >> "$CALLS"',
    "installer": 'echo "installer $*" >> "$CALLS"',
}


def test_failed_download_stops_before_sudo(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in STUBS.items():
        p = bindir / name
        p.write_text("#!/bin/bash\n" + body + "\n")
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
    src = SPOKE.read_text()
    src = re.sub(r"@@[A-Z_]+@@", "filled", src)
    script = tmp_path / "spoke.sh"
    script.write_text(src)
    (tmp_path / "home").mkdir()
    (tmp_path / "t").mkdir()
    calls = tmp_path / "calls"
    env = {"HOME": str(tmp_path / "home"), "TMPDIR": str(tmp_path / "t"), "CALLS": str(calls),
           "PATH": f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}"}
    r = subprocess.run(["bash", str(script), "join"], env=env, capture_output=True, text=True, timeout=30)
    log = calls.read_text() if calls.exists() else ""
    assert "download failed" in r.stdout, r.stdout
    assert "sudo" not in log and "installer" not in log
    assert "/tmp/brain-spoke-tailscale.pkg" not in log
    assert str(tmp_path / "t" / "brain-spoke.") in log           # a mktemp folder under TMPDIR


def test_no_fixed_shared_tmp_path_left():
    assert "/tmp/brain-spoke-tailscale.pkg" not in SPOKE.read_text()
