"""The record door (A2A-2, 2026-11-23; api/federation_record.py, docs/RECORDS.md).

Two throwaway brains, fresh ED25519 keys per run, no network: brain A is a Door object,
brain B is the real FastAPI app (its routes, its owner key, its store), and each reaches
the other in-process. Nothing here knows what a record means.
"""
import json
import os
import sys
import tempfile
import types

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("BRAIN_IDENTITY_SECRET", "test-only-secret")
_RUNTIME = tempfile.mkdtemp(prefix="record-test-")
os.environ.setdefault("BRAIN_RUNTIME_DIR", _RUNTIME)
os.environ.setdefault("SETTINGS_PATH", os.path.join(_RUNTIME, "settings.json"))

from fastapi.testclient import TestClient  # noqa: E402

from api import federation_record as fr  # noqa: E402
from api import hbar_commands  # noqa: E402
from api import main as m  # noqa: E402
from api.identity.core import generate_brain_keypair  # noqa: E402

A, B, EVE = "brain-a-test", "brain-b-test", "brain-eve-test"
A_PRIV, A_PUB = generate_brain_keypair()
B_PRIV, B_PUB = generate_brain_keypair()
EVE_PRIV, EVE_PUB = generate_brain_keypair()
OWNER = {"x-api-key": "owner-key-b"}
RID = "rec-0001-test"


class FakeRedis:
    def __init__(self):
        self.d = {}

    def incr(self, k):
        self.d[k] = self.d.get(k, 0) + 1
        return self.d[k]

    def expire(self, k, s):
        pass

    def ttl(self, k):
        return 42


def _pins(table):
    return lambda bid: table.get(bid)


