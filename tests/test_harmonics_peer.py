"""
Created 2026-10-25. record_event carries a peer's countersignature beside the row, and the
table migrates idempotently. No database: a fake connection records the SQL.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from api import harmonics as h
from api.identity.core import generate_brain_keypair


class _Cur:
    def __init__(self, log): self.log = log
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=None): self.log.append((sql, params))
    def fetchone(self): return (7,)


class _Conn:
    def __init__(self): self.log = []
    def cursor(self): return _Cur(self.log)


def test_record_event_stores_peer_fields(monkeypatch):
    monkeypatch.setenv("BRAIN_PRIVATE_KEY", generate_brain_keypair()[0])
    c = _Conn()
    rid = h.record_event(peer_pubkey="p", role="contributor", cos=0.6, sin=0.8, score=0.48,
                         content_hash="sha256:x", event_timestamp=5, peer_sig="S", peer_payload="{}", conn=c)
    assert rid == 7
    sql, params = c.log[0]
    assert "peer_sig" in sql and "peer_payload" in sql
    assert params[-2:] == ("S", "{}") and params[6].startswith("ed25519:")


def test_peer_fields_default_null_and_do_not_change_signature(monkeypatch):
    monkeypatch.setenv("BRAIN_PRIVATE_KEY", generate_brain_keypair()[0])
    a, b = _Conn(), _Conn()
    kw = dict(peer_pubkey="p", role="contributor", cos=0.6, sin=0.8, score=0.48,
              content_hash="sha256:x", event_timestamp=5)
    h.record_event(**kw, conn=a)
    h.record_event(**kw, peer_sig="S", peer_payload="{}", conn=b)
    assert a.log[0][1][-2:] == (None, None)
    assert a.log[0][1][6] == b.log[0][1][6]  # the brain's own signature does not cover the receipt


def test_migration_is_idempotent_ddl():
    assert h.COHERENCE_EVENTS_DDL.count("ADD COLUMN IF NOT EXISTS peer_sig") == 1
    assert "ADD COLUMN IF NOT EXISTS peer_payload" in h.COHERENCE_EVENTS_DDL
    c = _Conn()
    os.environ["DATABASE_URL"] = "postgres://x"
    try:
        h.init_tables(conn=c)
    finally:
        del os.environ["DATABASE_URL"]
    assert "peer_sig" in c.log[0][0]


# SEC-1 (2026-11-06): /harmonics/score with record=true wrote a contributor row without a key.
def _score_client(monkeypatch, recorded):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    monkeypatch.setenv("BRAIN_ENV", "production")
    monkeypatch.setenv("BRAIN_API_KEY", "k-" + "x" * 12)
    monkeypatch.setattr(h, "coherence", lambda c, r: (0.6, 0.8, 0.48))
    monkeypatch.setattr(h, "record_event", lambda **kw: recorded.append(kw) or 9)
    app = FastAPI()
    app.include_router(h.router)
    return TestClient(app)


def test_score_record_needs_operator_key(monkeypatch):
    recorded = []
    c = _score_client(monkeypatch, recorded)
    body = {"contribution": "c", "receiver_context": "r", "record": True}
    assert c.post("/harmonics/score", json=body).status_code == 401
    assert c.post("/harmonics/score", json=body, headers={"X-API-Key": "wrong"}).status_code == 401
    assert recorded == []
    r = c.post("/harmonics/score", json=body, headers={"X-API-Key": "k-" + "x" * 12})
    assert r.status_code == 200 and r.json()["event_id"] == 9 and len(recorded) == 1


def test_score_without_record_stays_open(monkeypatch):
    recorded = []
    c = _score_client(monkeypatch, recorded)
    r = c.post("/harmonics/score", json={"contribution": "c", "receiver_context": "r"})
    assert r.status_code == 200 and r.json()["event_id"] is None and recorded == []


# ── receiver context is public-scoped (audit 2026-11-13) ────────────────────

_CHUNKS = [
    ("PRIVATE open note", {}),
    ("TRASHED public", {"scope": "public", "deleted_at": "2026-11-01"}),
    ("QUARANTINED public", {"scope": "public", "quarantined": True}),
    ("LOCAL public", {"scope": "public", "privacy": "local-only"}),
    ("PUBLIC live", {"scope": "public"}),
]


class _ScopeCur:
    """Applies the WHERE clauses it recognises; an unrecognised filter set
    would leave private rows in, so a weakened query fails the test."""
    def __init__(self): self.sql = ""
    def __enter__(self): return self
    def __exit__(self, *a): return False

    def execute(self, sql, params=None):
        self.sql = sql
        rows = list(_CHUNKS)
        if "COALESCE(metadata->>'privacy', 'open') = 'open'" in sql:
            rows = [r for r in rows if r[1].get("privacy", "open") == "open"]
        if "metadata->>'scope' = 'public'" in sql:
            rows = [r for r in rows if r[1].get("scope") == "public"]
        if "metadata->>'deleted_at' IS NULL" in sql:
            rows = [r for r in rows if "deleted_at" not in r[1]]
        if "metadata->>'quarantined' IS NULL" in sql:
            rows = [r for r in rows if "quarantined" not in r[1]]
        self.rows = rows

    def fetchone(self):
        return (self.rows[0][0],) if self.rows else None


class _ScopeConn:
    def cursor(self): return _ScopeCur()


def _fake_model(monkeypatch):
    import types
    mod = types.ModuleType("api.embeddings.model")

    class _M:
        def encode(self, text, normalize_embeddings=True):
            return [0.0, 1.0]
    mod.get_model = lambda: _M()
    monkeypatch.setitem(sys.modules, "api.embeddings.model", mod)


def test_receiver_context_reads_only_public_live_chunks(monkeypatch):
    _fake_model(monkeypatch)
    assert h._receiver_context("anything", conn=_ScopeConn()) == "PUBLIC live"


def test_receiver_context_none_when_no_public_chunk(monkeypatch):
    _fake_model(monkeypatch)
    monkeypatch.setattr(sys.modules[__name__], "_CHUNKS", _CHUNKS[:4])
    assert h._receiver_context("PRIVATE open note", conn=_ScopeConn()) is None
