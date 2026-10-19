"""Multi-instance: several members' brains on one box (2026-10-19, docs/MULTI_INSTANCE.md).

Port block math (shell and Python agree), today's single brain unchanged by default (compose,
install.sh, split-hands.sh, update_brain.sh, the bridge), add-member.sh's dry run and refusals,
and no secret in any printed line. Every host effect is stubbed: nothing here touches a box.

Run from repo root:
    pytest tests/test_multi_instance.py -v
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
sys.path.insert(0, str(ROOT / "scripts"))
import cc_member  # noqa: E402
import member_env  # noqa: E402

# Host-side variables a reasoner's own shell may carry (the bridge passes CC_PORT to its hands).
_AMBIENT = ("CC_MEMBER", "CC_MEMBER_N", "CC_PORT", "TERM_PORT", "UI_PORT", "API_PORT", "BRIDGE_USER", "HANDS_USER",
            "TERM_USER", "CADDY_ROUTES", "COMPOSE_PROJECT_NAME", "BRAIN_DIR", "HEALTH_URL", "TMUX", "ADMIN_USER")


def _clean_env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _AMBIENT}
    env.update(extra)
    return env


def _sh_member(member: str = "", n: str = "") -> dict:
    """member.sh's values for a member (or none), read back from bash."""
    keys = "M_API_PORT M_UI_PORT M_NODEOS_PORT M_PG_PORT M_PUBLIC_CHAT_PORT M_TERM_PORT M_CC_PORT M_SFX M_BRIDGE_USER M_HANDS_USER M_PROJECT M_TOKEN_VAR M_CADDY_ENV".split()
    script = f'. "{ROOT}/scripts/cc/member.sh"; member_load || exit 3; ' + "; ".join(f'echo "{k}=${{{k}}}"' for k in keys)
    r = subprocess.run(["bash", "-c", script], env=_clean_env(CC_MEMBER=member, CC_MEMBER_N=n), capture_output=True, text=True)
    if r.returncode:
        return {"_rc": r.returncode, "_err": r.stderr}
    return dict(line.split("=", 1) for line in r.stdout.splitlines())


# ------------------------------------------------------------------ port block math ----
def test_port_block_math():
    assert cc_member.ports(1) == {"api": 8110, "ui": 8111, "nodeos": 8112, "postgres": 8113,
                                  "public_chat": 8114, "terminal": 8117, "bridge": 8118}
    assert cc_member.ports(2)["api"] == 8120 and cc_member.ports(2)["bridge"] == 8128
    assert cc_member.ports(99)["bridge"] == 9098
    blocks = [set(cc_member.ports(n).values()) for n in range(1, 100)]
    assert all(not (a & b) for i, a in enumerate(blocks) for b in blocks[i + 1:])     # blocks never overlap
    single = set(cc_member.SINGLE.values())
    assert all(not (b & single) for b in blocks)                                       # nor touch today's ports
    for bad in (0, 100, "x", "-1", "01"):
        assert not cc_member.block_ok(bad)
        with pytest.raises(ValueError):
            cc_member.ports(bad)


@pytest.mark.parametrize("n", ["1", "2", "7", "42", "99"])
def test_shell_and_python_agree(n):
    sh = _sh_member("ada", n)
    py = cc_member.ports(n)
    assert (int(sh["M_API_PORT"]), int(sh["M_UI_PORT"]), int(sh["M_NODEOS_PORT"]), int(sh["M_PG_PORT"]),
            int(sh["M_PUBLIC_CHAT_PORT"]), int(sh["M_TERM_PORT"]), int(sh["M_CC_PORT"])) == \
           (py["api"], py["ui"], py["nodeos"], py["postgres"], py["public_chat"], py["terminal"], py["bridge"])
    assert sh["M_SFX"] == "-ada" and sh["M_PROJECT"] == "brain-ada"
    assert sh["M_BRIDGE_USER"] == "ada-cc" and sh["M_HANDS_USER"] == "ada-hands"
    assert sh["M_TOKEN_VAR"] == "CC_OPERATOR_TOKEN_ADA" and sh["M_CADDY_ENV"] == "cc-ada"