@pytest.fixture
def two(monkeypatch, tmp_path):
    """Brain B = the app; brain A = a Door whose deliver posts to B's route."""
    monkeypatch.setenv("BRAIN_ID", B)
    monkeypatch.setenv("BRAIN_PRIVATE_KEY", B_PRIV)
    monkeypatch.setenv("FEDERATION_RECORDS_PATH", str(tmp_path / "b" / "records.jsonl"))
    monkeypatch.setenv("BRAIN_KNOWN_PEERS_PATH", str(tmp_path / "none.toml"))
    monkeypatch.setattr(m, "BRAIN_API_KEY", OWNER["x-api-key"])
    peers = tmp_path / "peers.json"
    peers.write_text(json.dumps([{"brain_id": A, "endpoint": "https://a.example", "public_key": A_PUB}]))
    monkeypatch.setattr(hbar_commands, "_PEERS_PATH", peers)
    from api.tools import federation_audit
    monkeypatch.setattr(federation_audit, "FEDERATION_AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(m._ask_rate_limiter, "_client", FakeRedis())
    monkeypatch.setattr(m._ask_rate_limiter, "max_hits", 30)
    client = TestClient(m.app)

    def a_to_b(peer, env):
        assert peer["brain_id"] == B and peer["endpoint"] == "https://b.example"
        r = client.post(fr.RECORD_PATH, json=env)
        return r.status_code, r.json()

    a = fr.Door(brain_id=A, private_key=A_PRIV, store=fr.Store(tmp_path / "a" / "records.jsonl"),
                pins=_pins({B: {"brain_id": B, "endpoint": "https://b.example", "public_key": B_PUB}}),
                deliver=a_to_b)

    def b_to_a(peer, env):
        assert peer["brain_id"] == A and peer["endpoint"] == "https://a.example"
        try:
            return 200, json.loads(json.dumps(a.receive(json.loads(json.dumps(env)))))
        except fr.RecordError as e:
            return e.status, {"detail": e.reason}

    monkeypatch.setattr(fr, "http_deliver", b_to_a)
    fr._DOORS.clear()
    yield types.SimpleNamespace(a=a, client=client, tmp=tmp_path, audit=federation_audit)
    fr._DOORS.clear()


def _b():
    return fr.door_from_env()


def _send(a, rid=RID, **kw):
    args = dict(kind="test.note", to=B, rid=rid, body={"text": "hello", "n": 3}, confirm="yes test.note from a")
    args.update(kw)
    return a.send(**args)


def _signed(rec, priv=A_PRIV):
    return {"record": rec, "sig": fr.sign_doc(priv, rec)}


def _rec(now=None, **kw):
    import time
    args = dict(kind="test.note", rid=RID, frm=A, to=B, body={"text": "hi"}, now=int(now or time.time()))
    args.update(kw)
    return fr.make_record(**args)


# ---------------------------------------------------------------- the whole loop

def test_full_loop_rows_identical_on_both_brains(two):
    row_a = _send(two.a)
    assert "receipt" in row_a and row_a["receipt"]["by"] == B
    key = f"{A}/{RID}"
    r = two.client.get("/v1/federation/records/row", params={"peer": A, "rid": RID}, headers=OWNER)
    assert r.status_code == 200 and r.json() == row_a  # record, sig, receipt, receipt_sig: identical

    listed = two.client.get("/v1/federation/records", headers=OWNER).json()["records"]
    assert listed[0]["answerable"] and listed[0]["confirm_text"] == "yes test.note from a"

    # B's owner presses confirm: B signs a confirm record and delivers it back to A, A countersigns
    r = two.client.post("/v1/federation/records/answer", headers=OWNER,
                        json={"peer": A, "rid": RID, "typed": "yes test.note from a", "note": "ok"})
    assert r.status_code == 200, r.text
    conf_b = r.json()
    assert conf_b["record"]["kind"] == "record.confirm" and conf_b["receipt"]["by"] == A
    assert conf_b["record"]["ref"] == fr.record_hash(row_a["record"])
    conf_a = two.a.row(f"{B}/{RID}.confirm")
    assert conf_a == conf_b  # the confirmation lands on A's side too, countersigned, same bytes
    assert two.a.row(key) == _b().row(key)
    assert two.a.verify() == [] and _b().verify() == []
    assert two.client.get("/v1/federation/records/verify", headers=OWNER).json()["clean"] is True
    a_list = {x["key"]: x for x in two.a.list()}
    assert a_list[key]["answer"] == "confirm"


def test_decline_is_a_signed_record_too(two):
    _send(two.a)
    r = two.client.post("/v1/federation/records/answer", headers=OWNER,
                        json={"peer": A, "rid": RID, "typed": "decline", "decline": True})
    assert r.status_code == 200 and r.json()["record"]["kind"] == "record.decline"
    assert {x["key"]: x for x in two.a.list()}[f"{A}/{RID}"]["answer"] == "decline"


# ---------------------------------------------------------------- the owner's press

def test_confirm_needs_exact_text_and_the_owner_key(two):
    _send(two.a)
    r = two.client.post("/v1/federation/records/answer", json={"peer": A, "rid": RID, "typed": "yes test.note from a"})
    assert r.status_code in (401, 403)
    r = two.client.post("/v1/federation/records/answer", headers=OWNER,
                        json={"peer": A, "rid": RID, "typed": "yes"})
    assert r.status_code == 400 and "type exactly" in r.json()["detail"]
    assert two.a.list()[0]["answer"] is None  # nothing went back


def test_sending_and_listing_need_the_owner_key(two):
    for path in ("/v1/federation/records", "/v1/federation/records/verify"):
        assert two.client.get(path).status_code in (401, 403)
    r = two.client.post("/v1/federation/records/send", json={"kind": "x", "to": A, "rid": "r-00000001", "body": {}})
    assert r.status_code in (401, 403)


def test_confirm_twice_returns_the_same_answer(two):
    _send(two.a)
    body = {"peer": A, "rid": RID, "typed": "yes test.note from a"}
    first = two.client.post("/v1/federation/records/answer", headers=OWNER, json=body).json()
    again = two.client.post("/v1/federation/records/answer", headers=OWNER, json=body).json()
    assert first == again
    assert len([l for l in two.a.store.lines() if l["event"] == "in"]) == 1


def test_a_confirmation_cannot_be_confirmed(two):
    _send(two.a)
    two.client.post("/v1/federation/records/answer", headers=OWNER,
                    json={"peer": A, "rid": RID, "typed": "yes test.note from a"})
    with pytest.raises(fr.RecordError, match="not confirmed again"):
        two.a.answer(frm=B, rid=f"{RID}.confirm", typed="confirm")


# ---------------------------------------------------------------- trust

def test_unknown_sender_refused(two):
    rec = _rec(frm=EVE)
    r = two.client.post(fr.RECORD_PATH, json=_signed(rec, EVE_PRIV))
    assert r.status_code == 403 and r.json()["detail"] == "unknown_peer"


def test_impostor_key_against_the_pin_refused(two):
    r = two.client.post(fr.RECORD_PATH, json=_signed(_rec(), EVE_PRIV))
    assert r.status_code == 401 and "pinned" in r.json()["detail"]


def test_tampered_record_refused(two):
    env = _signed(_rec())
    env["record"]["body"]["text"] = "changed"
    assert two.client.post(fr.RECORD_PATH, json=env).status_code == 401


def test_misaddressed_refused(two):
    r = two.client.post(fr.RECORD_PATH, json=_signed(_rec(to="brain-c-test")))
    assert r.status_code == 403 and "addressed" in r.json()["detail"]


def test_expired_future_and_long_lived_refused(two):
    import time
    now = int(time.time())
    raw = {"v": 1, "kind": "test.note", "rid": RID, "from": A, "to": B, "iat": now - 3 * 86400,
           "exp": now - 86400, "body": {}}
    assert two.client.post(fr.RECORD_PATH, json=_signed(raw)).json()["detail"] == "expired"
    raw.update(iat=now + 3600, exp=now + 7200)
    assert two.client.post(fr.RECORD_PATH, json=_signed(raw)).json()["detail"] == "issued in the future"
    raw.update(iat=now, exp=now + fr.MAX_TTL + 10)
    assert "lifetime" in two.client.post(fr.RECORD_PATH, json=_signed(raw)).json()["detail"]


def test_floats_extra_fields_and_reserved_kinds_refused(two):
    import time
    now = int(time.time())
    base = {"v": 1, "kind": "test.note", "rid": RID, "from": A, "to": B, "iat": now, "exp": now + 60, "body": {}}
    with pytest.raises(fr.RecordError, match="float"):
        fr.sign_doc(A_PRIV, dict(base, body={"x": 1.5}))
    for bad in (dict(base, extra=1), dict(base, kind="record.receipt"), dict(base, kind="Bad Kind"),
                dict(base, rid="short"), dict(base, v=2)):
        assert two.client.post(fr.RECORD_PATH, json=_signed(bad)).status_code == 400


def test_body_size_capped(two):
    import time
    now = int(time.time())
    raw = {"v": 1, "kind": "test.note", "rid": RID, "from": A, "to": B, "iat": now, "exp": now + 60,
           "body": {"t": "x" * (fr.MAX_BODY_BYTES + 10)}}
    r = two.client.post(fr.RECORD_PATH, json=_signed(raw))
    assert r.status_code == 413


def test_forged_confirmation_for_a_record_never_sent_refused(two):
    # B (pinned on A) claims to confirm something A never sent: A refuses it
    b = _b()
    rec = fr.make_record(kind="record.confirm", rid="never-sent.confirm", frm=B, to=A, now=b._now(),
                         ref="0" * 64, body={"rid": "never-sent", "kind": "test.note", "note": ""})
    with pytest.raises(fr.RecordError, match="confirms no record"):
        two.a.receive({"record": rec, "sig": fr.sign_doc(B_PRIV, rec)})


def test_confirmation_with_wrong_ref_refused(two):
    _send(two.a)
    b = _b()
    rec = fr.make_record(kind="record.confirm", rid=f"{RID}.confirm", frm=B, to=A, now=b._now(),
                         ref="1" * 64, body={"rid": RID, "kind": "test.note", "note": ""})
    with pytest.raises(fr.RecordError, match="ref does not match"):
        two.a.receive({"record": rec, "sig": fr.sign_doc(B_PRIV, rec)})


def test_send_only_to_pinned_peers_and_no_hand_made_confirms(two):
    with pytest.raises(fr.RecordError, match="unknown_peer"):
        two.a.send(kind="test.note", to=EVE, rid=RID, body={})
    with pytest.raises(fr.RecordError, match="confirm press"):
        two.a.send(kind="record.confirm", to=B, rid=RID, body={"rid": "x"}, ref="0" * 64)


# ---------------------------------------------------------------- replay

def test_replay_returns_the_same_receipt_and_rid_reuse_refused(two):
    env = _signed(_rec())
    r1 = two.client.post(fr.RECORD_PATH, json=env).json()
    r2 = two.client.post(fr.RECORD_PATH, json=env).json()
    assert r1 == r2
    assert len([l for l in _b().store.lines() if l["event"] == "in"]) == 1
    other = _signed(_rec(body={"text": "other"}))
    r3 = two.client.post(fr.RECORD_PATH, json=other)
    assert r3.status_code == 409


def test_replay_survives_a_restart(two):
    env = _signed(_rec())
    r1 = two.client.post(fr.RECORD_PATH, json=env).json()
    fr._DOORS.clear()  # a new process: the store on disk is the replay guard
    assert two.client.post(fr.RECORD_PATH, json=env).json() == r1
    assert two.client.post(fr.RECORD_PATH, json=_signed(_rec(body={"x": "y"}))).status_code == 409


def test_sender_refuses_reusing_its_own_rid(two):
    _send(two.a)
    with pytest.raises(fr.RecordError, match="rid already used"):
        _send(two.a)


# ---------------------------------------------------------------- delivery

def test_unreachable_peer_keeps_the_signed_record_and_redelivers(two):
    real = two.a.deliver
    two.a.deliver = lambda peer, env: (_ for _ in ()).throw(OSError("down"))
    row = _send(two.a)
    assert "receipt" not in row and row["delivery"].startswith("pending")
    assert two.a.list()[0]["last_error"].startswith("unreachable")
    two.a.deliver = real
    row = two.a.redeliver(RID)
    assert "receipt" in row and row == _b().row(f"{A}/{RID}")


def test_forged_receipt_refused(two):
    def liar(peer, env):
        rec = env["record"]
        receipt = fr.make_receipt(rec, by=B, now=0)
        return 200, {"receipt": receipt, "sig": fr.sign_doc(EVE_PRIV, receipt)}
    two.a.deliver = liar
    with pytest.raises(fr.RecordError, match="signature"):
        _send(two.a)
    assert "receipt" not in two.a.row(f"{A}/{RID}")


def test_receipt_for_other_content_refused(two):
    def liar(peer, env):
        receipt = dict(fr.make_receipt(env["record"], by=B, now=0), record_hash="2" * 64)
        return 200, {"receipt": receipt, "sig": fr.sign_doc(B_PRIV, receipt)}
    two.a.deliver = liar
    with pytest.raises(fr.RecordError, match="does not match"):
        _send(two.a)


# ---------------------------------------------------------------- store

def test_store_is_private_chained_and_tamper_found(two):
    _send(two.a)
    p = two.tmp / "b" / "records.jsonl"
    assert oct(p.stat().st_mode & 0o777) == "0o600"
    assert _b().verify() == []
    lines = p.read_text().splitlines()
    e = json.loads(lines[0])
    e["body"]["record"]["body"]["text"] = "edited on disk"
    lines[0] = json.dumps(e, sort_keys=True)
    p.write_text("\n".join(lines) + "\n")
    probs = _b().verify()
    assert "hash chain broken" in probs and any("record signature" in x for x in probs)


def test_canonical_bytes_are_jcs():
    doc = {"b": [1, True, None], "a": {"z": "ü", "y": -3}}
    assert fr.canonical(doc) == b'{"a":{"y":-3,"z":"\xc3\xbc"},"b":[1,true,null]}'


def test_inbound_is_audited(two):
    _send(two.a)
    two.client.post(fr.RECORD_PATH, json=_signed(_rec(frm=EVE), EVE_PRIV))
    lines = [json.loads(l) for l in (two.tmp / "audit.jsonl").read_text().splitlines()]
    outcomes = [l.get("outcome") for l in lines if l.get("surface") == "record"]
    assert "kept" in outcomes and any(o.startswith("refused:unknown_peer") for o in outcomes)


def test_door_holds_no_money_words():
    src = open(fr.__file__, encoding="utf-8").read().lower()
    for w in ("amount", "currency", "price", "iban", "eur ", "payment", "invoice"):
        assert w not in src, w
