"""Asking out (2026-10-20): POST /v1/ask-peer and api/ask_out.py. No network: a fake opener plays the peer."""
import io
import json
import os
import sys
import tempfile
import types
import urllib.error

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if "sentence_transformers" not in sys.modules:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        _st = types.ModuleType("sentence_transformers")
        _st.SentenceTransformer = object
        sys.modules["sentence_transformers"] = _st

os.environ.setdefault("BRAIN_IDENTITY_SECRET", "test-only-secret")
_RUNTIME = tempfile.mkdtemp(prefix="ask-peer-test-")
os.environ.setdefault("BRAIN_RUNTIME_DIR", _RUNTIME)
os.environ.setdefault("SETTINGS_PATH", os.path.join(_RUNTIME, "settings.json"))

from fastapi.testclient import TestClient  # noqa: E402

from api import ask_out  # noqa: E402
from api import main as m  # noqa: E402
from api.identity.core import generate_brain_keypair, verify_federation_assertion  # noqa: E402

ME = "brain-me"
PEER_ID = "brain-peer"
PRIV, PUB = generate_brain_keypair()
KEY = "owner-key"
CARD = {"name": "Peer", "url": "https://peer.example/v1/ask",
        "capabilities": {"extensions": [{"params": {"brain_id": PEER_ID}}]}}


class _Resp(io.BytesIO):
    def __init__(self, status, obj):
        super().__init__(obj if isinstance(obj, bytes) else json.dumps(obj).encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakePeer:
    """Plays the peer: serves the card, checks the signed ask, answers or refuses."""

    def __init__(self, card=CARD, reply=None, refuse=None):
        self.card, self.reply, self.refuse, self.seen = card, reply, refuse, []

    def open(self, req, timeout=None):
        self.seen.append(req)
        if req.get_method() == "GET":
            return _Resp(200, self.card)
        token = req.get_header("X-brain-assertion")
        claims = verify_federation_assertion(public_key_b64=PUB, token=token, expected_audience=PEER_ID,
                                             expected_issuer=ME)
        body = json.loads(req.data)
        q = body["params"]["message"]["parts"][0]["text"]
        assert claims["qh"] == ask_out.hashlib.sha256(q.encode()).hexdigest()
        if self.refuse:
            return _Resp(200, {"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32011, "message": self.refuse}})
        return _Resp(200, self.reply or {"jsonrpc": "2.0", "id": body["id"], "result": {
            "parts": [{"kind": "text", "text": "Tides follow the moon."},
                      {"kind": "data", "data": {"citations": ["notes/public-essay.md"]}}]}})


def _public(host):
    return host.endswith(".example")


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAIN_ID", ME)
    monkeypatch.setenv("BRAIN_PRIVATE_KEY", PRIV)
    monkeypatch.setattr(m, "BRAIN_API_KEY", KEY)
    from api.tools import federation_audit
    monkeypatch.setattr(federation_audit, "FEDERATION_AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(ask_out, "_public_host", _public)
    peer = FakePeer()
    monkeypatch.setattr(ask_out, "_OPENER", peer)
    c = TestClient(m.app)
    c.peer, c.audit = peer, tmp_path / "audit.jsonl"
    return c


def _ask(c, peer="https://peer.example", key=KEY):
    return c.post("/v1/ask-peer", json={"peer": peer, "question": "What do tides follow?"},
                  headers={"X-API-Key": key} if key else {})


def test_refused_without_the_owner_key(client):
    assert _ask(client, key=None).status_code in (401, 403)
    assert _ask(client, key="wrong").status_code in (401, 403)
    assert client.peer.seen == []


def test_answer_signed_and_audited(client):
    r = _ask(client)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] and d["brain_id"] == PEER_ID and d["answer"] == "Tides follow the moon."
    assert d["citations"] == ["notes/public-essay.md"]
    line = json.loads(client.audit.read_text().strip().splitlines()[-1])
    assert line["direction"] == "out" and line["surface"] == "ask" and line["outcome"] == "ok"


@pytest.mark.parametrize("peer", ["http://peer.example", "https://10.0.0.5", "https://internal.lan", "file:///etc/passwd"])
def test_refuses_plain_http_and_private_peers(client, peer):
    r = _ask(client, peer=peer)
    assert r.status_code == 400 and r.json()["ok"] is False
    assert client.peer.seen == []
    assert json.loads(client.audit.read_text().strip().splitlines()[-1])["direction"] == "out"


def test_card_pointing_inside_is_refused(client):
    client.peer.card = {**CARD, "url": "https://metadata.internal/v1/ask"}
    r = _ask(client)
    assert r.status_code == 400 and "public" in r.json()["error"]
    assert len(client.peer.seen) == 1                       # the card only; the ask was never sent


def test_peer_refusal_is_clean_json(client):
    client.peer.refuse = "not pinned"
    r = _ask(client)
    assert r.status_code == 502 and r.json() == {"ok": False, "error": "the peer refused: not pinned"}


def test_bad_reply_and_no_card(client):
    client.peer.reply = {"jsonrpc": "2.0", "id": "x"}
    assert _ask(client).status_code == 502
    client.peer.card = {"name": "no id"}
    assert "brain_id" in _ask(client).json()["error"]


def test_redirect_not_followed():
    class R(ask_out._NoRedirect):
        pass
    with pytest.raises(ask_out.PeerError) as e:
        R().redirect_request(None, None, 302, "Found", {}, "https://elsewhere.example")
    assert e.value.status == 502


def test_size_cap():
    with pytest.raises(ask_out.PeerError):
        ask_out._read(io.BytesIO(b"x" * 11), 10)


def test_timeout_is_504():
    class Slow:
        def open(self, req, timeout=None):
            raise urllib.error.URLError(TimeoutError())
    with pytest.raises(ask_out.PeerError) as e:
        ask_out.http_json("https://peer.example/x", timeout=1, cap=10, opener=Slow())
    assert e.value.status == 504


def test_no_identity_is_503(client, monkeypatch):
    monkeypatch.delenv("BRAIN_PRIVATE_KEY")
    assert _ask(client).status_code == 503