def test_handles():
    for ok in ("ada", "bob", "test1", "cy"):
        assert cc_member.handle_ok(ok) and "_rc" not in _sh_member(ok, "1")
    for bad in ("", "a", "Ada", "ada-b", "1ada", "hbar", "hands", "cc", "root", "test", "x" * 17):
        assert not cc_member.handle_ok(bad)
        assert _sh_member(bad, "1").get("_rc") == 3 or bad == ""     # "" is the single brain, not an error
    assert _sh_member("ada", "").get("_rc") == 3                     # a member needs a block


# ------------------------------------------------------------- defaults == today ----
def test_member_sh_defaults_are_today():
    sh = _sh_member()
    assert (sh["M_API_PORT"], sh["M_UI_PORT"], sh["M_NODEOS_PORT"], sh["M_PG_PORT"], sh["M_PUBLIC_CHAT_PORT"],
            sh["M_TERM_PORT"], sh["M_CC_PORT"]) == ("8010", "3010", "8001", "54332", "3020", "7681", "7682")
    assert sh["M_SFX"] == "" and sh["M_PROJECT"] == "" and sh["M_HANDS_USER"] == "hands"
    assert sh["M_TOKEN_VAR"] == "CC_OPERATOR_TOKEN" and sh["M_CADDY_ENV"] == "cc"
    assert cc_member.ports() == cc_member.SINGLE and cc_member.unit("cc-bridge") == "cc-bridge"


def test_compose_host_ports_default_to_today():
    text = (ROOT / "docker-compose.yml").read_text()
    published = re.findall(r'"127\.0\.0\.1:(\$\{[A-Z_]+:-\d+\}|\d+):\d+"', text)
    assert sorted(published) == sorted([
        "${BRAIN_OLLAMA_PORT:-11435}", "${BRAIN_API_PORT:-8010}", "${BRAIN_NODEOS_PORT:-8001}",
        "${BRAIN_UI_PORT:-3010}", "${BRAIN_PUBLIC_CHAT_PORT:-3020}", "${BRAIN_POSTGRES_PORT:-54332}"])
    assert not re.search(r"^name:", text, re.M)          # project: COMPOSE_PROJECT_NAME, else the directory, as before
    assert "container_name" not in text                    # names stay per project


# The installers, run with every host effect stubbed: sudo writes land under a fake root.
_SUDO = r'''#!/usr/bin/env bash
echo "sudo $*" >> "$FAKE/log"
while [ "${1:-}" = "-u" ] || [ "${1:-}" = "-n" ] || [ "${1:-}" = "-H" ]; do [ "$1" = -u ] && shift; shift; done
[ "${1:-}" = env ] && shift
case "${1:-}" in
  tee) shift; [ "${1:-}" = -a ] && shift; mkdir -p "$FAKE/root$(dirname "$1")"; cat >> "$FAKE/root$1" ;;
  install) f="${@: -1}"; src="${@: -2:1}"; mkdir -p "$FAKE/root$(dirname "$f")"; cp "$src" "$FAKE/root$f" ;;
  test) [ -n "${STUB_TEST_OK:-}" ] && exit 0; exit 1 ;;
  grep) exit 1 ;;
  *) exit 0 ;;
esac
'''


