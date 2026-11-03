"""
Orfeo door (2026-11-03): api/orfeo_post.py, POST /v1/orfeo/post, and the bridge's card-first
/orfeo/post. Keys are generated here; the station is mocked; nothing leaves the process.

Run from repo root:
    pytest tests/test_orfeo_post.py -v
"""
import base64
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import threading
import time
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if "sentence_transformers" not in sys.modules:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        _st = types.ModuleType("sentence_transformers")
        _st.SentenceTransformer = object
        sys.modules["sentence_transformers"] = _st

os.environ.setdefault("BRAIN_IDENTITY_SECRET", "test-only-secret")
_RUNTIME = tempfile.mkdtemp(prefix="orfeo-post-test-")
os.environ.setdefault("BRAIN_RUNTIME_DIR", _RUNTIME)
os.environ.setdefault("SETTINGS_PATH", os.path.join(_RUNTIME, "settings.json"))

from api import orfeo_post as op  # noqa: E402
from api.identity.core import generate_brain_keypair, verify_federation_assertion  # noqa: E402

KEYS = generate_brain_keypair()
PRIV, PUB = KEYS[0], KEYS[1]
SHA = "b" * 64
POST = {"kind": "loop", "title": "night loop", "audio_url": "https://files.example.com/a.wav",
        "audio_sha256": SHA, "note": "four bars", "bpm": 124, "key": "8A"}


def _claims(token):
    c = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(c + "=" * (-len(c) % 4)))


def test_token_signed_for_orfeo_post():
    t = op.issue_post_token(post=POST, private_key=PRIV, brain_id="b1", endpoint="https://b1.example.com")
    c = verify_federation_assertion(public_key_b64=PUB, token=t, expected_audience="orfeo.music", expected_issuer="b1")
    assert c["sub"] == "orfeo.post" and c["title"] == "night loop" and c["audio_sha256"] == SHA
    assert c["issuer_endpoint"] == "https://b1.example.com" and c["exp"] - c["iat"] == 600
    other = generate_brain_keypair()[1]
    with pytest.raises(ValueError):
        verify_federation_assertion(public_key_b64=other, token=t, expected_audience="orfeo.music")


@pytest.mark.parametrize("bad", [{"kind": "album"}, {"title": ""}, {"audio_url": "http://x/a.wav"}, {"audio_sha256": "zz"}])
def test_clean_post_refuses(bad):
    with pytest.raises(ValueError):
        op.clean_post({**POST, **bad})


def test_station_must_be_https():
    assert op.normalise_station(None) == "https://orfeo.music"
    with pytest.raises(ValueError):
        op.normalise_station("http://127.0.0.1:3000")
    assert op.normalise_station("http://127.0.0.1:3000", "http://127.0.0.1:3000") == "http://127.0.0.1:3000"


class _R:
    def __init__(self, code, body):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


def test_send_reads_pending_and_refusal():
    assert op.send("https://s", "t", lambda u, b: _R(202, {"ok": True, "id": "x1", "status": "pending"})) == \
        {"ok": True, "status": "pending", "id": "x1"}
    r = op.send("https://s", "t", lambda u, b: _R(409, {"ok": False, "reason": "replay: this token was already used"}))
    assert r["ok"] is False and "replay" in r["reason"]


def test_route_signs_and_sends(monkeypatch):
    from fastapi.testclient import TestClient
    from api import main as m
    monkeypatch.setenv("BRAIN_PRIVATE_KEY", PRIV)
    monkeypatch.setenv("BRAIN_ID", "b1")
    monkeypatch.setenv("BRAIN_PUBLIC_URL", "https://b1.example.com")
    seen = {}

    def fake_send(station, token, http_post=None):
        seen["station"], seen["token"] = station, token
        return {"ok": True, "status": "pending", "id": "x1"}
    monkeypatch.setattr(op, "send", fake_send)
    m.app.dependency_overrides[m.get_api_key] = lambda: "owner"
    try:
        r = TestClient(m.app).post("/v1/orfeo/post", json=POST)
    finally:
        m.app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert r.json()["sent"]["status"] == "pending" and seen["station"] == "https://orfeo.music"
    assert _claims(seen["token"])["sub"] == "orfeo.post"


def test_route_owner_only():
    from fastapi.testclient import TestClient
    from api import main as m
    m.app.dependency_overrides.clear()
    r = TestClient(m.app).post("/v1/orfeo/post", json=POST)
    assert r.status_code in (401, 403, 503)          # no key, or no key configured: closed either way


# ---- the bridge: card first, never remembered ----

def _bridge(monkeypatch, tmp_path):
    pytest.importorskip("permitd")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.setenv("CC_BOX", "1")
    monkeypatch.setenv("CC_PERMIT_TTL", "5")
    monkeypatch.delenv("CC_POSTURE", raising=False)
    monkeypatch.delenv("ONE_SECRET", raising=False)
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    spec = importlib.util.spec_from_file_location("cc_bridge_orfeo", ROOT / "scripts" / "cc" / "cc-bridge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cc_bridge_orfeo"] = mod
    spec.loader.exec_module(mod)
    mod.BRAIN_API_KEY = "k"
    return mod


BODY = {**POST, "station": "https://orfeo.music"}


def test_bridge_key_never_remembered(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    aid, summary, ok = m._box_key("orfeo_post", BODY)
    assert aid == "orfeo_post" and ok is False and "night loop" in summary and "pending" in summary


def test_bridge_refusal_sends_nothing(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    calls = []
    code, d = m._orfeo_post(BODY, ask=lambda *a: {"behavior": "deny", "message": "the person refused this action"},
                            api=lambda *a: calls.append(a))
    assert code == 403 and not calls


def test_bridge_nobody_watching_sends_nothing(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    m.RUNS.clear()
    calls = []
    code, d = m._orfeo_post(BODY, api=lambda *a: calls.append(a))
    assert code == 403 and "watching" in d["error"] and not calls


def test_bridge_card_then_send(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    cards, calls, out = [], [], {}
    m.RUNS.clear(); run = m.Run(None, "post my loop"); m.RUNS[run.id] = run
    run.attach(lambda kind, payload: cards.append(payload) if kind == "ask" else None)

    def api(method, path, body):
        calls.append((method, path, body))
        return {"sent": {"ok": True, "status": "pending", "id": "x1"}}
    th = threading.Thread(target=lambda: out.setdefault("r", m._orfeo_post({**BODY, "run": run.id}, api=api)))
    th.start()
    for _ in range(50):
        if cards:
            break
        time.sleep(0.05)
    assert cards and cards[0]["method"] == "orfeo_post" and cards[0]["remember_ok"] is False
    assert not calls                                   # nothing signed or sent before the click
    pm = m.GATE.get(cards[0]["id"])
    assert m._run_permit(cards[0]["id"], pm)["ok"] is True
    m._box_settle(cards[0]["id"], "allow")
    th.join(3)
    assert out["r"][0] == 200 and out["r"][1]["status"] == "pending"
    assert calls and calls[0][1] == "/v1/orfeo/post"
