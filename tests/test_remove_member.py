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


def _box(tmp_path, registry="paul\t1\t8110\t2026-10-21\nada\t4\t8140\t2026-10-27\n", caddyfile=CADDYFILE):
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
    (caddy / "Caddyfile").write_text(caddyfile)
    bins = tmp_path / "bin"
    bins.mkdir()
    stubs = {"docker": "exit 1",                                  # not reachable: stack steps printed only
             "ss": "printf 'LISTEN 0 128 127.0.0.1:8140 0.0.0.0:*\\n'",
             "sudo": 'echo "sudo was called: $*" >&2; exit 1'}   # a dry run must not need it
    for name, body in stubs.items():
        (bins / name).write_text(f"#!/bin/sh\n{body}\n")
        (bins / name).chmod(0o755)
    env = _clean_env(BRAINS_ROOT=str(srv), SYSTEMD_DIR=str(systemd), SUDOERS_DIR=str(sudoers), CADDY_DIR=str(caddy),
                     UPDATE_STATE=str(state), ADMIN_USER="hbar", BACKUP_DIR=str(box / "backups"),
                     PATH=f"{bins}:{os.environ['PATH']}")
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
    (("ada", "--apply"), {}, 2, "needs --export"),                       # the memory is decided out loud
    (("ada", "--apply", "--carry", "/tmp/x"), {}, 2, "needs --export"),
    (("ada", "--dry-run", "--export", "--no-export"), {}, 2, "usage"),
    (("ada", "--dry-run", "--site", "bad name;rm"), {}, 2, "--site takes a host name"),
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


# 2026-11-06 (SEC-1, docs/MEMBER_LIFECYCLE.md): sites found by the port block, the export, step 11.
SHOWCASE = CADDYFILE + """
brain.ada.example {
    reverse_proxy localhost:8140
}

console.brain.ada.example {
    basicauth {
        hbar $2a$14$SHOWHASHSHOWHASHSHOWHASH
    }
    reverse_proxy 127.0.0.1:8141
}
"""


def test_dry_run_finds_sites_by_port_block(tmp_path):
    box, env = _box(tmp_path, caddyfile=SHOWCASE)
    (box / "backups" / "ada-daily-2026-11-01").mkdir(parents=True)
    (box / "backups" / "paul-daily-2026-11-01").mkdir()
    (box / "backups" / "adam-daily-2026-11-01").mkdir()
    for who, ts in (("ada", "20261102T031500Z"), ("paul", "20261102T031501Z")):
        art = box / "backups" / "daily" / ts
        art.mkdir(parents=True)
        (art / "manifest.txt").write_text(f"brain backup manifest\nbrain_dir:     {env['BRAINS_ROOT']}/{who}\n")
    before = _tree(box)
    r = _rm(env, "ada", "--dry-run", "--site", "extra.ada.example")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _tree(box) == before and "sudo was called" not in r.stderr
    out = r.stdout
    drop = next(ln for ln in out.splitlines() if "site blocks to drop:" in ln).split(":", 1)[1].split()
    assert drop == ["ada.brainfoundry.ai", "console.ada.brainfoundry.ai", "extra.ada.example",
                    "brain.ada.example", "console.brain.ada.example"]
    assert "brain.ada.example: lines" in out and "console.brain.ada.example: lines" in out
    assert "extra.ada.example: not found" in out
    assert "paul" not in " ".join(drop) and "notada" not in " ".join(drop)
    assert "DNS (by hand, not here): delete ada.brainfoundry.ai console.ada.brainfoundry.ai extra.ada.example brain.ada.example" in out
    s11 = out.split("== 11")[1]
    assert f"{box}/backups/ada-daily-2026-11-01" in s11 and "paul-daily" not in s11 and "adam-daily" not in s11
    assert f"{box}/backups/daily/20261102T031500Z" in s11 and "20261102T031501Z" not in s11   # by manifest
    for word in ("known_peers.toml", "brain-identity-baseline.tsv", "@BotFather", "snapshots"):
        assert word in s11, word
    assert "$2a$14$" not in out + r.stderr