def _run_stubbed(tmp_path, script: str, **env) -> tuple[Path, str]:
    fake = tmp_path / "fake"
    (fake / "bin").mkdir(parents=True)
    (fake / "bin" / "sudo").write_text(_SUDO)
    for c in ("systemctl", "curl", "ttyd", "caddy", "sleep", "visudo", "pstree"):
        (fake / "bin" / c).write_text(f'#!/usr/bin/env bash\necho "{c} $*" >> "$FAKE/log"\n')
    for f in (fake / "bin").iterdir():
        f.chmod(0o755)
    cwd = tmp_path / "cwd"
    claude = cwd / "~fakeuser" / ".local" / "bin" / "claude"          # HOME_DIR of a user that does not exist
    claude.parent.mkdir(parents=True)
    claude.write_text("#!/bin/sh\necho claude-stub\n")
    claude.chmod(0o755)
    caddyfile = tmp_path / "Caddyfile"
    caddyfile.write_text("x.brainfoundry.ai {\n    reverse_proxy localhost:8010\n}\nconsole.x.brainfoundry.ai {\n    reverse_proxy localhost:3010\n}\n")
    e = _clean_env(**{"FAKE": str(fake), "PATH": f"{fake / 'bin'}:{os.environ['PATH']}", "BRAIN_USER": "fakeuser",
                      "BRAIN_DIR": str(ROOT), "CADDYFILE": str(caddyfile), **env})
    r = subprocess.run(["bash", str(ROOT / "scripts" / "cc" / script)], cwd=cwd, env=e, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    return fake / "root", r.stdout


def test_install_defaults_are_today(tmp_path):
    root, out = _run_stubbed(tmp_path, "install.sh", BRIDGE_USER="cc")
    units = sorted(p.name for p in (root / "etc" / "systemd" / "system").iterdir())
    assert units == ["cc-bridge-watch.path", "cc-bridge-watch.service", "cc-bridge.service", "cc-install-watch.path",
                     "cc-install-watch.service", "claude-tab.service"]
    tab = (root / "etc/systemd/system/claude-tab.service").read_text()
    assert "User=fakeuser" in tab and "-p 7681 -b /claude" in tab and "Description=Reasoner web terminal for the brain console (ttyd + tmux)\n" in tab
    bridge = (root / "etc/systemd/system/cc-bridge.service").read_text()
    assert "Environment=CC_PORT=7682\n" in bridge and "CC_MEMBER" not in bridge and "BRAIN_API_URL" not in bridge
    assert "Environment=CC_TOOLS=Read,Grep,Glob\nEnvironmentFile=-" in bridge          # no blank line slipped in
    watch = (root / "etc/systemd/system/cc-install-watch.service").read_text()
    assert "CC_MEMBER" not in watch and "install.log\n" in watch
    sudoers = (root / "etc/sudoers.d/cc-bridge.tmp").read_text()
    assert sudoers == ("# The CC bridge user's root verbs (scripts/cc/install.sh). Each is also behind a card in the chat.\n"
                       f"cc ALL=(root) NOPASSWD: /usr/bin/systemctl restart cc-bridge, /usr/bin/systemctl restart claude-tab, "
                       f"/usr/bin/systemctl status *, /usr/bin/journalctl *, /usr/bin/docker ps *, /usr/bin/docker compose "
                       f"--project-directory {ROOT} logs *, /usr/bin/bash {ROOT}/scripts/update_brain.sh, /usr/local/bin/brain-write *\n")
    assert (root / "usr/local/bin/brain-write").exists()
    assert "add route" not in out and "cc-bridge: " in out


def test_install_member_is_walled(tmp_path):
    root, out = _run_stubbed(tmp_path, "install.sh", CC_MEMBER="test1", CC_MEMBER_N="1", CADDY_ROUTES="0")
    sysd = root / "etc" / "systemd" / "system"
    assert sorted(p.name for p in sysd.iterdir()) == [
        "cc-bridge-test1.service", "cc-bridge-watch-test1.path", "cc-bridge-watch-test1.service",
        "cc-install-watch-test1.path", "cc-install-watch-test1.service", "claude-tab-test1.service"]
    tab = (sysd / "claude-tab-test1.service").read_text()
    assert "User=test1-cc" in tab and "-p 8117 -b /claude" in tab                    # the door is never the admin
    bridge = (sysd / "cc-bridge-test1.service").read_text()
    assert "User=test1-cc" in bridge and "CC_PORT=8118" in bridge and "CC_MEMBER=test1" in bridge
    assert "BRAIN_API_URL=http://127.0.0.1:8110" in bridge
    assert "reload-or-restart cc-bridge-test1.service" in (sysd / "cc-bridge-watch-test1.service").read_text()
    watch = (sysd / "cc-install-watch-test1.service").read_text()
    assert "CC_MEMBER=test1" in watch and "CC_MEMBER_N=1" in watch and "CADDY_ROUTES=0" in watch
    sudoers = (root / "etc/sudoers.d/cc-bridge-test1.tmp").read_text()
    verbs = sudoers.split("NOPASSWD: ", 1)[1].strip()
    assert verbs == ("/usr/bin/systemctl restart cc-bridge-test1, /usr/bin/systemctl restart claude-tab-test1, "
                     "/usr/bin/systemctl status cc-bridge-test1, /usr/bin/systemctl status claude-tab-test1")
    assert "*" not in verbs and not (root / "usr/local/bin/brain-write").exists()
    assert "CADDY_ROUTES=0: Caddyfile untouched" in out
    assert "Caddyfile.bak" not in (tmp_path / "fake" / "log").read_text()


def test_split_hands_defaults_and_member(tmp_path):
    root, _ = _run_stubbed(tmp_path / "a", "split-hands.sh", STUB_TEST_OK="1", BRAIN_DIR=str(tmp_path / "nobrain"))
    assert (root / "etc/sudoers.d/cc-hands").read_text().endswith("hbar ALL=(hands) NOPASSWD: /usr/bin/env\n")
    assert re.fullmatch(r"CC_OPERATOR_TOKEN=[0-9a-f]{48}\n", (root / "etc/caddy/cc.env").read_text())
    assert (root / "etc/systemd/system/caddy.service.d/cc.conf").read_text() == "[Service]\nEnvironmentFile=/etc/caddy/cc.env\n"
    root, out = _run_stubbed(tmp_path / "b", "split-hands.sh", STUB_TEST_OK="1", BRAIN_DIR=str(tmp_path / "nobrain"),
                             CC_MEMBER="test1", CC_MEMBER_N="1", CADDY_ROUTES="0")
    assert (root / "etc/sudoers.d/cc-hands-test1").read_text() == (
        "Defaults:test1-cc !syslog\nDefaults:test1-cc umask_override, umask=0002\n"
        "test1-cc ALL=(test1-hands) NOPASSWD: /usr/bin/env\nhbar ALL=(test1-hands) NOPASSWD: /usr/bin/env\n")
    assert re.fullmatch(r"CC_OPERATOR_TOKEN_TEST1=[0-9a-f]{48}\n", (root / "etc/caddy/cc-test1.env").read_text())
    assert not (root / "etc/caddy/cc.env").exists()                                   # the first brain's token untouched
    log = (tmp_path / "b" / "fake" / "log").read_text()
    assert "restart caddy" not in log and "systemctl restart cc-bridge-test1" in log
    assert "127.0.0.1:8118/cc/health" in log
    tok = (root / "etc/caddy/cc-test1.env").read_text().split("=", 1)[1].strip()
    assert tok not in out                                                                 # never printed


def _update_trace(tmp_path, env_text: str | None, dirname: str = "brain") -> str:
    d = tmp_path / dirname
    d.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(d)], check=True)                            # no origin: the script stops early
    if env_text is not None:
        (d / ".env").write_text(env_text)
    r = subprocess.run(["bash", "-x", str(ROOT / "scripts" / "update_brain.sh"), str(d)], env=_clean_env(),
                       capture_output=True, text=True, cwd=tmp_path)
    assert "No 'origin' remote" in r.stdout
    return r.stderr


