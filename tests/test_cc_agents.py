"""Standing agents (2026-10-17): scripts/cc/cc_agents.py."""
from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def ag(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("cc_agents", ROOT / "scripts" / "cc" / "cc_agents.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "AGENTS_DIR", tmp_path / "agents")
    return mod


BODY = {"name": "Disk watch", "mission": "Check disk and backups, propose fixes.", "ground": "/srv/x\n/srv/y/",
        "every_minutes": 60, "budget_usd": 1}


def test_create_and_list(ag):
    a = ag.create(BODY)
    assert a["id"] == "disk-watch" and a["ground"] == ["/srv/x", "/srv/y"] and a["enabled"]
    b = ag.create(BODY)
    assert b["id"] == "disk-watch-2"
    v = ag.view()
    assert [x["id"] for x in v["agents"]] == ["disk-watch", "disk-watch-2"]


@pytest.mark.parametrize("bad", [
    {"mission": "too short"},
    {"every_minutes": 5},
    {"budget_usd": 50},
    {"ground": "relative/path"},
    {"ground": "/"},
    {"ground": "/srv/app/.env"},
    {"model": "bad model; rm"},
    {"name": ""},
])
def test_validation_refuses(ag, bad):
    with pytest.raises(ValueError):
        ag.create({**BODY, **bad})


def test_due_and_schedule(ag):
    a = ag.create(BODY)
    assert ag.due(a)                                   # never ran: due at once
    a["last_run"] = ag.iso(1_000_000)
    assert not ag.due(a, 1_000_000 + 59 * 60)
    assert ag.due(a, 1_000_000 + 60 * 60)
    a["enabled"] = False
    assert not ag.due(a, 9e12)


def test_settings_scope_and_refusals(ag):
    a = ag.create(BODY)
    s = ag.settings(a)
    allow = s["permissions"]["allow"]
    assert "Edit(//srv/x/**)" in allow and "Edit(//srv/y/**)" in allow
    assert any(str(ag.AGENTS_DIR / "disk-watch").lstrip("/") in r for r in allow)
    deny = " ".join(s["permissions"]["deny"])
    assert "git push" in deny and "rm -rf" in deny and ".env" in deny
    assert "cc-permit-hook.py" in json.dumps(s["hooks"])


def test_prompt_and_command(ag, tmp_path):
    a = ag.create({**BODY, "model": "claude-sonnet-x"})
    p = ag.prompt(a, "2026-10-17T1200Z")
    assert BODY["mission"] in p and "sitreps/2026-10-17T1200Z.md" in p and "never push" in p
    cmd = ag.job_command(a, tmp_path / "p.md", tmp_path / "s.json")
    assert "--max-budget-usd 1.0" in cmd and "--model claude-sonnet-x" in cmd and "--add-dir /srv/x" in cmd


def test_tick_runs_due_records_job_and_caps(ag, monkeypatch):
    for i in range(5):
        ag.create({**BODY, "name": f"agent {i}"})
    seen = []
    started = ag.tick(opener=lambda a, cmd, cwd: (seen.append(a["id"]), f"J179{len(seen):07d}")[1])
    assert len(started) == ag.MAX_PER_TICK == len(seen)
    a = ag.load(started[0]["id"])
    assert a["last_job"].startswith("J179") and a["runs"] == 1 and a["last_run"]
    assert not ag.due(a)                               # ran: not due again until its schedule
    assert (ag.AGENTS_DIR / a["id"] / "prompt.md").exists()


def test_failed_start_is_recorded_not_retried_every_minute(ag):
    ag.create(BODY)

    def boom(a, cmd, cwd):
        raise RuntimeError("cc-job not found")
    a = ag.run("disk-watch", opener=boom)
    assert "cc-job not found" in a["last_error"] and a["runs"] == 0
    assert not ag.due(a)


def test_update_delete_and_sitrep(ag):
    ag.create(BODY)
    a = ag.update("disk-watch", {"enabled": False})
    assert a["enabled"] is False and a["mission"] == BODY["mission"]
    d = ag.sitrep_dir(a)
    (d / "2026-10-17T1200Z.md").write_text("SITREP disk-watch ok")
    assert "ok" in ag.last_sitrep(a)["text"]
    ag.delete("disk-watch")
    assert ag.view()["agents"] == [] and list((ag.AGENTS_DIR / ".trash").glob("disk-watch.*.json"))
    with pytest.raises(ValueError):
        ag.load("../etc/passwd")


def test_serials_never_reused_and_tag(ag):
    a = ag.create({**BODY, "callsign": "Sentinel", "post": "I Hands"})
    b = ag.create(BODY)
    assert (a["serial"], b["serial"]) == (1, 2)
    assert ag.tag(a) == 'A-001 "Sentinel"' and ag.tag(b) == "A-002"
    ag.delete(b["id"])
    c = ag.create(BODY)
    assert c["serial"] == 3                            # a retired number is never given again
    assert "A-001" in ag.prompt(a, "x") and "I Hands" in ag.prompt(a, "x")
    v = ag.view()
    assert [x["tag"] for x in v["agents"]] == ['A-001 "Sentinel"', "A-003"]


def test_callsign_and_post_validation(ag):
    with pytest.raises(ValueError):
        ag.create({**BODY, "callsign": "x" * 31})
    with pytest.raises(ValueError):
        ag.create({**BODY, "post": "bad<post>"})


def test_unattended_checks_allowed_but_no_post_or_branch_delete(ag):
    allow = ag.settings(ag.create(BODY))["permissions"]["allow"]
    assert "Bash(curl -s -o /dev/null *)" in allow and "WebFetch" in allow and "Bash(git worktree list)" in allow
    assert not any("curl -X" in a or "curl -d" in a or "branch -D" in a or a == "Bash(curl *)" for a in allow)
