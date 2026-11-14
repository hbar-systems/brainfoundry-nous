"""Telegram pairing (2026-11-14): a bot belongs to the chat that sends the one-time code made in
the console, never to whoever writes first. Both bots: the brain's (api/integrations/telegram.py,
webhook in api/main.py) and the bridge's (scripts/cc/cc_extras.py Telegram, scripts/cc/cc-bridge.py).

Run from repo root:
    pytest tests/test_telegram_pairing.py -v
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import tempfile
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
_RUNTIME = tempfile.mkdtemp(prefix="tg-pair-test-")
os.environ.setdefault("BRAIN_RUNTIME_DIR", _RUNTIME)
os.environ.setdefault("SETTINGS_PATH", os.path.join(_RUNTIME, "settings.json"))

from fastapi.testclient import TestClient  # noqa: E402

from api import main as m  # noqa: E402
from api.integrations import telegram  # noqa: E402

_spec = importlib.util.spec_from_file_location("cc_extras", ROOT / "scripts" / "cc" / "cc_extras.py")
X = importlib.util.module_from_spec(_spec); sys.modules.setdefault("cc_extras", X); _spec.loader.exec_module(X)


# ---------------------------------------------------------------- the bridge's bot (pure)

def _bridge_tg(tmp_path, owner=""):
    return X.Telegram("tok", tmp_path / "tg.json", owner=owner, api=lambda *a, **k: {"ok": True})


def test_bridge_no_owner_until_the_code(tmp_path):
    tg = _bridge_tg(tmp_path)
    assert tg.owner() is None and tg.try_pair(42, "hello") is None
    assert tg.try_pair(42, "/pair 123456") == "expired" and tg.owner() is None
    out = tg.new_pair_code(now=1000)
    assert out["ok"] and len(out["code"]) == 6 and out["code"].isdigit() and out["expires_at"] == 1600
    st = json.loads((tmp_path / "tg.json").read_text())
    assert out["code"] not in json.dumps(st), "the code itself must never be stored"
    assert tg.pair_pending(now=1100)
    assert tg.try_pair(42, f"/start {out['code']}", now=1100) == "paired" and tg.owner_ok(42)
    # once only
    assert tg.try_pair(43, f"/pair {out['code']}", now=1101) == "expired" and tg.owner_ok(42)


def test_bridge_code_expires_and_wrong_codes_burn_it(tmp_path):
    tg = _bridge_tg(tmp_path)
    code = tg.new_pair_code(now=0)["code"]
    assert tg.try_pair(42, f"/pair {code}", now=601) == "expired" and tg.owner() is None
    code = tg.new_pair_code(now=0)["code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(X.Telegram.PAIR_TRIES - 1):
        assert tg.try_pair(99, f"/pair {wrong}", now=1) == "wrong"
    assert tg.pair_pending(now=1)
    assert tg.try_pair(99, f"/pair {wrong}", now=1) == "wrong" and not tg.pair_pending(now=1)
    assert tg.try_pair(42, f"/pair {code}", now=2) == "expired" and tg.owner() is None


def test_bridge_new_phone_moves_ownership_and_unpair_clears(tmp_path):
    tg = _bridge_tg(tmp_path)
    tg.pin(42)                                   # an owner pinned before pairing existed stays
    assert tg.owner_ok(42)
    code = tg.new_pair_code(now=0)["code"]
    assert tg.try_pair(77, f"/pair@mybot {code}", now=5) == "paired" and tg.owner_ok(77) and not tg.owner_ok(42)
    assert tg.unpair() == {"ok": True} and tg.owner() is None


def test_bridge_forced_owner_cannot_be_moved(tmp_path):
    tg = _bridge_tg(tmp_path, owner="77")
    assert tg.new_pair_code()["ok"] is False and tg.unpair()["ok"] is False
    assert tg.try_pair(42, "/pair 123456") == "expired" and tg.owner_ok(77)


# ---------------------------------------------------------------- the brain's bot

@pytest.fixture
def store(monkeypatch):
    data: dict = {"token": "t", "username": "mybot", "webhook_secret": "s3cret"}
    monkeypatch.setattr(telegram.settings_store, "get_telegram", lambda: dict(data))
    monkeypatch.setattr(telegram.settings_store, "set_telegram", lambda d: data.update(d))
    return data


def test_brain_code_lifecycle(store):
    assert telegram.try_pair(1, "hi") is None
    out = telegram.new_pair_code(now=0)
    assert out["link"] == f"https://t.me/mybot?start={out['code']}" and out["code"] not in json.dumps(store)
    assert telegram.status()["pair_pending"] in (True, False)  # wall clock; shape only
    assert telegram.try_pair(5, f"/pair {out['code']}", now=10) == "paired" and store["owner_chat_id"] == 5
    assert telegram.try_pair(6, f"/pair {out['code']}", now=11) == "expired" and store["owner_chat_id"] == 5
    telegram.unpair()
    assert store["owner_chat_id"] is None and telegram.status()["owner_pinned"] is False


def test_brain_wrong_codes_burn(store):
    code = telegram.new_pair_code(now=0)["code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(telegram.PAIR_TRIES):
        assert telegram.try_pair(9, f"/pair {wrong}", now=1) == "wrong"
    assert telegram.try_pair(9, f"/pair {code}", now=2) == "expired" and store.get("owner_chat_id") is None


def _hook(client, chat_id, text):
    return client.post("/integrations/telegram/webhook", headers={"x-telegram-bot-api-secret-token": "s3cret"},
                       json={"message": {"chat": {"id": chat_id}, "text": text}})


def test_webhook_first_chat_no_longer_owns_the_bot(store, monkeypatch):
    sent = []

    async def fake_send(chat_id, text):
        sent.append((chat_id, text))

    async def fake_answer(q):
        return "from memory: " + q

    monkeypatch.setattr(telegram, "send_message", fake_send)
    monkeypatch.setattr(telegram, "answer", fake_answer)
    c = TestClient(m.app)
    # a stranger writes first: nothing is pinned, nothing is answered from memory
    assert _hook(c, 666, "what do you know?").status_code == 200
    assert store.get("owner_chat_id") is None and sent[-1] == (666, "This brain is private.")
    # the owner pairs with the console's code
    code = telegram.new_pair_code()["code"]
    _hook(c, 5, f"/start {code}")
    assert store["owner_chat_id"] == 5 and sent[-1][1].startswith("Paired.")
    _hook(c, 5, "hello")
    assert sent[-1] == (5, "from memory: hello")
    _hook(c, 666, "hello")
    assert sent[-1] == (666, "This brain is private.")
    # a stale code from the owner is not a question for the reasoner
    _hook(c, 5, "/pair 123456")
    assert "wrong or expired" in sent[-1][1] and store["owner_chat_id"] == 5


def test_pair_routes_need_the_key(store, monkeypatch):
    monkeypatch.setattr(m, "BRAIN_API_KEY", "owner-key")
    c = TestClient(m.app)
    for path in ("/integrations/telegram/pair-code", "/integrations/telegram/unpair"):
        assert c.post(path).status_code == 401
        assert c.post(path, headers={"X-API-Key": "wrong"}).status_code == 401
    r = c.post("/integrations/telegram/pair-code", headers={"X-API-Key": "owner-key"})
    assert r.status_code == 200 and len(r.json()["code"]) == 6