def test_update_brain_defaults_and_member_path(tmp_path):
    trace = _update_trace(tmp_path / "a", None)
    assert "HEALTH_URL=http://127.0.0.1:8010/health" in trace and "PROJECT=brain\n" in trace
    assert "export COMPOSE_PROJECT_NAME" not in trace and "umask 027" not in trace       # compose decides, as before
    trace = _update_trace(tmp_path / "b", "BRAIN_API_KEY=" + "a" * 64 + "\nCOMPOSE_PROJECT_NAME=brain-test1\nBRAIN_API_PORT=8110\n", "test1")
    assert "HEALTH_URL=http://127.0.0.1:8110/health" in trace and "COMPOSE_PROJECT_NAME=brain-test1" in trace
    assert "a" * 64 not in trace                                                         # only the named lines are read
    assert "+ umask 027" in trace                                                        # nothing it writes is group-writable


def test_api_passes_its_checkout_to_the_scripts():
    src = (ROOT / "api" / "main.py").read_text()
    assert src.count('["bash", script, BRAIN_HOST_DIR]') == 3


# ----------------------------------------------------------------------- bridge ----
def _bridge(monkeypatch, tmp_path, **env):
    for k in _AMBIENT + ("BRAIN_API_URL",):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    spec = importlib.util.spec_from_file_location("cc_bridge_mi", ROOT / "scripts" / "cc" / "cc-bridge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cc_bridge_mi"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_bridge_single_brain_unchanged(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    assert (m.PORT, m.BRAIN_API_URL, m.BRIDGE_UNIT, m.TAB_UNIT) == (7682, "http://127.0.0.1:8010", "cc-bridge", "claude-tab")
    assert m._RESTART_CMD.match("sudo systemctl restart cc-bridge")


def test_bridge_member(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path, CC_MEMBER="ada", CC_MEMBER_N="2", CC_BOX="1")
    assert (m.PORT, m.BRAIN_API_URL, m.BRIDGE_UNIT, m.TAB_UNIT) == (8128, "http://127.0.0.1:8120", "cc-bridge-ada", "claude-tab-ada")
    assert m._RESTART_CMD.match("sudo systemctl restart cc-bridge-ada")
    assert not m._RESTART_CMD.match("sudo systemctl restart cc-bridge")                  # never another brain's bridge
    assert "sudo systemctl restart cc-bridge-ada" in m.SYSTEM and "journalctl" not in m.SYSTEM and "brain-write" not in m.SYSTEM
    m = _bridge(monkeypatch, tmp_path, CC_MEMBER="ada", CC_MEMBER_N="2", CC_PORT="9999")
    assert m.PORT == 9999                                                                 # an explicit port wins


# ------------------------------------------------------------------- add-member ----
def _add(tmp_path, *args, ss: str = "", registry: str | None = None):
    bins = tmp_path / "bin"
    bins.mkdir(parents=True, exist_ok=True)
    (bins / "ss").write_text(f"#!/bin/sh\nprintf '%s' '{ss}'\n")
    (bins / "ss").chmod(0o755)
    root = tmp_path / "srv"
    if registry is not None:
        root.mkdir()
        (root / "members.tsv").write_text(registry)
    env = _clean_env(BRAINS_ROOT=str(root), SYSTEMD_DIR=str(tmp_path / "systemd"), PATH=f"{bins}:{os.environ['PATH']}",
                     ADMIN_USER="hbar", BRAIN_REPO_URL="https://example.invalid/brain.git")
    return subprocess.run(["bash", str(ROOT / "scripts" / "add-member.sh"), *args], env=env, capture_output=True, text=True), root


def test_add_member_dry_run(tmp_path):
    r, root = _add(tmp_path, "test1", "1", "--dry-run")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert not root.exists()                                                              # touched nothing
    assert "api 8110  ui 8111  nodeos 8112  postgres 8113  public chat 8114  terminal 8117  bridge 8118" in out
    for action in ("+ sudo useradd -m -s /bin/bash -U -G test1-brain test1-cc", "+ sudo chmod 700 /home/test1-hands",
                   f"+ sudo install -d -o hbar -g test1-brain -m 2750 {root}/test1",
                   f"+ git clone -q https://example.invalid/brain.git {root}/test1",
                   f"scripts/member_env.py test1 1 ", f"+ docker compose --project-directory {root}/test1 up -d --build",
                   "profiles: [\"own-ollama\"]", "brains-ollama-link.timer",
                   "CC_MEMBER=test1 CC_MEMBER_N=1", "CADDY_ROUTES=0 bash", "scripts/cc/split-hands.sh",
                   "test1.brainfoundry.ai {", "console.test1.brainfoundry.ai {", "reverse_proxy localhost:8110",
                   "reverse_proxy localhost:8111", "reverse_proxy localhost:8117 {", "reverse_proxy localhost:8118 {",
                   "header_up X-CC-Operator {$CC_OPERATOR_TOKEN_TEST1}", "Dry run: nothing was changed"):
        assert action in out, action
    assert "docker.sock" not in out                                                       # the Update tab socket is opt-in
    users = out.split("== 1 users")[1].split("== 2")[0].split(")", 1)[1]
    assert "docker" not in users and not re.search(r"-G\S* sudo|-aG sudo", users)        # no sudo, not in docker
    r, _ = _add(tmp_path / "u", "test1", "1", "--dry-run", "--update-tab")
    assert "/var/run/docker.sock:/var/run/docker.sock" in r.stdout


@pytest.mark.parametrize("args,registry,ss,why", [
    (("bob", "2", "--dry-run"), "bob\t1\t8110\t2026-10-19\n", "", "handle bob is already in"),
    (("cy", "1", "--dry-run"), "bob\t1\t8110\t2026-10-19\n", "", "port block 1 is already taken"),
    (("cy", "3", "--dry-run"), None, "LISTEN 0 128 127.0.0.1:8133 0.0.0.0:*", "port 8133 of block 3 is in use"),
    (("hbar", "3", "--dry-run"), None, "", "bad member handle"),
    (("Cy", "3", "--dry-run"), None, "", "bad member handle"),
    (("cy", "0", "--dry-run"), None, "", "needs CC_MEMBER_N"),
    (("cy", "100", "--apply"), None, "", "needs CC_MEMBER_N"),
])
def test_add_member_refuses(tmp_path, args, registry, ss, why):
    r, _ = _add(tmp_path, *args, ss=ss, registry=registry)
    assert r.returncode != 0 and why in r.stderr, r.stdout + r.stderr
    assert "+ sudo" not in r.stdout                                                       # refused before any action


def test_add_member_refuses_existing_checkout(tmp_path):
    (tmp_path / "srv" / "ada").mkdir(parents=True)
    r, _ = _add(tmp_path, "ada", "4", "--apply")
    assert r.returncode == 1 and "srv/ada exists" in r.stderr and "+ " not in r.stdout


def test_add_member_bad_mode(tmp_path):
    r, root = _add(tmp_path, "ada", "4", "--yes")
    assert r.returncode == 2 and "usage" in r.stderr and not root.exists()


# ------------------------------------------------------------ secrets stay in files ----
def test_member_env_secrets_only_in_the_file(tmp_path):
    out = tmp_path / ".env"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "member_env.py"), "test1", "1",
                        str(ROOT / ".env.example"), str(out)], capture_output=True, text=True, env=_clean_env())
    assert r.returncode == 0, r.stderr
    assert oct(out.stat().st_mode & 0o777) == "0o600"
    env = dict(line.split("=", 1) for line in out.read_text().splitlines() if re.match(r"^[A-Z][A-Z0-9_]*=", line))
    for k in member_env.SECRET_KEYS:
        assert re.fullmatch(r"[0-9a-f]{64}", env[k]), k
        assert env[k] not in r.stdout and env[k] not in r.stderr
    for k in member_env.KEYPAIR_KEYS:
        if env.get(k):
            assert env[k] not in r.stdout + r.stderr
    assert len({env[k] for k in member_env.SECRET_KEYS}) == len(member_env.SECRET_KEYS)      # all fresh, all distinct
    assert env["COMPOSE_PROJECT_NAME"] == "brain-test1" and env["BRAIN_API_PORT"] == "8110"
    assert env["BRAIN_HOST_DIR"] == "/srv/brains/test1" and env["OLLAMA_URL"] == "http://ollama:11434"
    assert env["POSTGRES_PASSWORD"] != "postgres"
    r2 = subprocess.run([sys.executable, str(ROOT / "scripts" / "member_env.py"), "test1", "1",
                         str(ROOT / ".env.example"), str(out)], capture_output=True, text=True, env=_clean_env())
    assert r2.returncode == 1 and "exists" in r2.stderr                                  # written once, never overwritten


def test_build_is_deterministic_with_given_secrets():
    text = member_env.build("BRAIN_ID=x\nBRAIN_API_KEY=\n# keep me\n", "ada", 2, token=lambda: "S" * 8)
    assert "BRAIN_ID=ada\nBRAIN_API_KEY=SSSSSSSS\n# keep me\n" in text
    assert "BRAIN_UI_PORT=8121" in text and text.count("BRAIN_API_KEY=") == 1


def test_no_secret_shaped_line_in_dry_run(tmp_path):
    r, _ = _add(tmp_path, "test1", "1", "--dry-run")
    assert not re.search(r"[0-9a-f]{32,}", r.stdout + r.stderr)
    assert not re.search(r"(?i)(password|secret|api_key|token)\s*=\s*\S", r.stdout + r.stderr)
