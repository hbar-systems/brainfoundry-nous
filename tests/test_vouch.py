"""
Owner vouch: the newcomer on-ramp through the substrate floor (2026-11-01).

Pins: a vouched, pinned peer that fails the floor passes on the ask door and on
the handshake verify, marked trust "vouched"; unvouched, expired and withdrawn
peers are refused as before; a vouch needs an introduced peer with a pinned key;
1..90 days only; every vouch and withdrawal leaves an audit line. Reuses the ask
door's in-process fixture (no network, no database, no model).
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from api import substrate
from api.identity.core import issue_federation_assertion
from tests.test_ask import PEER, PEER_PRIV, PEER_PUB, THIS, _ask, env  # noqa: F401

AUTH = {"X-API-Key": "test-api-key"}


@pytest.fixture
def gated(env, monkeypatch):  # noqa: F811
    from api import main as m
    monkeypatch.setenv("FEDERATION_SUBSTRATE_GATE", "on")
    monkeypatch.setattr(m, "BRAIN_API_KEY", AUTH["X-API-Key"])
    calls = []

    async def floor(**kw):
        calls.append(kw)
        return substrate.FloorResult(ok=False, code="substrate_floor_not_met",
                                     details={"artifact_count": {"got": 0, "required": 50}})
    monkeypatch.setattr(substrate, "fetch_and_check_peer", floor)
    env.floor_calls = calls
    return env


def _peers(env):
    from api import hbar_commands
    return json.loads(hbar_commands._PEERS_PATH.read_text())


def _audit(env):
    p = env.audit.FEDERATION_AUDIT_PATH
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def _vouch(env, days=30, who=PEER):
    return env.client.post(f"/v1/federation/peers/{who}/vouch", json={"days": days}, headers=AUTH)


# ── helper ──────────────────────────────────────────────────────────────────

def test_vouch_active_rules():
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    assert substrate.vouch_active({"public_key": "k", "vouched_until": future})
    assert not substrate.vouch_active({"public_key": "k", "vouched_until": past})
    assert not substrate.vouch_active({"vouched_until": future})            # no pinned key
    assert not substrate.vouch_active({"public_key": "k"})                  # no vouch
    assert not substrate.vouch_active({"public_key": "k", "vouched_until": "soon"})
    assert not substrate.vouch_active({"public_key": "k", "vouched_until": "2099-01-01T00:00:00"})  # naive
    assert not substrate.vouch_active(None)


# ── ask door ────────────────────────────────────────────────────────────────

def test_unvouched_newcomer_refused_as_before(gated):
    r = _ask(gated)
    assert r.status_code == 403 and "degraded_peer" in r.json()["error"]["message"]


def test_vouched_newcomer_answered_and_marked(gated):
    assert _vouch(gated).status_code == 200
    r = _ask(gated)
    assert r.status_code == 200, r.text
    asks = [e for e in _audit(gated) if e.get("surface") == "ask"]
    assert asks[-1]["trust"] == "vouched" and asks[-1]["outcome"] == "ok"


def test_expired_vouch_refused(gated):
    from api import hbar_commands
    peers = _peers(gated)
    peers[0]["vouched_until"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    hbar_commands._PEERS_PATH.write_text(json.dumps(peers))
    assert _ask(gated).status_code == 403


def test_withdrawn_vouch_refused(gated):
    _vouch(gated)
    r = gated.client.delete(f"/v1/federation/peers/{PEER}/vouch", headers=AUTH)
    assert r.status_code == 200 and "vouched_until" not in _peers(gated)[0]
    assert _ask(gated).status_code == 403
    outcomes = [e["outcome"] for e in _audit(gated) if e.get("surface") == "peers"]
    assert outcomes == ["vouch:30d", "unvouch"]


def test_floor_passing_peer_unaffected(gated, monkeypatch):
    async def ok(**kw):
        return substrate.FloorResult(ok=True, code=None, details={})
    monkeypatch.setattr(substrate, "fetch_and_check_peer", ok)
    assert _ask(gated).status_code == 200
    assert [e for e in _audit(gated) if e.get("surface") == "ask"][-1]["trust"] == "peer"


# ── vouch endpoints ─────────────────────────────────────────────────────────

def test_vouch_needs_operator_key(gated):
    r = gated.client.post(f"/v1/federation/peers/{PEER}/vouch", json={"days": 30})
    assert r.status_code in (401, 403)
    assert "vouched_until" not in _peers(gated)[0]


def test_vouch_bounds(gated):
    assert _vouch(gated, days=0).status_code == 400
    assert _vouch(gated, days=91).status_code == 400
    r = _vouch(gated, days=90)
    assert r.status_code == 200
    until = datetime.fromisoformat(r.json()["vouched_until"].replace("Z", "+00:00"))
    assert timedelta(days=89, hours=23) < until - datetime.now(timezone.utc) <= timedelta(days=90)


def test_vouch_unknown_or_unpinned_refused(gated):
    from api import hbar_commands
    assert _vouch(gated, who="nobody").status_code == 404
    hbar_commands._PEERS_PATH.write_text(json.dumps(
        [{"brain_id": "nokey", "endpoint": "https://n.example"}]))
    assert _vouch(gated, who="nokey").status_code == 409


def test_listing_shows_vouch(gated):
    _vouch(gated, days=7)
    peers = gated.client.get("/v1/federation/peers", headers=AUTH).json()["peers"]
    assert peers[0]["vouched_until"]


# ── handshake verify (/v1/federation/assertion) ─────────────────────────────

def _assertion(gated, tmp_path, monkeypatch):
    toml = tmp_path / "known.toml"
    toml.write_text(f'[[peer]]\nbrain_id = "{PEER}"\nendpoint = "https://a.example"\n'
                    f'public_key = "{PEER_PUB}"\n')
    monkeypatch.setenv("BRAIN_KNOWN_PEERS_PATH", str(toml))
    token = issue_federation_assertion(private_key_b64=PEER_PRIV, issuer_brain_id=PEER,
                                       audience_brain_id=THIS, subject="handshake", ttl_seconds=120)
    return gated.client.post("/v1/federation/assertion",
                             json={"token": token, "issuer_endpoint": "https://a.example"})


def test_handshake_refused_without_vouch(gated, tmp_path, monkeypatch):
    r = _assertion(gated, tmp_path, monkeypatch)
    assert r.status_code == 403 and r.json()["code"] == "substrate_floor_not_met"


def test_handshake_passes_on_vouch(gated, tmp_path, monkeypatch):
    _vouch(gated)
    r = _assertion(gated, tmp_path, monkeypatch)
    assert r.status_code == 200, r.text
    assert r.json()["verified"] is True and r.json()["trust"] == "vouched"


def test_handshake_vouch_leaves_audit_line(gated, tmp_path, monkeypatch):
    _vouch(gated)
    _assertion(gated, tmp_path, monkeypatch)
    lines = [e for e in _audit(gated) if e.get("surface") == "assertion"]
    assert lines and lines[-1]["trust"] == "vouched" and lines[-1]["peer_brain_id"] == PEER


def test_handshake_expired_vouch_refused(gated, tmp_path, monkeypatch):
    from api import hbar_commands
    peers = _peers(gated)
    peers[0]["vouched_until"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    hbar_commands._PEERS_PATH.write_text(json.dumps(peers))
    assert _assertion(gated, tmp_path, monkeypatch).status_code == 403


def test_vouch_bound_to_the_vouched_key(gated, tmp_path, monkeypatch):
    # The owner vouched for brain-a pinned to key A (peers.json); a known_peers
    # entry with the same name but another key must not ride on that vouch.
    from api.identity.core import generate_brain_keypair
    _vouch(gated)
    other_priv, other_pub = generate_brain_keypair()
    toml = tmp_path / "known.toml"
    toml.write_text(f'[[peer]]\nbrain_id = "{PEER}"\nendpoint = "https://evil.example"\n'
                    f'public_key = "{other_pub}"\n')
    monkeypatch.setenv("BRAIN_KNOWN_PEERS_PATH", str(toml))
    token = issue_federation_assertion(private_key_b64=other_priv, issuer_brain_id=PEER,
                                       audience_brain_id=THIS, subject="handshake", ttl_seconds=120)
    r = gated.client.post("/v1/federation/assertion",
                          json={"token": token, "issuer_endpoint": "https://evil.example"})
    assert r.status_code == 403
    assert not substrate.vouched(PEER, other_pub) and substrate.vouched(PEER, PEER_PUB)


def test_vouch_field_outside_peers_json_ignored(gated, tmp_path, monkeypatch):
    # A vouched_until written anywhere but data/peers.json (here the
    # known_peers.toml pin) is not this owner's vouch and admits nothing.
    toml = tmp_path / "known.toml"
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    toml.write_text(f'[[peer]]\nbrain_id = "{PEER}"\nendpoint = "https://a.example"\n'
                    f'public_key = "{PEER_PUB}"\nvouched_until = "{future}"\n')
    monkeypatch.setenv("BRAIN_KNOWN_PEERS_PATH", str(toml))
    token = issue_federation_assertion(private_key_b64=PEER_PRIV, issuer_brain_id=PEER,
                                       audience_brain_id=THIS, subject="handshake", ttl_seconds=120)
    r = gated.client.post("/v1/federation/assertion",
                          json={"token": token, "issuer_endpoint": "https://a.example"})
    assert r.status_code == 403
