"""Help over the record door (MEMBERS-14, 2026-11-23; api/federation_help.py, docs/HELP.md).

Two throwaway brains, fresh ED25519 keys per run, temp dirs, no network. In `helper_app` the
helper (B, hbar's side) is the real FastAPI app and the member (A) is a Door; in `member_app`
the member is the app (its console routes) and the helper is a Door. Each reaches the other
in-process through POST /v1/federation/record, with every check of the door in place.
"""
import json
import os
import sys
import tempfile
import time
import types

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("BRAIN_IDENTITY_SECRET", "test-only-secret")
_RUNTIME = tempfile.mkdtemp(prefix="help-test-")
os.environ.setdefault("BRAIN_RUNTIME_DIR", _RUNTIME)
os.environ.setdefault("SETTINGS_PATH", os.path.join(_RUNTIME, "settings.json"))

from fastapi.testclient import TestClient  # noqa: E402

from api import federation_help as fh  # noqa: E402
from api import federation_record as fr  # noqa: E402
from api import hbar_commands  # noqa: E402
from api import main as m  # noqa: E402
from api.identity.core import generate_brain_keypair  # noqa: E402

MEMBER, HELPER, EVE = "brain-member-test", "brain-helper-test", "brain-eve-test"
M_PRIV, M_PUB = generate_brain_keypair()
H_PRIV, H_PUB = generate_brain_keypair()
EVE_PRIV, EVE_PUB = generate_brain_keypair()
OWNER = {"x-api-key": "owner-key-test"}
ASK = dict(screen="/cc", pressed=["/cc", "send", "/files"], words="the chat does not answer", lang="ru",
           console_version="0.13.0")


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


