"""
The ask door (api/ask.py, /.well-known/agent-card.json, /v1/ask; docs/ASK.md).

No network, no database, no model: retrieval, the model call and Redis are
replaced in-process. Keys are fresh ED25519 pairs per run.
"""
import json
import os
import sys
import tempfile
import types

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# api.main imports sentence_transformers at module top; the embedder is never
# used here, so a stand-in keeps the test env free of torch.
if "sentence_transformers" not in sys.modules:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        _st = types.ModuleType("sentence_transformers")
        _st.SentenceTransformer = object
        sys.modules["sentence_transformers"] = _st

# main refuses to start without an identity secret; a throwaway one for import.
os.environ.setdefault("BRAIN_IDENTITY_SECRET", "test-only-secret")
# Off-container: runtime state goes to a scratch dir, not /app/runtime.
_RUNTIME = tempfile.mkdtemp(prefix="ask-test-")
os.environ.setdefault("BRAIN_RUNTIME_DIR", _RUNTIME)
os.environ.setdefault("SETTINGS_PATH", os.path.join(_RUNTIME, "settings.json"))

from fastapi.testclient import TestClient  # noqa: E402

from api import ask, hbar_commands, settings_store, substrate  # noqa: E402
from api import main as m  # noqa: E402
from api.identity import replay_cache  # noqa: E402
from api.identity.core import generate_brain_keypair, issue_federation_assertion  # noqa: E402
from scripts import ask_brain  # noqa: E402

THIS = "brain-b"
PEER = "brain-a"
PEER_PRIV, PEER_PUB = generate_brain_keypair()
STRANGER_PRIV, STRANGER_PUB = generate_brain_keypair()

DOCS = [
    {"document_name": "notes/public-essay.md", "content": "PUBLIC FACT: tides follow the moon.",
     "metadata": {"scope": "public"}},
    {"document_name": "notes/team-plan.md", "content": "INTERNAL SECRET plan",
     "metadata": {"scope": "internal"}},
    {"document_name": "diary/2026.md", "content": "PRIVATE SECRET diary",
     "metadata": {"scope": "private"}},
    {"document_name": "unscoped.md", "content": "UNSCOPED SECRET", "metadata": {}},
]


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


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAIN_ID", THIS)
    monkeypatch.setenv("FEDERATION_SUBSTRATE_GATE", "off")
    monkeypatch.setenv("BRAIN_KNOWN_PEERS_PATH", str(tmp_path / "none.toml"))
    monkeypatch.setenv("BRAIN_PUBLIC_URL", "https://b.example")
    from api.tools import federation_audit
    monkeypatch.setattr(federation_audit, "FEDERATION_AUDIT_PATH", tmp_path / "audit.jsonl")
    peers = tmp_path / "peers.json"
    peers.write_text(json.dumps([{"brain_id": PEER, "endpoint": "https://a.example",
                                  "public_key": PEER_PUB}]))
    monkeypatch.setattr(hbar_commands, "_PEERS_PATH", peers)
    monkeypatch.setattr(settings_store, "get_ask_public_enabled", lambda: False)

    seen = {}

    def fake_search(query, limit=5, layers=None, architecture=None, scope=None, allow_local_only=False):
        seen.update(scope=scope, allow_local_only=allow_local_only, architecture=architecture)
        return [dict(d) for d in DOCS]  # retrieval misbehaves: the door must still filter

    async def fake_complete(model, messages, max_tokens=None, **kw):
        return "ECHO " + messages[0]["content"]  # leaks whatever the prompt holds

    monkeypatch.setattr(m, "search_similar_documents", fake_search)
    monkeypatch.setattr(m._providers, "complete", fake_complete)
    limiter = m._ask_rate_limiter
    monkeypatch.setattr(limiter, "_client", FakeRedis())
    monkeypatch.setattr(limiter, "max_hits", 30)
    replay_cache.clear()
    yield types.SimpleNamespace(client=TestClient(m.app), seen=seen, audit=federation_audit,
                                limiter=limiter)
    replay_cache.clear()