def test_mixed_block_is_refused_before_anything(tmp_path):
    mixed = CADDYFILE + "\nshared.example {\n    reverse_proxy /ada/* localhost:8147\n    reverse_proxy localhost:3010\n}\n"
    box, env = _box(tmp_path, caddyfile=mixed)
    before = _tree(box)
    r = _rm(env, "ada", "--dry-run")
    assert r.returncode == 1 and "mixes ada's ports" in r.stderr and "shared.example" in r.stderr, r.stdout + r.stderr
    assert "+ " not in r.stdout and _tree(box) == before


def test_dry_run_export_prints_the_carry(tmp_path):
    box, env = _box(tmp_path)
    before = _tree(box)
    r = _rm(env, "ada", "--dry-run", "--export", "--carry", str(tmp_path / "carry"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _tree(box) == before and not (tmp_path / "carry").exists()
    out = r.stdout
    assert f"+ BRAIN_DIR={env['BRAINS_ROOT']}/ada INCLUDE_VAULT=1 bash {ROOT}/scripts/export.sh {tmp_path}/carry" in out
    assert "not in the export: NodeOS memory_proposals" in out
    assert out.index("export.sh") < out.index("down -v")                  # carried before the stack goes
    r = _rm(env, "ada", "--dry-run")
    assert "export.sh" not in r.stdout and "rerun with --export" in r.stdout


def test_caddy_sites_ports_cli(tmp_path):
    f = tmp_path / "Caddyfile"
    f.write_text(SHOWCASE + "\nshared.example {\n    reverse_proxy /ada/* localhost:8147\n    reverse_proxy localhost:3010  # 8140\n}\n")
    cmd = [sys.executable, str(ROOT / "scripts" / "caddy_sites.py"), "ports", str(f)]
    r = subprocess.run(cmd + ["8140", "8141", "8147"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rows = [ln.split("\t") for ln in r.stdout.splitlines()]
    assert [(k, first) for k, first, *_ in rows] == [
        ("pure", "ada.brainfoundry.ai"), ("pure", "console.ada.brainfoundry.ai"), ("pure", "brain.ada.example"),
        ("pure", "console.brain.ada.example"), ("mixed", "shared.example")]
    assert "8110" not in r.stdout and "paul" not in r.stdout
    r = subprocess.run(cmd + ["81x0"], capture_output=True, text=True)
    assert r.returncode == 2 and "numbers" in r.stderr


def test_dry_run_takes_the_member_limits(tmp_path):
    # SEC-1 (2026-11-06): add-member.sh 4b writes a slice, two drop-ins and a limits file; remove takes them.
    box, env = _box(tmp_path)
    systemd, limits = Path(env["SYSTEMD_DIR"]), box / "limits"
    limits.mkdir()
    (systemd / "brain-ada.slice").write_text("[Slice]\n")
    (systemd / "cc-bridge-ada.service.d").mkdir()
    (systemd / "cc-bridge-ada.service.d" / "limits.conf").write_text("[Service]\n")
    (limits / "limits-ada.env").write_text("CC_MAX_JOBS=2\n")
    (limits / "limits-paul.env").write_text("CC_MAX_JOBS=2\n")
    env["LIMITS_DIR"] = str(limits)
    before = _tree(box)
    r = _rm(env, "ada", "--dry-run")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _tree(box) == before
    out = r.stdout
    assert f"+ sudo rm -f {systemd}/brain-ada.slice" in out
    assert f"+ sudo rm -f {limits}/limits-ada.env" in out
    assert f"+ sudo rm -rf {systemd}/cc-bridge-ada.service.d" in out
    assert "claude-tab-ada.service.d" not in out and "limits-paul" not in out   # only what exists, only ada
    assert "member_limits.py parent" in out
