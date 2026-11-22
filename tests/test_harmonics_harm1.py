"""
Created 2026-11-15 (HARM-1). The bilateral exchange between hbar's own brains:
pinned-peer resolution, self-exchange and nonce-replay refusal, the receiver's receipt
verified by the contributor, and a ring replay of E8's collusion pattern against the
real standing() with the scores measured live on 2026-11-15. No database, no network.
"""
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi import HTTPException

from api import harmonics as h
from api.identity.core import generate_brain_keypair
from api.identity import replay_cache


def _keys():
    priv, pub = generate_brain_keypair()
    return priv, pub


class _Resp:
    def __init__(self, code, data): self.status_code, self._d, self.text = code, data, json.dumps(data)
    def json(self): return self._d


class _Client:
    """httpx.Client stand-in: GET /identity and POST /harmonics/exchange."""
    calls = []
    identity = {}
    exchange = None
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get(self, url):
        _Client.calls.append(("GET", url))
        return _Resp(200, _Client.identity)
    def post(self, url, json=None):
        _Client.calls.append(("POST", url))
        return _Resp(200, _Client.exchange(json))


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    replay_cache.clear()
    _Client.calls = []
    monkeypatch.setattr(h.httpx, "Client", _Client)
    yield


def test_pinned_peer_uses_pinned_endpoint_not_brainfoundry(monkeypatch):
    _, pub = _keys()
    monkeypatch.setattr(h, "_pinned_peer", lambda handle: {
        "brain_id": "hbar-health", "endpoint": "https://brain.hbar.health/", "public_key": pub})
    _Client.identity = {"public_key": pub}
    key, ep = h._fetch_peer("hbar-health")
    assert (key, ep) == (pub, "https://brain.hbar.health")
    assert _Client.calls == [("GET", "https://brain.hbar.health/identity")]


def test_pinned_peer_key_mismatch_refused(monkeypatch):
    _, pub = _keys()
    _, other = _keys()
    monkeypatch.setattr(h, "_pinned_peer", lambda handle: {
        "brain_id": "nous", "endpoint": "https://api.nous.brainfoundry.ai", "public_key": pub})
    _Client.identity = {"public_key": other}
    with pytest.raises(HTTPException) as e:
        h._fetch_peer("nous")
    assert "pin" in e.value.detail


def test_unpinned_handle_keeps_one_label_rule(monkeypatch):
    monkeypatch.setattr(h, "_pinned_peer", lambda handle: None)
    _Client.identity = {"public_key": "k"}
    assert h._fetch_peer("hbar")[1] == "https://hbar.brainfoundry.ai"
    with pytest.raises(HTTPException):
        h._fetch_peer("evil.example/?")


def _signed_request(priv, pub, text="c", nonce="n1"):
    payload = {"from_brain": "a", "from_pubkey": pub, "contribution": text,
               "ts": int(time.time()), "nonce": nonce}
    prior = os.environ.get("BRAIN_PRIVATE_KEY")
    os.environ["BRAIN_PRIVATE_KEY"] = priv
    try:
        sig = h.sign_with_brain_key(payload)
    finally:
        if prior is None:
            del os.environ["BRAIN_PRIVATE_KEY"]
        else:
            os.environ["BRAIN_PRIVATE_KEY"] = prior
    return h.ExchangeRequest(**payload, signature=sig)


@pytest.fixture
def receiver(monkeypatch):
    rpriv, rpub = _keys()
    monkeypatch.setenv("BRAIN_PRIVATE_KEY", rpriv)
    monkeypatch.setenv("BRAIN_PUBLIC_KEY", rpub)
    rows = []
    monkeypatch.setattr(h, "_receiver_context", lambda c: "R")
    monkeypatch.setattr(h, "coherence", lambda c, r: (0.8, 0.6, 0.48))
    monkeypatch.setattr(h, "record_event", lambda **kw: rows.append(kw) or len(rows))
    # HARM-2: the v2 receiver also judges, checks novelty and the pair's day count.
    monkeypatch.setattr(h, "judge", lambda c, need, held=None: (0.48, "fits", "test-judge"))
    monkeypatch.setattr(h, "global_overlap", lambda text, own, excl: (own, []))
    monkeypatch.setattr(h, "_pair_events_today", lambda pub: 0)
    h._day_counts.clear()
    return rpriv, rpub, rows


def test_exchange_refuses_replayed_nonce(receiver):
    cpriv, cpub = _keys()
    req = _signed_request(cpriv, cpub)
    assert h.harmonics_exchange(req)["recorded"] is True
    with pytest.raises(HTTPException) as e:
        h.harmonics_exchange(req)
    assert e.value.status_code == 409
    assert len(receiver[2]) == 1


def test_exchange_refuses_self(receiver):
    rpriv, rpub, rows = receiver
    with pytest.raises(HTTPException) as e:
        h.harmonics_exchange(_signed_request(rpriv, rpub))
    assert e.value.status_code == 400 and rows == []


def test_exchange_receipt_verifies_against_receiver_key(receiver):
    rpriv, rpub, rows = receiver
    cpriv, cpub = _keys()
    out = h.harmonics_exchange(_signed_request(cpriv, cpub))
    rp = h._receiver_payload(contributor_pubkey=cpub, cos=0.8, sin=0.6, score=0.48,
                             content_hash=out["content_hash"], event_timestamp=out["event_timestamp"],
                             judge_reason="fits", judge_model="test-judge", novelty=1.0)
    assert h.verify_with_pubkey(rpub, out["receiver_sig"], rp)


