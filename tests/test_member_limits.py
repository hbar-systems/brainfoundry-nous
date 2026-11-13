"""Per-member limits on a shared box (SEC-1 front 3, 2026-11-06, docs/MEMBER_LIMITS.md).

The compose defaults change nothing for a brain alone on its box, the profile fits five members plus
the admin brain on friends-1 and a seventh tenant does not, the check fails on an unlimited member,
add-member.sh's dry run prints the override, the slice, the drop-ins and the job cap and touches
nothing, the bridge's job cap and the admin's spend ceiling hold. Every host effect is stubbed.

    pytest tests/test_member_limits.py -v
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import member_limits as L  # noqa: E402
import cc_extras as X  # noqa: E402
import cc_spend as S  # noqa: E402

from tests.test_multi_instance import _add, _clean_env  # noqa: E402

FRIENDS1 = "paul\t1\t8110\t2026-10-22\nalexander\t2\t8120\t2026-10-25\nelena\t3\t8130\t2026-10-25\n" \
           "christos\t4\t8140\t2026-10-27\nsinan\t5\t8150\t2026-11-04\n"
SCRIPT = str(ROOT / "scripts" / "member_limits.py")


def _env(**extra) -> dict:
    env = {k: v for k, v in _clean_env().items() if not k.startswith(("BRAIN_LIMIT_", "BOX_"))}
    env.update(extra)
    return env


def _run(*args, **env):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, env=_env(**env))


# ------------------------------------------------------------ compose defaults ----
def test_compose_limits_default_to_none():
    text = (ROOT / "docker-compose.yml").read_text()
    for svc in ("OLLAMA", "API", "NODEOS", "UI", "PUBLIC_CHAT", "POSTGRES", "REDIS"):
        assert f"cpus: ${{BRAIN_LIMIT_{svc}_CPUS:-0}}" in text, svc
        assert f"mem_limit: ${{BRAIN_LIMIT_{svc}_MEM:-0}}" in text, svc
        assert f"mem_reservation: ${{BRAIN_LIMIT_{svc}_MEM_RES:-0}}" in text, svc
        assert f"pids_limit: ${{BRAIN_LIMIT_{svc}_PIDS:--1}}" in text, svc
    assert text.count("logging: *brain-logging") == 7                       # every service rotates its log
    assert 'max-size: "${BRAIN_LOG_MAX_SIZE:-20m}"' in text and 'max-file: "${BRAIN_LOG_MAX_FILE:-5}"' in text


@pytest.mark.skipif(not shutil.which("docker"), reason="docker not installed")
def test_compose_config_unlimited_by_default_and_member_override_applies(tmp_path):
    def cfg(*files):
        r = subprocess.run(["docker", "compose", "--project-directory", str(ROOT), "-p", "limits-test",
                            *sum((["-f", f] for f in files), []), "--env-file", str(ROOT / ".env.example"), "config"],
                           capture_output=True, text=True, env=_env())
        if r.returncode and "Cannot connect" not in r.stderr and "unknown" in r.stderr:
            pytest.skip(f"docker compose unusable here: {r.stderr[:120]}")
        assert r.returncode == 0, r.stderr
        return r.stdout
    base = cfg(str(ROOT / "docker-compose.yml"))
    assert "mem_limit" not in base and "cpus:" not in base and "mem_reservation" not in base
    assert base.count("pids_limit: -1") == 7
    ov = tmp_path / "override.yml"
    ov.write_text(L.member_override(L.profile({})))
    member = cfg(str(ROOT / "docker-compose.yml"), str(ov))
    assert 'mem_limit: "2684354560"' in member and "pids_limit: 512" in member      # api: 2560m, 512
    assert "pids_limit: -1" not in member.split("\nnetworks:")[0]                 # every started service is limited
    assert "\n  ollama:" not in member.split("\nnetworks:")[0] or "own-ollama" in member


# ------------------------------------------------------------ the profile ----
def test_mib_parsing():
    assert L.mib("2560m") == 2560 and L.mib("2g") == 2048 and L.mib("2560M") == 2560 and L.mib("1024k") == 1
    assert L.mib(2684354560) == 2560 and L.mib("2684354560") == 2560              # compose renders bytes
    for none in (None, "", "0", 0, "infinity", "-1", "max"):
        assert L.mib(none) is None
    with pytest.raises(ValueError):
        L.mib("lots")


def test_profile_env_overrides_and_refusals():
    p = L.profile({"BRAIN_LIMIT_API_MEM": "3g", "BRAIN_LIMIT_PUBLIC_CHAT_CPUS": "0.25", "BRAIN_LIMIT_JOBS": "2",
                   "BRAIN_LIMIT_SPEND_EUR": "10", "BRAIN_LIMIT_SLICE_TASKS": "300"})
    assert p["services"]["api"]["mem"] == "3g" and p["services"]["public-chat"]["cpus"] == "0.25"
    assert p["jobs"] == 2 and p["spend_eur"] == 10 and p["slice"]["tasks"] == 300
    with pytest.raises(ValueError):
        L.profile({"BRAIN_LIMIT_API_MEM_RES": "4g"})                               # reservation over ceiling
    with pytest.raises(ValueError):
        L.profile({"BRAIN_LIMIT_UI_MEM": "big"})


# ------------------------------------------------------------ the check ----
def test_plan_fits_friends1_and_a_seventh_tenant_does_not(tmp_path):
    tsv = tmp_path / "members.tsv"
    tsv.write_text(FRIENDS1)
    r = _run("check", "--plan", str(tsv))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "guaranteed memory 13312M of 15577M" in r.stdout and "limits: OK" in r.stdout
    for m in ("admin", "paul", "alexander", "elena", "christos", "sinan", "ollama"):
        assert re.search(rf"^{m}\s", r.stdout, re.M), m
    assert "disk quotas 90G + shared reserve 40G = 130G of 150G" in r.stdout
    r2 = _run("check", "--plan", str(tsv), "--add", "2")                           # 8 tenants
    assert r2.returncode == 1 and "overcommitted" in r2.stdout and "limits: FAIL" in r2.stdout


def test_check_fails_on_an_unlimited_member(tmp_path):
    root = tmp_path / "srv"
    (root / "paul").mkdir(parents=True)
    (root / "members.tsv").write_text("paul\t1\t8110\t2026-10-22\n")
    (root / "paul" / "docker-compose.override.yml").write_text('services:\n  ollama:\n    profiles: ["own-ollama"]\n')
    r = _run("check", "--brains-root", str(root), "--no-admin", "--systemd-dir", str(tmp_path / "sd"),
             "--limits-dir", str(tmp_path / "lim"))
    assert r.returncode == 1 and "paul: unlimited: no memory ceiling" in r.stdout
    assert "paul: unlimited: no cap on running jobs" in r.stdout


def test_check_reads_what_add_member_writes(tmp_path):
    """The files add-member.sh writes, read back by the check: limited, and within the box."""
    root, sd, lim = tmp_path / "srv", tmp_path / "sd", tmp_path / "lim"
    p = L.profile({})
    (root / "paul").mkdir(parents=True)
    sd.mkdir(); lim.mkdir()
    (root / "members.tsv").write_text("paul\t1\t8110\t2026-10-22\n")
    (root / "paul" / "docker-compose.override.yml").write_text(L.member_override(p))
    (sd / "brain-paul.slice").write_text(L.unit_text("paul", "slice", p))
    (lim / "limits-paul.env").write_text(L.unit_text("paul", "env", p))
    admin = tmp_path / "admin"
    admin.mkdir()
    (admin / "docker-compose.override.yml").write_text(L.merge_override("", p, admin=True))
    (sd / "brain-admin.slice").write_text(L.unit_text("admin", "slice", p))
    (lim / "limits-admin.env").write_text(L.unit_text("admin", "env", p))
    r = _run("check", "--brains-root", str(root), "--admin-dir", str(admin), "--systemd-dir", str(sd), "--limits-dir", str(lim))
    assert r.returncode == 0, r.stdout
    assert re.search(r"^paul\s+6912M\s+1536M\s+5.5\s+2240\s+3\s", r.stdout, re.M), r.stdout
    assert re.search(r"^ollama\s+5120M\s+3072M", r.stdout, re.M)


def test_merge_keeps_existing_keys(tmp_path):
    p = L.profile({})
    text = ('services:\n  ollama:\n    profiles: ["own-ollama"]\n  api:\n    volumes:\n'
            '      - ./api/identity/known_peers.toml:/app/api/identity/known_peers.toml:ro\n    mem_limit: 9g\n')
    import yaml
    doc = yaml.safe_load(L.merge_override(text, p))
    assert doc["services"]["ollama"] == {"profiles": ["own-ollama"]}                 # a member's Ollama stays off
    assert doc["services"]["api"]["volumes"] == ["./api/identity/known_peers.toml:/app/api/identity/known_peers.toml:ro"]
    assert doc["services"]["api"]["mem_limit"] == "2560m"                            # replaced, not doubled
    adm = yaml.safe_load(L.merge_override("services:\n  ollama:\n    environment:\n      - OLLAMA_KEEP_ALIVE=-1\n", p, admin=True))
    assert adm["services"]["ollama"]["environment"] == ["OLLAMA_KEEP_ALIVE=-1", "OLLAMA_NUM_PARALLEL=2", "OLLAMA_MAX_LOADED_MODELS=2"]
    assert adm["services"]["ollama"]["mem_limit"] == "5120m"


def test_units_and_parents():
    p = L.profile({"BRAIN_LIMIT_SPEND_EUR": "12.5"})
    sl = L.unit_text("ada", "slice", p)
    assert "CPUQuota=150%" in sl and "MemoryMax=2560M" in sl and "MemoryLow=256M" in sl and "TasksMax=1024" in sl
    br = L.unit_text("ada", "bridge", p)
    assert "Slice=brain-ada.slice" in br and "EnvironmentFile=-/etc/brainfoundry/limits-ada.env" in br
    assert "Slice=brain-ada.slice" in L.unit_text("ada", "term", p)
    env = L.unit_text("ada", "env", p)
    assert "CC_MAX_JOBS=3" in env and "CC_SPEND_CAP_EUR=12.5" in env
    assert "CC_SPEND_CAP_EUR=" not in L.unit_text("ada", "env", L.profile({})).replace("# CC_SPEND_CAP_EUR=", "")
    assert L.unit_names("admin") == ("brain-admin.slice", "cc-bridge.service", "claude-tab.service")
    assert "MemoryLow=1536M" in L.parent_text("brain", 6, L.profile({}))
    assert "MemoryLow=10752M" in L.parent_text("system", 6, L.profile({}))          # 6 x 1280 + 3072


def test_cli_prints_only(tmp_path):
    before = sorted(p.name for p in tmp_path.iterdir())
    for args in (("profile",), ("override",), ("unit", "ada", "slice"), ("parent", "brain", str(tmp_path / "none.tsv")),
                 ("check", "--plan", str(tmp_path / "none.tsv"))):
        r = _run(*args, BRAINS_ROOT=str(tmp_path))
        assert r.returncode == 0, (args, r.stderr)
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert _run("unit", "Bad-Name", "slice").returncode == 2
    assert _run("profile", BRAIN_LIMIT_API_MEM="huge").returncode == 2


def test_disk_alarm_over_quota(tmp_path, monkeypatch):
    root = tmp_path / "srv"
    (root / "ada").mkdir(parents=True)
    (root / "ada" / "blob").write_bytes(b"x" * (3 * 1024 * 1024))
    monkeypatch.setattr(L, "member_volumes", lambda m: [])
    lines, problems = L.disk(["ada"], root, quota_gb=1 / 1024, home=str(tmp_path / "home"))   # a 1 MB quota
    assert any(ln.startswith("ada") for ln in lines) and problems and "over its 1 MB quota" in problems[0]
    lines, problems = L.disk(["ada"], root, quota_gb=1, home=str(tmp_path / "home"))
    assert not [p for p in problems if p.startswith("ada")]


# ------------------------------------------------------------ add-member ----
def test_add_member_dry_run_writes_the_limits(tmp_path):
    r, root = _add(tmp_path, "test1", "1", "--dry-run")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert not root.exists() and not (tmp_path / "systemd").exists()             # touched nothing
    for want in ("mem_limit: 2560m", "mem_reservation: 768m", "pids_limit: 512", "CPUQuota=150%", "TasksMax=1024",
                 "Slice=brain-test1.slice", "EnvironmentFile=-/etc/brainfoundry/limits-test1.env", "CC_MAX_JOBS=3",
                 f"+ write {tmp_path / 'systemd'}/brain-test1.slice (root, 644)",
                 f"+ write {tmp_path / 'systemd'}/cc-bridge-test1.service.d/limits.conf (root, 644)",
                 f"+ write {tmp_path / 'systemd'}/claude-tab-test1.service.d/limits.conf (root, 644)",
                 f"+ write {tmp_path / 'systemd'}/brain.slice (root, 644)",
                 "+ append test1-cc and test1-hands to /etc/cron.deny and /etc/at.deny"):
        assert want in out, want
    assert out.index("== 4b host limits") < out.index("== 7 the member's bridge")    # the slice exists before the units


def test_add_member_limits_from_the_admins_shell(tmp_path):
    bins = tmp_path / "bin"
    r, _ = _add(tmp_path, "test1", "1", "--dry-run")
    env_r = subprocess.run(["bash", str(ROOT / "scripts" / "add-member.sh"), "test2", "2", "--dry-run"], capture_output=True,
                           text=True, env=_env(BRAINS_ROOT=str(tmp_path / "srv2"), SYSTEMD_DIR=str(tmp_path / "sd2"),
                                               PATH=f"{bins}:{os.environ['PATH']}", ADMIN_USER="hbar",
                                               BRAIN_REPO_URL="https://example.invalid/b.git",
                                               BRAIN_LIMIT_API_MEM="3g", BRAIN_LIMIT_JOBS="1"))
    assert env_r.returncode == 0, env_r.stderr
    assert "mem_limit: 3072m" in env_r.stdout and "CC_MAX_JOBS=1" in env_r.stdout
    bad = subprocess.run(["bash", str(ROOT / "scripts" / "add-member.sh"), "test3", "3", "--dry-run"], capture_output=True,
                         text=True, env=_env(BRAINS_ROOT=str(tmp_path / "srv3"), SYSTEMD_DIR=str(tmp_path / "sd3"),
                                             PATH=f"{bins}:{os.environ['PATH']}", ADMIN_USER="hbar",
                                             BRAIN_REPO_URL="https://example.invalid/b.git", BRAIN_LIMIT_API_MEM="huge"))
    assert bad.returncode != 0 and "limits" in bad.stderr


# ------------------------------------------------------------ the bridge ----
def _wait_ended(j, n=50):
    for _ in range(n):
        if all(r.get("ended") is not None for r in j.list()):
            return
        time.sleep(0.1)


def test_job_cap(tmp_path):
    j = X.Jobs(tmp_path / "out", lambda: {"PATH": "/usr/bin:/bin"}, max_running=2)
    a = j.start("sleep 5", None, "a")
    b = j.start("sleep 5", None, "b")
    assert a.get("id") and b.get("id")
    c = j.start("echo c", None, "c")
    assert "error" in c and "CC_MAX_JOBS=2" in c["error"]
    for r in (a, b):
        os.killpg(r["pid"], 15)
    _wait_ended(j)
    assert j.start("echo d", None, "d").get("id")                                  # room again once they end


def test_job_cap_from_env_and_default_none(tmp_path, monkeypatch):
    monkeypatch.delenv("CC_MAX_JOBS", raising=False)
    assert X.Jobs(tmp_path / "a", lambda: {}).max_running == 0                      # a brain alone: no cap, as before
    monkeypatch.setenv("CC_MAX_JOBS", "4")
    assert X.Jobs(tmp_path / "b", lambda: {}).max_running == 4
    monkeypatch.setenv("CC_MAX_JOBS", "many")
    assert X.Jobs(tmp_path / "c", lambda: {}).max_running == 1                      # unreadable: strictest


def test_admin_spend_ceiling(tmp_path, monkeypatch):
    monkeypatch.delenv("CC_SPEND_CAP_EUR", raising=False)
    led = S.Ledger(tmp_path)
    led.append("turn", "Anthropic", eur=8.0)
    assert led.admin_cap() is None and not led.over_cap() and not led.over_admin_cap()
    led.set_cap(50)
    monkeypatch.setenv("CC_SPEND_CAP_EUR", "5")
    assert led.limit() == 5 and led.over_cap() and led.over_admin_cap()           # the lower cap rules
    v = led.view()
    assert v["cap"] == 50 and v["admin_cap"] == 5 and v["over"] is True
    led.set_cap(2)
    assert led.limit() == 2                                                         # the owner may go lower, never higher
    monkeypatch.setenv("CC_SPEND_CAP_EUR", "0")
    assert led.admin_cap() is None


def test_bridge_refuses_jobs_over_the_admin_ceiling():
    src = (ROOT / "scripts" / "cc" / "cc-bridge.py").read_text()
    block = src.split('if route == "/jobs/start":', 1)[1].split("JOBS.start(", 1)[0]
    assert "SPEND.over_admin_cap()" in block and "self._send(409" in block


# ------------------------------------------- set-env.sh and the override mode (SEAT-1, 2026-11-08) ----
def _set_env(tmp_path, bridge_user, value):
    """scripts/cc/set-env.sh with sudo, systemctl, chown and curl faked; the env file sits where
    `~<bridge_user>` expands to for an unknown user (the literal path, relative to the cwd)."""
    bins = tmp_path / "fakebin"
    bins.mkdir(parents=True, exist_ok=True)
    for name, body in (("sudo", '[ "$1" = -u ] && shift 2; exec "$@"'), ("chown", "exit 0"),
                       ("systemctl", f'echo "$@" >> {tmp_path}/systemctl.log'), ("curl", "exit 7")):
        (bins / name).write_text(f"#!/bin/sh\n{body}\n")
        (bins / name).chmod(0o755)
    envf = tmp_path / f"~{bridge_user}" / ".cc-bridge" / "env"
    envf.parent.mkdir(parents=True, exist_ok=True)
    envf.write_text("OTHER=1\n")
    r = subprocess.run(["bash", str(ROOT / "scripts" / "cc" / "set-env.sh"), "CC_CODEX_WRITE"], input=value, cwd=tmp_path,
                       capture_output=True, text=True, timeout=30,
                       env={"PATH": f"{bins}:/usr/bin:/bin", "BRIDGE_USER": bridge_user, "HOME": str(tmp_path)})
    log = (tmp_path / "systemctl.log").read_text() if (tmp_path / "systemctl.log").exists() else ""
    return r, envf.read_text(), log


def test_set_env_takes_a_value_with_no_final_newline_and_restarts_the_members_bridge(tmp_path):
    r, text, log = _set_env(tmp_path, "nosuchmember-cc", "1")          # printf '1' | set-env.sh, as on 11-07
    assert r.returncode == 0, r.stderr
    assert "CC_CODEX_WRITE=1\n" in text and "OTHER=1\n" in text
    assert log.split() == ["restart", "cc-bridge-nosuchmember"]          # the member's unit, never the owner's
    assert "cc-bridge-nosuchmember restarted" in r.stdout
    r, text, _ = _set_env(tmp_path / "b", "nosuchmember-cc", "")
    assert r.returncode != 0 and "nothing given" in r.stdout and "CC_CODEX_WRITE" not in text


def test_add_member_writes_the_override_644():
    src = (ROOT / "scripts" / "add-member.sh").read_text()
    line = next(x for x in src.splitlines() if 'printf \'%s\\n\' "$OVERRIDE" > "$DIR/docker-compose.override.yml"' in x)
    assert "umask 022" in line and 'chmod 644 "$DIR/docker-compose.override.yml"' in line