def _signed(question, *, priv=PEER_PRIV, iss=PEER, aud=THIS, ttl=120, qh=None, sub="ask",
            public_key=None):
    token = issue_federation_assertion(
        private_key_b64=priv, issuer_brain_id=iss, audience_brain_id=aud, subject=sub,
        ttl_seconds=ttl, claims={"qh": qh or ask.question_hash(question)})
    params = {"message": {"role": "user", "messageId": "m1",
                          "parts": [{"kind": "text", "text": question}]}}
    if public_key:
        params["metadata"] = {"brainfoundry": {"public_key": public_key}}
    return {ask.ASSERTION_HEADER: token}, {"jsonrpc": "2.0", "id": 7, "method": "message/send",
                                           "params": params}


def _ask(env, question="What do tides follow?", **kw):
    headers, body = _signed(question, **kw)
    return env.client.post("/v1/ask", json=body, headers=headers)


# ── card ─────────────────────────────────────────────────────────────────────

def test_card_shape(env, monkeypatch):
    monkeypatch.setattr(m, "BRAIN_PERSONA", "# TEMPLATE banner\n\n# I am Brain B, a field notebook.\nMore.")
    r = env.client.get("/.well-known/agent-card.json")
    assert r.status_code == 200
    c = r.json()
    for k in ("protocolVersion", "name", "description", "url", "version", "skills",
              "capabilities", "securitySchemes", "security", "defaultInputModes", "defaultOutputModes"):
        assert k in c
    assert c["url"] == "https://b.example/v1/ask"
    assert c["description"] == "I am Brain B, a field notebook."
    assert [s["id"] for s in c["skills"]] == ["ask"]
    scheme = c["securitySchemes"]["brainfoundry-ed25519"]
    assert scheme["in"] == "header" and scheme["name"] == "X-Brain-Assertion"
    assert "https://b.example/identity" in scheme["description"]
    assert c["security"] == [{"brainfoundry-ed25519": []}]
    ext = c["capabilities"]["extensions"][0]["params"]
    assert ext["identity_url"] == "https://b.example/identity" and ext["brain_id"] == THIS
    assert c["version"] == m.BRAIN_VERSION


# ── trust ────────────────────────────────────────────────────────────────────

def test_signed_peer_gets_answer_with_citations(env):
    r = _ask(env)
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    assert r.json()["id"] == 7 and res["kind"] == "message" and res["role"] == "agent"
    assert res["parts"][0]["kind"] == "text" and "PUBLIC FACT" in res["parts"][0]["text"]
    assert res["parts"][1]["data"]["citations"] == ["notes/public-essay.md"]


def test_unsigned_refused(env):
    _, body = _signed("q")
    r = env.client.post("/v1/ask", json=body)
    assert r.status_code == 401 and r.json()["error"]["code"] == ask.UNAUTHENTICATED


def test_wrongly_signed_refused(env):
    r = _ask(env, priv=STRANGER_PRIV)  # claims to be the pinned peer, signed by another key
    assert r.status_code == 401 and "invalid_signature" in r.json()["error"]["message"]


def test_expired_refused(env):
    r = _ask(env, ttl=-5)
    assert r.status_code == 401 and "expired" in r.json()["error"]["message"]


def test_overlong_token_refused(env):
    r = _ask(env, ttl=86400)
    assert r.status_code == 401


def test_wrong_audience_refused(env):
    r = _ask(env, aud="someone-else")
    assert r.status_code == 401 and "aud_mismatch" in r.json()["error"]["message"]


def test_question_swap_refused(env):
    headers, body = _signed("harmless question")
    body["params"]["message"]["parts"][0]["text"] = "a different question"
    r = env.client.post("/v1/ask", json=body, headers=headers)
    assert r.status_code == 401 and "hash" in r.json()["error"]["message"]


def test_replay_refused(env):
    headers, body = _signed("q")
    assert env.client.post("/v1/ask", json=body, headers=headers).status_code == 200
    r = env.client.post("/v1/ask", json=body, headers=headers)
    assert r.status_code == 401 and "replay" in r.json()["error"]["message"]


