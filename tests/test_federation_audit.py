"""
Tests for the cross-brain federation audit log (api/tools/federation_audit.py).
The log path is redirected to a tmp file via FEDERATION_AUDIT_PATH so no real
runtime volume is touched.
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _fresh_module(tmp_path, monkeypatch):
    monkeypatch.setenv("FEDERATION_AUDIT_PATH", str(tmp_path / "fed_audit.jsonl"))
    from api.tools import federation_audit
    importlib.reload(federation_audit)
    return federation_audit


def test_record_and_tail_roundtrip(tmp_path, monkeypatch):
    fa = _fresh_module(tmp_path, monkeypatch)
    fa.record_event(direction="out", peer_brain_id="hbar-university",
                    query="what is bayes", documents_used=3, answer_len=120,
                    verified=True, outcome="ok")
    fa.record_event(direction="in", peer_brain_id="anonymous",
                    query="hello", documents_used=0, answer_len=40,
                    verified=False, outcome="ok")
    entries = fa.tail(50)
    assert len(entries) == 2
    out, inn = entries  # newest last; insertion order preserved
    assert out["direction"] == "out" and out["peer_brain_id"] == "hbar-university"
    assert out["verified"] is True and out["trust"] == "peer"
    assert out["query_summary"] == "what is bayes"
    assert inn["direction"] == "in" and inn["trust"] == "anonymous"
    # ts is stamped automatically
    assert "ts" in out and out["ts"]


def test_query_summary_truncated(tmp_path, monkeypatch):
    fa = _fresh_module(tmp_path, monkeypatch)
    fa.record_event(direction="in", peer_brain_id="p", query="x" * 1000, outcome="ok")
    assert len(fa.tail(1)[0]["query_summary"]) == 200


def test_tail_empty_when_no_file(tmp_path, monkeypatch):
    fa = _fresh_module(tmp_path, monkeypatch)
    assert fa.tail(10) == []


def test_outcome_recorded(tmp_path, monkeypatch):
    fa = _fresh_module(tmp_path, monkeypatch)
    fa.record_event(direction="out", peer_brain_id="p", outcome="budget_exceeded")
    assert fa.tail(1)[0]["outcome"] == "budget_exceeded"
