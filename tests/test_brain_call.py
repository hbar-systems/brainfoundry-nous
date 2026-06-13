"""
Tests for the federation brain_call tool (api/tools/brain_call.py). The peer
directory and the HTTP query are both monkeypatched, so no file/network is
touched — we exercise the lookup, the unknown-peer guard, and the attributed
untrusted-wrapping of a peer's answer.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api import tools  # noqa: E402
from api.tools import brain_call  # noqa: E402
from api.tools import ToolResult  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _fake_peers(monkeypatch, peers):
    monkeypatch.setattr(brain_call, "callable_peers", lambda: peers)


def test_registered_yellow():
    t = tools.get("brain_call")
    assert t is not None and t.tier == tools.YELLOW


def test_empty_query():
    r = _run(brain_call.run("hbar-university", ""))
    assert r.ok is False and "empty query" in r.error


def test_unknown_peer_lists_known(monkeypatch):
    _fake_peers(monkeypatch, [{"brain_id": "hbar-university", "endpoint": "https://u"}])
    r = _run(brain_call.run("nope", "what is bayes"))
    assert r.ok is False
    assert "unknown peer 'nope'" in r.error
    assert "hbar-university" in r.error


def test_successful_call_attributes_and_wraps(monkeypatch):
    _fake_peers(monkeypatch, [{"brain_id": "hbar-university", "endpoint": "https://u"}])

    async def fake_query(endpoint, query, assertion=None):
        assert endpoint == "https://u" and query == "what is bayes"
        return {"brain_id": "hbar-university", "answer": "Bayes' theorem relates...", "documents_used": 3}

    monkeypatch.setattr(brain_call, "_query_peer", fake_query)
    r = _run(brain_call.run("hbar-university", "what is bayes"))
    assert r.ok is True
    # Attributed to the peer, and framed as a non-owner reference.
    assert "hbar-university" in r.content
    assert "not your owner" in r.content
    assert "Bayes' theorem relates" in r.content
    # Provenance points at the peer brain.
    assert r.provenance[0]["tool"] == "brain_call"
    assert r.provenance[0]["title"].startswith("hbar-university")
    assert r.meta["documents_used"] == 3


def test_empty_answer_is_error(monkeypatch):
    _fake_peers(monkeypatch, [{"brain_id": "p", "endpoint": "https://p"}])

    async def fake_query(endpoint, query, assertion=None):
        return {"brain_id": "p", "answer": "   "}

    monkeypatch.setattr(brain_call, "_query_peer", fake_query)
    r = _run(brain_call.run("p", "q"))
    assert r.ok is False and "no answer" in r.error


def test_transport_failure_is_clean_error(monkeypatch):
    _fake_peers(monkeypatch, [{"brain_id": "p", "endpoint": "https://p"}])

    async def boom(endpoint, query, assertion=None):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(brain_call, "_query_peer", boom)
    r = _run(brain_call.run("p", "q"))
    assert r.ok is False and "failed" in r.error and "connection refused" in r.error


def test_per_peer_budget_refusal(monkeypatch):
    """A peer over its monthly budget is refused before any network call, with a
    clear message — and the network is never touched."""
    from api.tools import budget
    _fake_peers(monkeypatch, [{"brain_id": "p", "endpoint": "https://p"}])
    monkeypatch.setattr(budget, "under_cap", lambda key: False)
    monkeypatch.setattr(budget, "cap", lambda key: 500)

    called = {"hit": False}
    async def fake_query(endpoint, query, assertion=None):
        called["hit"] = True
        return {"brain_id": "p", "answer": "should not run"}

    monkeypatch.setattr(brain_call, "_query_peer", fake_query)
    r = _run(brain_call.run("p", "q"))
    assert r.ok is False
    assert "budget" in r.error and "500" in r.error
    assert called["hit"] is False  # refused before the round-trip


def test_per_peer_budget_keyed_by_target(monkeypatch):
    """The budget is checked/recorded per peer (brain_call:<id>), not globally."""
    from api.tools import budget
    _fake_peers(monkeypatch, [{"brain_id": "u", "endpoint": "https://u"}])
    seen = {}
    monkeypatch.setattr(budget, "under_cap", lambda key: seen.setdefault("under", key) or True)
    monkeypatch.setattr(budget, "record", lambda key: seen.setdefault("record", key))

    async def fake_query(endpoint, query, assertion=None):
        return {"brain_id": "u", "answer": "ok", "documents_used": 1}

    monkeypatch.setattr(brain_call, "_query_peer", fake_query)
    r = _run(brain_call.run("u", "q"))
    assert r.ok is True
    assert seen["under"] == "brain_call:u"
    assert seen["record"] == "brain_call:u"
