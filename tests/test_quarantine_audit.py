"""
Tests for the quarantine-decision audit log (api/quarantine_audit.py). The log
path is redirected to a tmp file via QUARANTINE_AUDIT_PATH so no real runtime
volume is touched. Mirrors tests/test_federation_audit.py.
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _fresh_module(tmp_path, monkeypatch):
    monkeypatch.setenv("QUARANTINE_AUDIT_PATH", str(tmp_path / "q_audit.jsonl"))
    from api import quarantine_audit
    importlib.reload(quarantine_audit)
    return quarantine_audit


def test_record_and_tail_roundtrip(tmp_path, monkeypatch):
    qa = _fresh_module(tmp_path, monkeypatch)
    qa.record_decision(action="release", document_name="app-x.md", chunks=3,
                       new_tier="untrusted", injection_risk="high")
    qa.record_decision(action="delete", document_name="app-y.md", chunks=1,
                       new_tier=None, injection_risk="high")
    entries = qa.tail(50)
    assert len(entries) == 2
    rel, dele = entries  # newest last; insertion order preserved
    assert rel["action"] == "release" and rel["document_name"] == "app-x.md"
    assert rel["chunks"] == 3 and rel["new_tier"] == "untrusted"
    assert rel["injection_risk"] == "high" and rel["actor"] == "operator"
    assert dele["action"] == "delete" and dele["new_tier"] is None
    # ts is stamped automatically
    assert "ts" in rel and rel["ts"]


def test_tail_empty_when_no_file(tmp_path, monkeypatch):
    qa = _fresh_module(tmp_path, monkeypatch)
    assert qa.tail(10) == []


def test_actor_defaults_operator(tmp_path, monkeypatch):
    qa = _fresh_module(tmp_path, monkeypatch)
    qa.record_decision(action="release", document_name="d.md", chunks=1)
    assert qa.tail(1)[0]["actor"] == "operator"