def _contributor_env(monkeypatch):
    cpriv, cpub = _keys()
    monkeypatch.setenv("BRAIN_PRIVATE_KEY", cpriv)
    monkeypatch.setenv("BRAIN_PUBLIC_KEY", cpub)
    monkeypatch.setenv("BRAIN_ID", "hbar")
    return cpriv, cpub


def _fake_receiver(rpriv, cpub, tamper=False):
    def ex(body):
        rp = h._receiver_payload(contributor_pubkey=cpub, cos=0.8, sin=0.6, score=0.48,
                                 content_hash="sha256:x", event_timestamp=body["ts"],
                                 judge_reason="fits", judge_model="test-judge", novelty=1.0)
        os.environ["_K"] = os.environ["BRAIN_PRIVATE_KEY"]
        os.environ["BRAIN_PRIVATE_KEY"] = rpriv
        try:
            sig = h.sign_with_brain_key(rp)
        finally:
            os.environ["BRAIN_PRIVATE_KEY"] = os.environ.pop("_K")
        return {"recorded": True, "event_id": 1, "cos": 0.8, "sin": 0.6,
                "score": 0.5 if tamper else 0.48, "content_hash": "sha256:x",
                "event_timestamp": body["ts"], "receiver_sig": sig,
                "v": 2, "judge_reason": "fits", "judge_model": "test-judge", "novelty": 1.0}
    return ex


def test_contribute_verifies_and_stores_receipt(monkeypatch):
    _, cpub = _contributor_env(monkeypatch)
    rpriv, rpub = _keys()
    monkeypatch.setattr(h, "_pinned_peer", lambda handle: {
        "brain_id": "hbar-health", "endpoint": "https://brain.hbar.health", "public_key": rpub})
    _Client.identity = {"public_key": rpub}
    _Client.exchange = _fake_receiver(rpriv, cpub)
    rows = []
    monkeypatch.setattr(h, "record_event", lambda **kw: rows.append(kw) or 9)
    out = h.harmonics_contribute(h.ContributeRequest(to="hbar-health", contribution="c"), _auth="k")
    assert out["receipt_verified"] is True and rows[0]["peer_sig"].startswith("ed25519:")
    assert json.loads(rows[0]["peer_payload"])["role"] == "receiver"
    assert ("POST", "https://brain.hbar.health/harmonics/exchange") in _Client.calls


def test_contribute_refuses_tampered_receipt(monkeypatch):
    _, cpub = _contributor_env(monkeypatch)
    rpriv, rpub = _keys()
    monkeypatch.setattr(h, "_pinned_peer", lambda handle: None)
    _Client.identity = {"public_key": rpub}
    _Client.exchange = _fake_receiver(rpriv, cpub, tamper=True)
    monkeypatch.setattr(h, "record_event", lambda **kw: pytest.fail("must not record"))
    with pytest.raises(HTTPException) as e:
        h.harmonics_contribute(h.ContributeRequest(to="nous", contribution="c"), _auth="k")
    assert "receipt" in e.value.detail


def test_contribute_refuses_self(monkeypatch):
    _contributor_env(monkeypatch)
    with pytest.raises(HTTPException) as e:
        h.harmonics_contribute(h.ContributeRequest(to="hbar", contribution="c"), _auth="k")
    assert e.value.status_code == 400


# ─── Ring replay (E8 collusion pattern) on the real standing() ──────────────
# Scores measured live on 2026-11-15 at brain.hbar.university / brain.hbar.health
# (hbar.world ops/2026-11-15_harm-1/results.jsonl).
USEFUL_MEAN = 0.473689  # mean of the 10 useful contributions
JUNK = 0.468226         # control C3, "qwz 8812 lorem ..."
UNRELATED = 0.421586    # control C1, sourdough recipe


class _RowsConn:
    def __init__(self, rows): self.rows = rows
    def cursor(self):
        rows = self.rows
        class C:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def execute(s, *a): pass
            def fetchall(s): return [(sc, ts) for sc, ts in rows]
        return C()


def _standing(per_day, score, days=90, now=None):
    """v0 standing as it ran on 2026-11-15 (every contributor row summed, decayed).
    HARM-2 replaced standing(); the v0 formula is kept here so this test still
    records what HARM-1 found."""
    import math
    now = now or days * 86400.0
    rows = [(score, d * 86400.0) for d in range(days) for _ in range(per_day)]
    return sum(s * math.exp(-math.log(2) * (now - ts) / 86400.0 / h.HALF_LIFE_DAYS)
               for s, ts in rows)


def test_ring_still_farms_standing_under_v0():
    honest = _standing(1, USEFUL_MEAN)
    ring_member = _standing(10, JUNK)       # each of A and B: 10 junk events a day to the other
    assert ring_member / honest > 9.0       # volume wins; content quality does not matter
    assert _standing(1, JUNK) / honest > 0.98   # even one junk a day is 99% of honest
    assert _standing(1, UNRELATED) / honest > 0.88
