"""The kill switch (2026-10-25): scripts/cc/cc_halt.py, cc-job halt/resume, cc_agents refusal. No network.

Run from repo root:
    pytest tests/test_cc_halt.py -v
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "cc" / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


H = _load("cc_halt", "cc_halt.py")


def test_halt_file_set_read_clear(tmp_path):
    assert H.halted(tmp_path) is None
    assert H.set_halt(tmp_path, "  phone said so ", by="hbar") == "phone said so"
    assert H.halt_file(tmp_path) == tmp_path / ".cc-bridge" / "HALT"
    assert H.halted(tmp_path) == "HALT: phone said so"
    assert H.clear_halt(tmp_path, by="hbar") is True
    assert H.halted(tmp_path) is None
    assert H.clear_halt(tmp_path) is False
    lines = (tmp_path / ".cc-bridge" / "halt.log").read_text().splitlines()
    assert len(lines) == 3 and "halt by hbar: phone said so" in lines[0] and "resume by hbar: cleared" in lines[1]


def test_empty_reason_is_still_a_halt(tmp_path):
    (tmp_path / ".cc-bridge").mkdir()
    (tmp_path / ".cc-bridge" / "HALT").write_text("")
    assert H.halted(tmp_path) == "HALT: halted"


def test_budget_tolerant(tmp_path):
    assert H.budget_halts("") == {} and H.budget_halts(tmp_path) == {}
    f = tmp_path / "ops" / "finance" / "budgets.tsv"
    f.parent.mkdir(parents=True)
    f.write_text("post\tcap_eur\n" "media\t20\n")            # no state column
    assert H.budget_halts(tmp_path) == {}
    f.write_text("# weekly caps\n" "post\tcap_eur\tstate\n" "media\t20\tHALT-media\n" "research\t10\tok\n" "legal\t5\tHALT\n" "short\n")
    assert H.budget_halts(tmp_path) == {"media": "HALT-media", "legal": "HALT"}
    assert H.budget_refusal("Media: render the loop", tmp_path).startswith("HALT: budget for media is spent this week")
    assert H.budget_refusal("research: read papers", tmp_path) is None
    assert H.budget_refusal("mediaX: not that post", tmp_path) is None
    assert H.budget_refusal("", tmp_path) is None


def test_refusal_order(tmp_path):
    f = tmp_path / "ops" / "finance" / "budgets.tsv"
    f.parent.mkdir(parents=True)
    f.write_text("post\tstate\nmedia\tHALT-media\n")
    assert H.refusal(tmp_path, tmp_path, "media: x") == "HALT: budget for media is spent this week (HALT-media in ops/finance/budgets.tsv)"
    assert H.refusal(tmp_path, tmp_path, "other: x") is None
    H.set_halt(tmp_path, "stop")
    assert H.refusal(tmp_path, tmp_path, "other: x") == "HALT: stop"


def test_kill_jobs_signals_running_groups_only(tmp_path, monkeypatch):
    reg = tmp_path / "jobs.json"
    reg.write_text(json.dumps([
        {"id": "J1", "pid": 101, "started": 1000, "ended": None},
        {"id": "J2", "pid": 102, "started": 1000, "ended": 2000},          # finished
        {"id": "J3", "pid": 103, "started": 1000, "ended": None},          # pid reused later
        {"id": "J4", "pid": 104, "started": 1000, "ended": None},          # not ours (root's sudo alone)
        {"id": "J5", "pid": 105, "started": 1000, "ended": None},          # gone
    ]))
    monkeypatch.setattr(H, "_proc_start", lambda pid: {103: 5000.0}.get(pid, 1001.0))
    sent = []
    def killer(pid, sig):
        if pid == 104:
            raise PermissionError
        if pid == 105:
            raise ProcessLookupError
        sent.append((pid, sig))
    assert H.kill_jobs(reg, killer=killer) == ["J1"]
    assert sent == [(101, H.signal.SIGTERM)]
    assert H.kill_jobs(tmp_path / "missing.json", killer=killer) == []


def test_cc_agents_refuses_while_halted(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    ag = _load("cc_agents_halt_test", "cc_agents.py")
    monkeypatch.setattr(ag, "AGENTS_DIR", tmp_path / "agents")
    assert ag.main(["cc_agents.py", "tick"]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1]) == {"ok": True, "started": []}
    H.set_halt(tmp_path, "paused from the phone")
    assert ag.main(["cc_agents.py", "tick"]) == 1
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["ok"] is False and out["error"] == "HALT: paused from the phone"
    assert ag.main(["cc_agents.py", "run", "any"]) == 1


def test_cc_job_halt_resume_status(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USER", "hands")
    monkeypatch.setenv("CC_WORLD_DIR", str(tmp_path / "world"))
    job = _load("cc_job", "cc-job.py")
    monkeypatch.setattr(job, "HANDS_HOME", tmp_path)
    assert job.main(["halt", "--status"]) == 0
    assert "not halted" in capsys.readouterr().out
    assert job.main(["halt", "testing the switch"]) == 0
    assert "HALT: testing the switch" in capsys.readouterr().out
    assert (tmp_path / ".cc-bridge" / "HALT").read_text().splitlines()[0] == "testing the switch"
    assert job.main(["halt", "--status"]) == 3
    out = capsys.readouterr().out
    assert "HALT: testing the switch" in out and "budget halts: none" in out and "running jobs: 0" in out
    # run is refused by the bridge; cc-job prints the HALT line as it came
    monkeypatch.setattr(job, "_call", lambda *a, **k: {"error": "HALT: testing the switch"})
    assert job.main(["run", "-t", "x", "--", "echo hi"]) == 1
    assert capsys.readouterr().out.strip() == "HALT: testing the switch"
    # --kill with nothing running
    assert job.main(["halt", "again", "--kill"]) == 0
    assert "none were running" in capsys.readouterr().out
    assert job.main(["resume"]) == 0
    assert "resumed" in capsys.readouterr().out
    assert not (tmp_path / ".cc-bridge" / "HALT").exists()
    log = (tmp_path / ".cc-bridge" / "halt.log").read_text()
    assert "halt by hands: testing the switch" in log and "kill by hands: no running jobs" in log and "resume by hands: cleared" in log
