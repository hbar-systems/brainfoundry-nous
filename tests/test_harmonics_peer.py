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
