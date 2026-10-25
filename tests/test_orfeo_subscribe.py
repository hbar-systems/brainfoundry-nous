"""
Radio subscribe token (2026-10-25): POST /v1/radio/subscribe-token, api/radio_taste.py and
scripts/orfeo_subscribe.py. Memory search and keys are mocked; nothing leaves the process.
"""
import base64
import json
import os
import sys
import tempfile
import types

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
_RUNTIME = tempfile.mkdtemp(prefix="radio-test-")
os.environ.setdefault("BRAIN_RUNTIME_DIR", _RUNTIME)
os.environ.setdefault("SETTINGS_PATH", os.path.join(_RUNTIME, "settings.json"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api import main as m  # noqa: E402
from api import radio_taste as rt  # noqa: E402
from api.identity.core import generate_brain_keypair  # noqa: E402
from scripts import orfeo_subscribe  # noqa: E402

KEYS = generate_brain_keypair()
PRIV, PUB = KEYS[0], KEYS[1]
OWNER_KEY = "owner-key-test"
MUSIC = [{"content": "I love ambient and deep house. Listening to Burial and Jon Hopkins, "
                     "dark hypnotic sets with modular synth and piano."}]


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _parts(token):
    h, c, s = token.split(".")
    return json.loads(_b64d(h)), json.loads(_b64d(c)), _b64d(s), f"{h}.{c}".encode()


@pytest.fixture
def env(monkeypatch):
    seen = {"calls": []}
    result = {"docs": MUSIC}

    def fake_search(query, limit=5, layers=None, architecture=None, scope=None, allow_local_only=False):
        seen["calls"].append((query, limit, allow_local_only))
        return list(result["docs"])

    monkeypatch.setattr(m, "search_similar_documents", fake_search)
    monkeypatch.setattr(m, "BRAIN_API_KEY", OWNER_KEY)
    monkeypatch.setenv("BRAIN_ID", "test-brain")
    monkeypatch.setenv("BRAIN_PRIVATE_KEY", PRIV)
    monkeypatch.setenv("BRAIN_PUBLIC_URL", "https://b.example")
    return types.SimpleNamespace(client=TestClient(m.app), seen=seen, result=result)


def _post(env, body=None, key=OWNER_KEY):
    headers = {"X-API-Key": key} if key else {}
    return env.client.post("/v1/radio/subscribe-token", json=body or {}, headers=headers)


def test_token_is_signed_for_orfeo(env):
    r = _post(env)
    assert r.status_code == 200, r.text
    body = r.json()
    header, claims, sig, signed = _parts(body["token"])
    assert header == {"alg": "EdDSA", "typ": "BRAIN_FED_ASSERTION", "v": 1}
    assert claims["iss"] == "test-brain" and claims["aud"] == "orfeo.music"
    assert claims["sub"] == "radio.subscribe"
    assert claims["exp"] - claims["iat"] == 600
    assert claims["issuer_endpoint"] == "https://b.example"
    assert claims["taste"] == body["taste"] and len(claims["taste"]) <= 600
    Ed25519PublicKey.from_public_bytes(_b64d(PUB)).verify(sig, signed)  # raises if bad
    assert body["url"].startswith("https://orfeo.music/radio?token=")


def test_taste_comes_from_memory_open_chunks_only(env):
    taste = _post(env).json()["taste"]
    for word in ("ambient", "deep house", "Burial", "Jon Hopkins", "piano"):
        assert word in taste
    query, limit, allow_local = env.seen["calls"][0]
    assert "music I like" in query and limit == 8 and allow_local is False


def test_no_music_memory_still_issues_token(env):
    env.result["docs"] = [{"content": "Tax receipts for the flat, 2025 invoices."}]
    body = _post(env).json()
    assert body["taste"] == "no music memory yet"
    assert _parts(body["token"])[1]["taste"] == "no music memory yet"
    env.result["docs"] = []
    assert _post(env).json()["taste"] == "no music memory yet"


def test_taste_capped_at_600():
    long = [{"content": "artists: " + ", ".join(f"Artist{chr(65 + i % 26)}{'x' * 30}" for i in range(200))}]
    assert len(rt.build_taste(long + MUSIC)) <= 600


def test_custom_station(env):
    body = _post(env, {"station": "https://radio.example/"}).json()
    assert body["url"].startswith("https://radio.example/radio?token=")


def test_station_must_be_https(env):
    assert _post(env, {"station": "http://radio.example"}).status_code == 400


def test_owner_gated(env):
    assert _post(env, key="wrong").status_code in (401, 403)
    assert _post(env, key=None).status_code in (401, 403)


@pytest.mark.parametrize("missing", ["BRAIN_PRIVATE_KEY", "BRAIN_ID"])
def test_missing_identity_is_503(env, monkeypatch, missing):
    monkeypatch.delenv(missing)
    r = _post(env)
    assert r.status_code == 503 and missing in r.text


def test_no_public_https_url_is_503(env, monkeypatch):
    monkeypatch.delenv("BRAIN_PUBLIC_URL")
    r = _post(env)  # TestClient base is http://testserver
    assert r.status_code == 503 and "BRAIN_PUBLIC_URL" in r.text


def test_script_prints_url(monkeypatch, capsys):
    seen = {}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"url": "https://orfeo.music/radio?token=T", "taste": "x"}).encode()

    def fake_urlopen(req, timeout=0):
        seen["url"], seen["key"] = req.full_url, req.get_header("X-api-key")
        seen["body"] = json.loads(req.data)
        return Resp()

    monkeypatch.setenv("BRAIN_API_KEY", "k")
    monkeypatch.setattr(orfeo_subscribe.urllib.request, "urlopen", fake_urlopen)
    assert orfeo_subscribe.main(["--api", "http://x:1"]) == 0
    assert capsys.readouterr().out.strip() == "https://orfeo.music/radio?token=T"
    assert seen == {"url": "http://x:1/v1/radio/subscribe-token", "key": "k",
                    "body": {"station": "https://orfeo.music"}}


def test_script_needs_key(monkeypatch):
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    assert orfeo_subscribe.main([]) == 2