def test_unknown_peer_refused_when_public_asking_off(env):
    r = _ask(env, priv=STRANGER_PRIV, iss="stranger", public_key=STRANGER_PUB)
    assert r.status_code == 403 and r.json()["error"]["message"] == "unknown_peer"


def test_unknown_peer_allowed_when_public_asking_on(env, monkeypatch):
    monkeypatch.setattr(settings_store, "get_ask_public_enabled", lambda: True)
    assert _ask(env, priv=STRANGER_PRIV, iss="stranger", public_key=STRANGER_PUB).status_code == 200
    # a pinned peer's name cannot be borrowed with a self-supplied key
    r = _ask(env, priv=STRANGER_PRIV, iss=PEER, public_key=STRANGER_PUB)
    assert r.status_code == 401


def test_degraded_peer_refused_unless_public(env, monkeypatch):
    monkeypatch.setenv("FEDERATION_SUBSTRATE_GATE", "on")

    async def floor(**kw):
        return substrate.FloorResult(ok=False, code="substrate_floor_not_met", details={})
    monkeypatch.setattr(substrate, "fetch_and_check_peer", floor)
    r = _ask(env)
    assert r.status_code == 403 and "degraded_peer" in r.json()["error"]["message"]
    monkeypatch.setattr(settings_store, "get_ask_public_enabled", lambda: True)
    assert _ask(env).status_code == 200


def test_not_message_send(env):
    headers, body = _signed("q")
    body["method"] = "tasks/get"
    r = env.client.post("/v1/ask", json=body, headers=headers)
    assert r.json()["error"]["code"] == ask.METHOD_NOT_FOUND


# ── scope ────────────────────────────────────────────────────────────────────

def test_private_scope_never_returned(env):
    r = _ask(env)
    text = json.dumps(r.json())
    for secret in ("INTERNAL SECRET", "PRIVATE SECRET", "UNSCOPED SECRET",
                   "team-plan", "diary/2026", "unscoped.md"):
        assert secret not in text
    assert env.seen == {"scope": "public", "allow_local_only": False, "architecture": "flat"}


def test_no_public_memory_no_model(env, monkeypatch):
    monkeypatch.setattr(m, "search_similar_documents",
                        lambda *a, **k: [d for d in DOCS if d["metadata"].get("scope") != "public"])

    async def boom(*a, **k):
        raise AssertionError("model must not run without public memory")
    monkeypatch.setattr(m._providers, "complete", boom)
    res = _ask(env).json()["result"]
    assert res["parts"][0]["text"] == ask.NO_ANSWER and res["parts"][1]["data"]["citations"] == []


# ── rate limit + audit ───────────────────────────────────────────────────────

def test_rate_limited_per_peer(env, monkeypatch):
    monkeypatch.setattr(env.limiter, "max_hits", 2)
    assert _ask(env, question="q1").status_code == 200
    assert _ask(env, question="q2").status_code == 200
    r = _ask(env, question="q3")
    assert r.status_code == 429 and r.json()["error"]["code"] == ask.RATE_LIMITED
    assert r.headers.get("Retry-After") == "42"
    assert "ask:peer:brain-a" in " ".join(env.limiter._client.d)


def test_every_ask_audited(env):
    _ask(env, question="audited one")
    env.client.post("/v1/ask", json=_signed("unsigned one")[1])
    entries = env.audit.tail(10)
    assert [e["surface"] for e in entries] == ["ask", "ask"]
    ok, refused = entries
    assert ok["peer_brain_id"] == PEER and ok["outcome"] == "ok" and ok["verified"] is True
    assert refused["outcome"].startswith("refused:") and refused["verified"] is False


# ── client ───────────────────────────────────────────────────────────────────

def test_client_request_accepted(env):
    card = env.client.get("/.well-known/agent-card.json").json()
    audience = ask_brain.audience_from_card(card)
    assert audience == THIS
    headers, body = ask_brain.build_request(question="What do tides follow?", audience=audience,
                                            private_key=PEER_PRIV, my_id=PEER)
    r = env.client.post("/v1/ask", json=body, headers=headers)
    assert r.status_code == 200
    text, cites = ask_brain.answer_of(r.json())
    assert "PUBLIC FACT" in text and cites == ["notes/public-essay.md"]