def _app_brain(monkeypatch, tmp_path, *, me, me_priv, peer, peer_pub, helper=None):
    monkeypatch.setenv("BRAIN_ID", me)
    monkeypatch.setenv("BRAIN_PRIVATE_KEY", me_priv)
    monkeypatch.setenv("FEDERATION_RECORDS_PATH", str(tmp_path / "app" / "records.jsonl"))
    monkeypatch.setenv("BRAIN_KNOWN_PEERS_PATH", str(tmp_path / "none.toml"))
    monkeypatch.setenv("HELP_CONFIG_PATH", str(tmp_path / "app" / "help.json"))
    monkeypatch.delenv("BRAIN_HELP_PEER", raising=False)
    if helper:
        (tmp_path / "app").mkdir(exist_ok=True)
        (tmp_path / "app" / "help.json").write_text(json.dumps({"helper": helper}))
    monkeypatch.setattr(m, "BRAIN_API_KEY", OWNER["x-api-key"])
    peers = tmp_path / "peers.json"
    peers.write_text(json.dumps([{"brain_id": peer, "endpoint": "https://peer.example", "public_key": peer_pub}]))
    monkeypatch.setattr(hbar_commands, "_PEERS_PATH", peers)
    from api.tools import federation_audit
    monkeypatch.setattr(federation_audit, "FEDERATION_AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(m._ask_rate_limiter, "_client", FakeRedis())
    monkeypatch.setattr(m._ask_rate_limiter, "max_hits", 30)
    return TestClient(m.app)


def _wire(client, door, monkeypatch):
    """door -> app through the app's real route; app -> door through door.receive."""
    def door_to_app(peer, env):
        r = client.post(fr.RECORD_PATH, json=json.loads(json.dumps(env)))
        return r.status_code, r.json()
    door.deliver = door_to_app

    def app_to_door(peer, env):
        try:
            return 200, json.loads(json.dumps(door.receive(json.loads(json.dumps(env)))))
        except fr.RecordError as e:
            return e.status, {"detail": e.reason}
    monkeypatch.setattr(fr, "http_deliver", app_to_door)


@pytest.fixture
def helper_app(monkeypatch, tmp_path):
    """B = hbar's brain (the app, the helper); A = the member's brain (a Door)."""
    client = _app_brain(monkeypatch, tmp_path, me=HELPER, me_priv=H_PRIV, peer=MEMBER, peer_pub=M_PUB)
    a = fr.Door(brain_id=MEMBER, private_key=M_PRIV, store=fr.Store(tmp_path / "a" / "records.jsonl"),
                pins=lambda b: {"brain_id": HELPER, "endpoint": "https://helper.example", "public_key": H_PUB}
                if b == HELPER else None)
    _wire(client, a, monkeypatch)
    fr._DOORS.clear()
    yield types.SimpleNamespace(a=a, client=client, tmp=tmp_path)
    fr._DOORS.clear()


@pytest.fixture
def member_app(monkeypatch, tmp_path):
    """The member's brain is the app (its console routes); hbar's brain is a Door."""
    client = _app_brain(monkeypatch, tmp_path, me=MEMBER, me_priv=M_PRIV, peer=HELPER, peer_pub=H_PUB, helper=HELPER)
    h = fr.Door(brain_id=HELPER, private_key=H_PRIV, store=fr.Store(tmp_path / "h" / "records.jsonl"),
                pins=lambda b: {"brain_id": MEMBER, "endpoint": "https://member.example", "public_key": M_PUB}
                if b == MEMBER else None)
    _wire(client, h, monkeypatch)
    fr._DOORS.clear()
    yield types.SimpleNamespace(h=h, client=client, tmp=tmp_path)
    fr._DOORS.clear()


def _signed(rec, priv):
    return {"record": rec, "sig": fr.sign_doc(priv, rec)}


def _req_record(frm=MEMBER, body=None, rid=None):
    now = int(time.time())
    raw = {"v": 1, "kind": "help.request", "rid": rid or f"help-{now:010d}-0123456789ab", "from": frm,
           "to": HELPER, "iat": now, "exp": now + 3600, "body": body or dict(ASK)}
    return raw


# ---------------------------------------------------------------- the whole loop

def test_request_goes_to_helper_and_answer_comes_back(helper_app, monkeypatch):
    monkeypatch.setenv("BRAIN_HELP_PEER", HELPER)
    row = fh.ask(helper_app.a, **ASK)
    assert row["receipt"]["by"] == HELPER  # B kept it and countersigned it
    rid = row["rid"]

    inbox = helper_app.client.get("/v1/help/inbox", headers=OWNER).json()
    assert inbox["open"] == 1
    card = inbox["requests"][0]
    assert card["from"] == MEMBER and card["words"] == ASK["words"] and card["screen"] == "/cc"
    assert card["pressed"] == ["/cc", "send", "/files"] and card["lang"] == "ru" and not card["answered"]
    assert helper_app.client.get("/v1/federation/records/verify", headers=OWNER).json()["clean"] is True

    r = helper_app.client.post("/v1/help/answer", headers=OWNER,
                               json={"peer": MEMBER, "rid": rid, "words": "press Reload, then sign in again"})
    assert r.status_code == 200, r.text
    assert r.json()["receipt"]["by"] == MEMBER  # the member's brain countersigned the answer
    assert r.json()["record"]["ref"] == fr.record_hash(row["record"])

    st = fh.status(helper_app.a)
    assert st["ready"] and st["message"] is None
    assert st["asked"][0]["answer"]["words"] == "press Reload, then sign in again"
    assert helper_app.client.get("/v1/help/inbox", headers=OWNER).json()["open"] == 0
    assert helper_app.a.verify() == []

    # answering twice sends nothing new
    again = helper_app.client.post("/v1/help/answer", headers=OWNER,
                                   json={"peer": MEMBER, "rid": rid, "words": "something else"}).json()
    assert again["record"]["body"]["words"] == "press Reload, then sign in again"


def test_member_console_routes(member_app):
    st = member_app.client.get("/v1/help/status", headers=OWNER).json()
    assert st["helper"] == HELPER and st["ready"] and st["asked"] == []
    r = member_app.client.post("/v1/help/ask", headers=OWNER,
                               json={"screen": "/files?path=/home/me/secret.txt", "pressed": ["/files", "Not A Name"],
                                     "words": "where are my files", "lang": "sk"})
    assert r.status_code == 200, r.text
    body = r.json()["record"]["body"]
    assert body == {"screen": "/files", "pressed": ["/files"], "words": "where are my files", "lang": "sk",
                    "console_version": m.BRAIN_VERSION}  # no query string, no label outside the alphabet
    got = fh.inbox(member_app.h)["requests"]
    assert got[0]["words"] == "where are my files"
    fh.answer(member_app.h, frm=MEMBER, rid=got[0]["rid"], words="open Files from the menu")
    st = member_app.client.get("/v1/help/status", headers=OWNER).json()
    assert st["asked"][0]["answer"]["words"] == "open Files from the menu"


def test_help_routes_need_the_owner_key(member_app):
    assert member_app.client.get("/v1/help/status").status_code in (401, 403)
    assert member_app.client.get("/v1/help/inbox").status_code in (401, 403)
    assert member_app.client.post("/v1/help/ask", json={"words": "x"}).status_code in (401, 403)
    assert member_app.client.post("/v1/help/answer", json={"peer": HELPER, "rid": "x", "words": "x"}).status_code in (401, 403)
    assert fh.inbox(member_app.h)["requests"] == []


# ---------------------------------------------------------------- trust and shape

def test_unpinned_sender_refused(helper_app):
    r = helper_app.client.post(fr.RECORD_PATH, json=_signed(_req_record(frm=EVE), EVE_PRIV))
    assert r.status_code == 403 and r.json()["detail"] == "unknown_peer"
    assert helper_app.client.get("/v1/help/inbox", headers=OWNER).json()["requests"] == []


def test_extra_fields_refused_at_the_door(helper_app):
    for extra in ({"memory": "my notes"}, {"chat": "hello"}, {"persona": "x"}):
        r = helper_app.client.post(fr.RECORD_PATH, json=_signed(_req_record(body=dict(ASK, **extra)), M_PRIV))
        assert r.status_code == 400 and "carries only" in r.json()["detail"]
    assert helper_app.client.get("/v1/help/inbox", headers=OWNER).json()["requests"] == []


def test_extra_fields_refused_by_the_members_own_brain(member_app):
    # the member's own brain will not even sign one: the console route forbids extra fields
    r = member_app.client.post("/v1/help/ask", headers=OWNER, json={"words": "hi", "memory": "my notes"})
    assert r.status_code == 422
    with pytest.raises(fr.RecordError, match="carries only"):
        member_app.h.send(kind="help.request", to=MEMBER, rid="help-0000000001-0123456789ab",
                          body=dict(ASK, chat="hello"))


def test_bad_values_in_the_shape_refused(helper_app):
    for bad in ({"screen": "/files?path=/x"}, {"pressed": ["a"] * 9}, {"pressed": ["My File.txt"]},
                {"words": ""}, {"words": "x" * 2001}, {"lang": "Russian"}, {"console_version": ""}):
        r = helper_app.client.post(fr.RECORD_PATH, json=_signed(_req_record(body=dict(ASK, **bad)), M_PRIV))
        assert r.status_code == 400, bad


def test_forged_answer_for_a_request_never_sent_refused(helper_app):
    rec = fr.make_record(kind="help.answer", rid="help-0000000001-0123456789ab.answer", frm=HELPER, to=MEMBER,
                         now=int(time.time()), ref="0" * 64,
                         body={"request_rid": "help-0000000001-0123456789ab", "words": "trust me"})
    with pytest.raises(fr.RecordError, match="answers no help request"):
        helper_app.a.receive(_signed(rec, H_PRIV))


def test_answer_with_wrong_ref_refused(helper_app, monkeypatch):
    monkeypatch.setenv("BRAIN_HELP_PEER", HELPER)
    rid = fh.ask(helper_app.a, **ASK)["rid"]
    rec = fr.make_record(kind="help.answer", rid=f"{rid}.answer", frm=HELPER, to=MEMBER, now=int(time.time()),
                         ref="1" * 64, body={"request_rid": rid, "words": "x"})
    with pytest.raises(fr.RecordError, match="ref does not match"):
        helper_app.a.receive(_signed(rec, H_PRIV))


def test_help_is_not_pressed_in_records(helper_app, monkeypatch):
    monkeypatch.setenv("BRAIN_HELP_PEER", HELPER)
    rid = fh.ask(helper_app.a, **ASK)["rid"]
    listed = helper_app.client.get("/v1/federation/records", headers=OWNER).json()["records"]
    assert listed[0]["kind"] == "help.request" and listed[0]["answerable"] is False
    r = helper_app.client.post("/v1/federation/records/answer", headers=OWNER,
                               json={"peer": MEMBER, "rid": rid, "typed": "confirm"})
    assert r.status_code == 400 and "Help" in r.json()["detail"]


# ---------------------------------------------------------------- no helper, replay, limits

def test_no_helper_configured_gives_a_plain_message(member_app, monkeypatch):
    (member_app.tmp / "app" / "help.json").unlink()
    st = member_app.client.get("/v1/help/status", headers=OWNER).json()
    assert st["helper"] is None and st["ready"] is False and st["message"] == fh.NO_HELPER
    r = member_app.client.post("/v1/help/ask", headers=OWNER, json={"words": "help"})
    assert r.status_code == 409 and r.json()["detail"] == fh.NO_HELPER
    assert "Tell hbar" in fh.NO_HELPER


def test_helper_named_but_not_pinned(member_app, monkeypatch):
    monkeypatch.setenv("BRAIN_HELP_PEER", "brain-stranger-test")
    st = member_app.client.get("/v1/help/status", headers=OWNER).json()
    assert st["ready"] is False and st["message"] == fh.NOT_PINNED
    assert member_app.client.post("/v1/help/ask", headers=OWNER, json={"words": "help"}).status_code == 409


def test_replay_refused(helper_app):
    rid = "help-0000000001-0123456789ab"
    env = _signed(_req_record(rid=rid), M_PRIV)
    r1 = helper_app.client.post(fr.RECORD_PATH, json=env).json()
    assert helper_app.client.post(fr.RECORD_PATH, json=env).json() == r1  # same receipt, kept once
    assert len(helper_app.client.get("/v1/help/inbox", headers=OWNER).json()["requests"]) == 1
    other = _signed(_req_record(rid=rid, body=dict(ASK, words="other words")), M_PRIV)
    assert helper_app.client.post(fr.RECORD_PATH, json=other).status_code == 409


def test_answer_replay_refused(helper_app, monkeypatch):
    monkeypatch.setenv("BRAIN_HELP_PEER", HELPER)
    rid = fh.ask(helper_app.a, **ASK)["rid"]
    fh_row = helper_app.client.post("/v1/help/answer", headers=OWNER,
                                    json={"peer": MEMBER, "rid": rid, "words": "first"}).json()
    rec = fr.make_record(kind="help.answer", rid=f"{rid}.answer", frm=HELPER, to=MEMBER, now=int(time.time()),
                         ref=fh_row["record"]["ref"], body={"request_rid": rid, "words": "second, changed"})
    with pytest.raises(fr.RecordError, match="rid already used"):
        helper_app.a.receive(_signed(rec, H_PRIV))
    assert fh.status(helper_app.a)["asked"][0]["answer"]["words"] == "first"


def test_asks_per_day_capped(helper_app, monkeypatch):
    monkeypatch.setenv("BRAIN_HELP_PEER", HELPER)
    for _ in range(fh.MAX_ASKS_PER_DAY):
        fh.ask(helper_app.a, **ASK)
    with pytest.raises(fr.RecordError, match="today already"):
        fh.ask(helper_app.a, **ASK)


def test_unreachable_helper_keeps_the_request(helper_app, monkeypatch):
    monkeypatch.setenv("BRAIN_HELP_PEER", HELPER)
    real = helper_app.a.deliver
    helper_app.a.deliver = lambda peer, env: (_ for _ in ()).throw(OSError("down"))
    row = fh.ask(helper_app.a, **ASK)
    assert row["delivery"].startswith("pending")
    assert fh.status(helper_app.a)["asked"][0]["delivered"] is False
    helper_app.a.deliver = real
    helper_app.a.redeliver(row["rid"])
    assert fh.status(helper_app.a)["asked"][0]["delivered"] is True


def test_help_module_carries_no_content_words():
    """The shape has no room for memory, chat, files or persona; the module never reads them."""
    src = open(fh.__file__, encoding="utf-8").read()
    for w in ("import api.memory", "vector", "chroma", "persona_", "open(", "chat_history"):
        assert w not in src, w
