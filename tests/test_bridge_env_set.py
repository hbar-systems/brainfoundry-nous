"""scripts/cc/member.sh bridge_env_set and safe_user (audit 2026-11-13: cc-env-rewrite-root-follows-member-owned-dir-links,
cc-install-member-env-values-interpolated-into-root-shell). Runs as this user (BRIDGE_USER = us, so no sudo)."""
import getpass
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMBER_SH = ROOT / "scripts" / "cc" / "member.sh"


def _set(env_file: Path, key: str, value: str):
    return subprocess.run(["bash", "-c", f'. "{MEMBER_SH}"; bridge_env_set "$1"', "x", key], input=value, text=True,
                          capture_output=True, env={"PATH": "/usr/bin:/bin", "BRIDGE_USER": getpass.getuser(),
                                                    "ENV_FILE": str(env_file)})


def test_sets_replaces_and_keeps_other_lines(tmp_path):
    f = tmp_path / "env"
    f.write_text("A=1\nCC_TOOLS=old\n")
    assert _set(f, "CC_TOOLS", '"Read,Bash(git status:*)"').returncode == 0
    assert f.read_text() == 'A=1\nCC_TOOLS="Read,Bash(git status:*)"\n'
    assert (os.stat(f).st_mode & 0o777) == 0o600


def test_value_is_data_never_shell(tmp_path):
    f = tmp_path / "env"
    f.write_text("")
    marker = tmp_path / "ran"
    v = f"x'; touch {marker}; echo '$(touch {marker})`touch {marker}`"
    assert _set(f, "CC_TOOLS", v).returncode == 0
    assert not marker.exists() and f.read_text() == f"CC_TOOLS={v}\n"


def test_refuses_bad_key_and_newline(tmp_path):
    f = tmp_path / "env"
    f.write_text("A=1\n")
    assert _set(f, "A;touch x", "1").returncode != 0
    assert _set(f, "B", "1\nUSER=root").returncode != 0
    assert f.read_text() == "A=1\n"


def test_a_planted_tmp_link_is_never_written(tmp_path):
    f = tmp_path / "env"
    f.write_text("A=1\n")
    victim = tmp_path / "victim"
    victim.write_text("keep\n")
    os.symlink(victim, tmp_path / "env.tmp")       # the old fixed temp name
    assert _set(f, "B", "2").returncode == 0
    assert victim.read_text() == "keep\n" and f.read_text() == "A=1\nB=2\n"


def test_safe_user():
    run = lambda v: subprocess.run(["bash", "-c", f'. "{MEMBER_SH}"; safe_user "$1"', "x", v], capture_output=True, text=True).stdout
    assert run("ada-hands") == "ada-hands"
    assert run("x|e touch /tmp/p|") == "" and run("") == "" and run("Root") == ""


def test_installers_never_paste_env_values_into_root_shells():
    for name in ("install.sh", "split-hands.sh", "set-env.sh"):
        text = (ROOT / "scripts" / "cc" / name).read_text()
        assert "$ENV_FILE.tmp" not in text and "'$ENV_FILE.tmp'" not in text, name
        assert 'sudo tee -a "$ENV_FILE"' not in text, name
