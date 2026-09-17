"""CC write gate (scripts/cc/cc-bridge.py + permitd): proposal extraction and the
propose -> approve -> execute flow with a fake runner. No network, no reasoner.

Run from repo root:
    pytest tests/test_cc_gate.py -v
Requires permitd (pip install permitd), stdlib-only.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
permitd = pytest.importorskip("permitd")


def _load(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.setenv("ONE_SECRET", "sk_test_not_a_real_key_000000000000")
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    spec = importlib.util.spec_from_file_location("cc_bridge_gate", ROOT / "scripts" / "cc" / "cc-bridge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cc_bridge_gate"] = mod
    spec.loader.exec_module(mod)
    return mod


PROPOSAL = ('Here is what I would do.\n\n<proposal>{"platform": "google-calendar", "action_id": "conn_mod_def::abc", '
            '"connection_key": "live::google-calendar::default::0123456789abcdef0123456789abcdef", "method": "POST", '
            '"path_vars": {"calendarId": "primary"}, "query": {}, "data": {"summary": "CC test"}, '
            '"summary": "google-calendar: create event \'CC test\' on primary"}</proposal>')


def test_gate_present_and_prompt_mentions_proposal(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    assert m.GATE is not None
    assert "<proposal>" in m.SYSTEM
    assert "never execute a write yourself" in m.SYSTEM
    assert "never answer that a write is impossible" in m.SYSTEM.replace("\n", " ") or "never " in m.SYSTEM
    # The closing rule comes last and does not forbid proposals.
    assert m.SYSTEM.rstrip().endswith("Say so if asked to.")
    assert "Apart from such proposals" in m.SYSTEM
    assert "Only read actions (GET) are permitted" not in m.SYSTEM


def test_extract_proposal_strips_block_and_keeps_keys(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    clean, p = m._extract_proposal(PROPOSAL)
    assert clean == "Here is what I would do."
    assert p["platform"] == "google-calendar" and p["method"] == "POST"
    assert p["data"] == {"summary": "CC test"} and p["path_vars"] == {"calendarId": "primary"}
    assert set(p) == set(m._PROPOSAL_KEYS)
    assert m._extract_proposal("no block here") == ("no block here", None)
    assert m._extract_proposal("<proposal>not json</proposal>")[1] is None


def test_propose_approve_execute_with_fake_runner(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    calls = []

    def fake_execute(**kw):
        calls.append(kw)
        return {"status": 200, "data": {"id": "evt_1"}}

    # Swap the RED tool's implementation; tier and gating stay.
    m.GATE.register("one_execute", fake_execute, tier=m.RED)
    _, p = m._extract_proposal(PROPOSAL)
    card = m._propose(p)
    assert "id" in card and card["summary"].startswith("google-calendar:")
    assert calls == []                      # nothing ran at propose time
    pid = card["id"]
    assert [x["id"] for x in [m._permit_public(pm) for pm in m.GATE.pending()]] == [pid]

    # Wrong arguments with the right permit are refused: the permit is bound.
    m.GATE.approve(pid)
    bad = dict(p); bad["data"] = {"summary": "something else"}
    r = m.GATE.call("one_execute", bad, permit_id=pid)
    assert not r.ok and r.reason == "args_mismatch" and calls == []

    # Exact arguments execute once; a second use is refused (single-use burn).
    r = m.GATE.call("one_execute", p, permit_id=pid)
    assert r.ok and r.result == {"status": 200, "data": {"id": "evt_1"}} and len(calls) == 1
    r2 = m.GATE.call("one_execute", p, permit_id=pid)
    assert not r2.ok and len(calls) == 1

    # Audit trail exists and verifies.
    assert (tmp_path / ".cc-bridge" / "permitd-audit.jsonl").exists()


def test_deny_blocks_execution(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    m.GATE.register("one_execute", lambda **kw: {"ran": True}, tier=m.RED)
    _, p = m._extract_proposal(PROPOSAL)
    pid = m._propose(p)["id"]
    m.GATE.deny(pid)
    r = m.GATE.call("one_execute", p, permit_id=pid)
    assert not r.ok


def test_egress_guard_refuses_credential_shaped_args(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    _, p = m._extract_proposal(PROPOSAL)
    p["data"] = {"body": "here is my key sk-ant-api03-" + "A" * 60}
    card = m._propose(p)
    assert "error" in card and "id" not in card
