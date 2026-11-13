"""Telegram webhook and Google OAuth callback name this brain, never a built-in host (audit 2026-11-13)."""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.integrations import google, telegram  # noqa: E402


@pytest.fixture
def no_base(monkeypatch):
    monkeypatch.delenv("PUBLIC_API_BASE", raising=False)
    monkeypatch.delenv("BRAIN_PUBLIC_URL", raising=False)


def test_derived_from_brain_public_url(no_base, monkeypatch):
    monkeypatch.setenv("BRAIN_PUBLIC_URL", "https://x.example/")
    assert telegram.webhook_url() == "https://x.example/integrations/telegram/webhook"
    assert google.redirect_uri() == "https://x.example/integrations/google/callback"
    monkeypatch.setenv("PUBLIC_API_BASE", "https://api.x.example")
    assert telegram.webhook_url().startswith("https://api.x.example/")


def test_refused_without_an_address(no_base, monkeypatch):
    with pytest.raises(RuntimeError):
        telegram.webhook_url()
    assert google.redirect_uri() == ""
    with pytest.raises(RuntimeError):
        google.auth_url("state")
    calls = []

    async def fake_call(method, **params):
        calls.append(method)
        return {"ok": True, "result": {"username": "bot"}}

    monkeypatch.setattr(telegram, "_call", fake_call)
    monkeypatch.setattr(telegram.settings_store, "set_telegram", lambda d: calls.append("store"))
    out = asyncio.run(telegram.connect("123:abc"))
    assert out["ok"] is False and calls == []          # nothing stored, setWebhook never called


def test_no_vendor_host_in_source():
    for mod in (telegram, google):
        assert "hbar.brainfoundry.ai" not in open(mod.__file__).read()
