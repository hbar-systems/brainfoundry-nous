"""scripts/spoke/door.sh fences (audit 2026-11-13): leaf links, Library in any case, hidden
folders, and undo ids are refused. Runs the real script against a scratch home; no network."""
import os
import pathlib
import subprocess

import pytest

DOOR = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "spoke" / "door.sh"


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    (h / "Documents").mkdir(parents=True)
    (h / "Documents" / "a.txt").write_text("hello")
    (h / "Library" / "Mail").mkdir(parents=True)
    (h / "Library" / "Mail" / "secret.txt").write_text("SECRET")
    (h / ".ssh").mkdir()
    (h / ".ssh" / "id").write_text("KEY")
    (tmp_path / "outside.txt").write_text("OUTSIDE")
    (h / "Documents" / "lib").symlink_to(h / "Library" / "Mail")
    (h / "Documents" / "hid").symlink_to(h / ".ssh" / "id")
    (h / "Documents" / "out").symlink_to(tmp_path / "outside.txt")
    (h / ".brain-spoke").mkdir()
    (h / ".brain-spoke" / "mode").write_text("organise\n")
    return h


def door(home, *args, stdin=""):
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    return subprocess.run(["bash", str(DOOR), *args], env=env, input=stdin,
                          capture_output=True, text=True, timeout=30)


def test_plain_file_readable(home):
    r = door(home, "peek", "Documents/a.txt")
    assert r.returncode == 0 and r.stdout == "hello"


@pytest.mark.parametrize("rel", ["Documents/lib", "Documents/hid", "Documents/out",
                                 "library/x", "LIBRARY/Mail/secret.txt", "Library/Mail/secret.txt",
                                 ".ssh/id", "Documents/../.ssh/id"])
def test_fenced_paths_refused(home, rel):
    for verb in ("peek", "list"):
        r = door(home, verb, rel)
        assert r.returncode == 3, (verb, rel, r.stdout)
        assert "SECRET" not in r.stdout and "KEY" not in r.stdout and "OUTSIDE" not in r.stdout


def test_undo_needs_organise_and_a_real_id(home):
    r = door(home, "apply", stdin="mkdir\tDocuments/new\nmv\tDocuments/a.txt\tDocuments/new/a.txt\n")
    assert r.returncode == 0, r.stderr
    uid = r.stdout.strip().split()[-1]
    for bad in ("../../tmp/x", "a/b", "20261113T000000Z/../x", ""):
        assert door(home, "undo", bad).returncode == 3
    (home / ".brain-spoke" / "mode").write_text("look\n")
    assert door(home, "undo", uid).returncode == 3
    (home / ".brain-spoke" / "mode").write_text("organise\n")
    r = door(home, "undo", uid)
    assert r.returncode == 0, r.stderr
    assert (home / "Documents" / "a.txt").read_text() == "hello"
    assert not (home / "Documents" / "new").exists()


def test_undo_replay_is_fenced(home):
    uid = "20261113T000000Z"
    (home / ".brain-spoke" / "undo").mkdir(exist_ok=True)
    (home / ".brain-spoke" / "undo" / f"{uid}.tsv").write_text(
        f"mv\t{home}/.ssh/id\t{home}/Documents/stolen\n")
    r = door(home, "undo", uid)
    assert r.returncode == 3
    assert (home / ".ssh" / "id").exists() and not (home / "Documents" / "stolen").exists()
