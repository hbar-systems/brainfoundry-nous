"""backup_brain.sh leaves owner-only artifacts whatever the caller's umask (audit 2026-11-13,
update-preupdate-db-dump-readable-by-hands). docker is a stub; nothing real is dumped."""
import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "backup_brain.sh"

DOCKER = """#!/bin/bash
args="$*"
case "$args" in
  *" ps postgres"*) echo "postgres Up"; exit 0 ;;
  *"printenv"*) exit 0 ;;
  *"pg_dump"*) echo "-- dummy dump"; exit 0 ;;
  *"psql"*) echo 3; exit 0 ;;
  *"tar czf"*) printf 'dummytar'; exit 0 ;;
esac
exit 0
"""


def _run(tmp_path, umask, backup_dir, *args):
    brain = tmp_path / "brain"
    brain.mkdir(exist_ok=True)
    (brain / "docker-compose.yml").write_text("services: {}\n")
    fake = tmp_path / "fake"
    fake.mkdir(exist_ok=True)
    (fake / "docker").write_text(DOCKER)
    (fake / "docker").chmod(0o755)
    env = {"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(tmp_path),
           "BRAIN_DIR": str(brain), "BACKUP_DIR": str(backup_dir)}
    cmd = f"umask {umask:03o}; exec bash {SCRIPT} {' '.join(args)}"
    r = subprocess.run(["bash", "-c", cmd], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr + r.stdout
    return r


def _assert_private(top):
    for dirpath, dirnames, filenames in os.walk(top):
        assert stat.S_IMODE(os.stat(dirpath).st_mode) & 0o077 == 0, dirpath
        for f in filenames:
            p = os.path.join(dirpath, f)
            assert stat.S_IMODE(os.stat(p).st_mode) & 0o077 == 0, p


@pytest.mark.parametrize("umask", [0o022, 0o002, 0o027])
@pytest.mark.parametrize("category", [[], ["--pre-update"]])
def test_backup_artifacts_are_owner_only(tmp_path, umask, category):
    bdir = tmp_path / "brain-backups"
    _run(tmp_path, umask, bdir, *category)
    files = [p for p in bdir.rglob("*") if p.is_file()]
    assert any(p.name == "db.sql.gz" for p in files)
    _assert_private(bdir)


def test_existing_open_backup_dir_is_closed_again(tmp_path):
    bdir = tmp_path / "brain-backups"
    old = bdir / "daily" / "20260101T000000Z"
    old.mkdir(parents=True)
    (old / "db.sql.gz").write_text("old")
    for p in (bdir, bdir / "daily", old):
        p.chmod(0o755)
    (old / "db.sql.gz").chmod(0o644)
    _run(tmp_path, 0o022, bdir)
    _assert_private(bdir)


def test_update_brain_has_no_fixed_names_in_shared_tmp():
    """audit 2026-11-13, update-brain-predictable-tmp-paths-as-root: scratch files live in a mktemp -d folder."""
    text = (ROOT / "scripts" / "update_brain.sh").read_text()
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    assert 'UPD_TMP=$(mktemp -d ' in code and "trap 'rm -rf \"$UPD_TMP\"' EXIT" in code
    assert "/tmp/" not in code.replace("${TMPDIR:-/tmp}", "")
