"""scripts/remove-member.sh (2026-10-26), the inverse of add-member.sh, and scripts/caddy_sites.py, its
brace-matched Caddyfile edit. Only the dry run and the refusals are run here: a fake box in a temporary
directory, docker and ss stubbed, no sudo. --apply is never run by these tests."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import caddy_sites  # noqa: E402

CADDYFILE = """{
    email ops@example.invalid
}

paul.brainfoundry.ai {
    reverse_proxy localhost:8110
}

console.paul.brainfoundry.ai {
    basicauth {
        paul $2a$14$PAULHASHPAULHASHPAULHASH
    }
    @cc path /cc /cc/*
    handle @cc {
        reverse_proxy localhost:8118 {
            header_up X-CC-Operator {$CC_OPERATOR_TOKEN_PAUL}
        }
    }
    reverse_proxy localhost:8111
}

ada.brainfoundry.ai {
    reverse_proxy localhost:8140
}

console.ada.brainfoundry.ai {
    basicauth {
        ada $2a$14$ADAHASHADAHASHADAHASH
    }
    @claude path /claude /claude/*
    handle @claude {
        reverse_proxy localhost:8147 {
            header_up X-CC-Operator {$CC_OPERATOR_TOKEN_ADA}
        }
    }
    reverse_proxy localhost:8141   # "}" in a comment {
}

notada.brainfoundry.ai, www.notada.brainfoundry.ai {
    respond "ada.brainfoundry.ai {"
}
"""


def _clean_env(**extra) -> dict:
    e = {k: v for k, v in os.environ.items() if not k.startswith(("CC_", "SUDO_", "INVOCATION_"))}
    e.update(extra)
    return e


def _tree(p: Path) -> dict:
    return {str(f.relative_to(p)): (f.stat().st_mode, f.read_bytes() if f.is_file() else None)
            for f in sorted(p.rglob("*"))}


def _box(tmp_path, registry="paul\t1\t8110\t2026-10-21\nada\t4\t8140\t2026-10-27\n"):
    box = tmp_path / "box"
    srv, systemd, sudoers, caddy, state = (box / d for d in ("srv", "systemd", "sudoers.d", "caddy", "state"))
    for d in (srv / "ada", srv / "paul", systemd / "caddy.service.d", sudoers, caddy, state / "ada"):
        d.mkdir(parents=True)
    (srv / "ada" / "docker-compose.yml").write_text("services: {}\n")
    (srv / "members.tsv").write_text(registry)
    for u in ("cc-bridge-ada.service", "claude-tab-ada.service", "cc-bridge-watch-ada.path", "cc-bridge-watch-ada.service",
              "cc-bridge-paul.service"):
        (systemd / u).write_text("[Unit]\n")
    (systemd / "caddy.service.d" / "cc-ada.conf").write_text("[Service]\n")
    (caddy / "cc-ada.env").write_text("CC_OPERATOR_TOKEN_ADA=x\n")
    for f in ("cc-bridge-ada", "brain-update-ada", "cc-bridge-paul"):
        (sudoers / f).write_text("# x\n")
    (caddy / "Caddyfile").write_text(CADDYFILE)
    bins = tmp_path / "bin"
    bins.mkdir()
    stubs = {"docker": "exit 1",                                  # not reachable: stack steps printed only
             "ss": "printf 'LISTEN 0 128 127.0.0.1:8140 0.0.0.0:*\\n'",
             "sudo": 'echo "sudo was called: $*" >&2; exit 1'}   # a dry run must not need it
    for name, body in stubs.items():
        (bins / name).write_text(f"#!/bin/sh\n{body}\n")
        (bins / name).chmod(0o755)
    env = _clean_env(BRAINS_ROOT=str(srv), SYSTEMD_DIR=str(systemd), SUDOERS_DIR=str(sudoers), CADDY_DIR=str(caddy),
                     UPDATE_STATE=str(state), ADMIN_USER="hbar", PATH=f"{bins}:{os.environ['PATH']}")
    return box, env


def _rm(env, *args):
    return subprocess.run(["bash", str(ROOT / "scripts" / "remove-member.sh"), *args], env=env,
                          capture_output=True, text=True)


def test_dry_run_prints_every_step_and_touches_nothing(tmp_path):
    box, env = _box(tmp_path)
    before = _tree(box)
    r = _rm(env, "ada", "--dry-run", "--carry", str(tmp_path / "carry"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _tree(box) == before and not (tmp_path / "carry").exists()
    assert "sudo was called" not in r.stderr
    out = r.stdout
    srv, systemd = env["BRAINS_ROOT"], env["SYSTEMD_DIR"]
    for action in (
        "port block 4: api 8140  ui 8141  nodeos 8142  postgres 8143  public chat 8144  terminal 8147  bridge 8148",
        f"exec -T api cat /app/runtime/brain_persona.local.md > {tmp_path}/carry/persona-ada.md",
        f"> {tmp_path}/carry/hash-ada.txt",
        f"+ docker compose --project-directory {srv}/ada down -v --rmi local --remove-orphans",
        "+ docker network disconnect brain-ada_llm-network brain-ollama-1", "+ docker network rm brain-ada_llm-network",
        "+ sudo systemctl disable --now cc-bridge-ada.service", f"+ sudo rm -f {systemd}/cc-bridge-watch-ada.path",
        "+ sudo systemctl disable --now claude-tab-ada.service",
        f"+ sudo rm -f {env['SUDOERS_DIR']}/cc-bridge-ada {env['SUDOERS_DIR']}/brain-update-ada", "+ sudo visudo -c",
        f"+ sudo rm -rf {env['UPDATE_STATE']}/ada",
        f"+ sudo rm -f {env['CADDY_DIR']}/cc-ada.env", f"+ sudo rm -f {systemd}/caddy.service.d/cc-ada.conf",
        f"+ sudo rm -rf {srv}/ada", f"+ sudo sed -i /^ada\\t/d {srv}/members.tsv",
        "ada.brainfoundry.ai: lines 22-24", "console.ada.brainfoundry.ai: lines 26-37",
        "only on Valid", "DNS (by hand, not here): delete ada.brainfoundry.ai", "Dry run: nothing was changed",
    ):
        assert action in out, action
    for other in ("paul", "cc-hands-ada", "cc-install-watch-ada", "cc-work-pull-ada"):   # only what exists, only ada
        assert f"rm -f {systemd}/{other}" not in out and f"{other}." not in out.split("== 4")[1].split("== 5")[0]
    assert "$2a$14$" not in out + r.stderr                                                  # no hash printed


def test_half_made_member_not_in_registry(tmp_path):
    box, env = _box(tmp_path, registry="paul\t1\t8110\t2026-10-21\n")
    r = _rm(env, "ada", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "not in" in r.stdout and "ports are not checked" in r.stdout


@pytest.mark.parametrize("args,env_extra,code,why", [
    (("zed", "--dry-run"), {}, 1, "nothing to remove"),
    (("hbar", "--dry-run"), {}, 1, "bad member handle"),
    (("Ada", "--dry-run"), {}, 1, "bad member handle"),
    (("ada", "--dry-run"), {"ADMIN_USER": "root"}, 1, "not root"),
    (("ada", "--yes"), {}, 2, "usage"),
    (("ada", "--dry-run", "--carry"), {}, 2, "usage"),
    (("ada",), {}, 2, "usage"),
])
def test_refusals(tmp_path, args, env_extra, code, why):
    box, env = _box(tmp_path)
    env.update(env_extra)
    before = _tree(box)
    r = _rm(env, *args)
    assert r.returncode == code and why in r.stderr, r.stdout + r.stderr
    assert "+ " not in r.stdout and _tree(box) == before


def test_caddy_sites_drop_keeps_every_other_block(tmp_path):
    out = caddy_sites.drop(CADDYFILE, ["ada.brainfoundry.ai", "console.ada.brainfoundry.ai"])
    assert "ada.brainfoundry.ai {" not in out.replace("notada.brainfoundry.ai", "").replace('"ada.brainfoundry.ai {"', "")
    assert "ADAHASH" not in out and "8140" not in out and "8147" not in out
    assert "PAULHASH" in out and "{$CC_OPERATOR_TOKEN_PAUL}" in out and "email ops@" in out
    assert 'respond "ada.brainfoundry.ai {"' in out                   # quoted braces and a longer name stay
    blocks = caddy_sites.blocks(out)
    assert [b[0] for b in blocks] == [[], ["paul.brainfoundry.ai"], ["console.paul.brainfoundry.ai"],
                                      ["notada.brainfoundry.ai", "www.notada.brainfoundry.ai"]]
    assert "\n\n\n" not in out


def test_caddy_sites_cli(tmp_path):
    f = tmp_path / "Caddyfile"
    f.write_text(CADDYFILE)
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "caddy_sites.py"), "drop", str(f), str(tmp_path / "new"),
                        "ada.brainfoundry.ai", "nope.brainfoundry.ai"], capture_output=True, text=True)
    assert r.returncode == 1 and "nope.brainfoundry.ai: not found" in r.stdout
    assert f.read_text() == CADDYFILE and "ADAHASH" in (tmp_path / "new").read_text()   # console.ada not named
    f.write_text(CADDYFILE + "}\n")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "caddy_sites.py"), "list", str(f), "ada.brainfoundry.ai"],
                       capture_output=True, text=True)
    assert r.returncode == 2 and "unbalanced" in r.stderr
