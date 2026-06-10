"""
api/integrations/telegram.py — chat with the brain from Telegram.

The operator creates a bot with @BotFather, pastes the token; the brain registers
a webhook (https://<public-api>/integrations/telegram/webhook) protected by a
secret token, and answers incoming messages from its own memory + reasoner.

Privacy: the bot only answers the FIRST chat that messages it (pinned as the
owner) — a stranger who finds the bot is refused. Read/answer only; it never
takes actions from a Telegram message.
"""
from __future__ import annotations

import os
import secrets as _secrets
from typing import Any, Dict, Optional

import httpx

from api import settings_store

_API = "https://api.telegram.org/bot{token}/{method}"


def _token() -> str:
    return settings_store.get_telegram().get("token", "")


def is_configured() -> bool:
    return bool(_token())


def status() -> Dict[str, Any]:
    t = settings_store.get_telegram()
    return {
        "configured": bool(t.get("token")),
        "username": t.get("username"),
        "owner_chat_id": t.get("owner_chat_id"),
    }


def webhook_url() -> str:
    base = os.getenv("PUBLIC_API_BASE", "https://hbar.brainfoundry.ai").rstrip("/")
    return f"{base}/integrations/telegram/webhook"


async def _call(method: str, **params) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=30)) as http:
        r = await http.post(_API.format(token=_token(), method=method), json=params)
        return r.json()


async def get_me() -> Dict[str, Any]:
    return await _call("getMe")


async def send_message(chat_id, text: str) -> Dict[str, Any]:
    return await _call("sendMessage", chat_id=chat_id, text=text[:4000])


async def connect(token: str) -> Dict[str, Any]:
    """Store the token, validate it, register the webhook. Returns status/error."""
    settings_store.set_telegram({"token": token.strip()})
    me = await get_me()
    if not me.get("ok"):
        settings_store.clear_telegram()
        return {"ok": False, "error": "Invalid bot token (Telegram rejected getMe)."}
    username = (me.get("result") or {}).get("username")
    secret = _secrets.token_urlsafe(24)
    settings_store.set_telegram({"username": username, "webhook_secret": secret})
    hook = await _call("setWebhook", url=webhook_url(), secret_token=secret,
                       allowed_updates=["message"])
    if not hook.get("ok"):
        return {"ok": False, "error": f"setWebhook failed: {hook.get('description')}", "username": username}
    return {"ok": True, "username": username}


async def disconnect() -> None:
    try:
        await _call("deleteWebhook")
    except Exception:
        pass
    settings_store.clear_telegram()


def verify_secret(header_value: Optional[str]) -> bool:
    expected = settings_store.get_telegram().get("webhook_secret")
    return bool(expected) and header_value == expected


def owner_chat_id():
    return settings_store.get_telegram().get("owner_chat_id")


def pin_owner(chat_id) -> None:
    settings_store.set_telegram({"owner_chat_id": chat_id})


async def answer(query: str) -> str:
    """Answer a message from the brain's memory + reasoner (flat RAG + the
    default model). Kept simple: no agentic tools over the Telegram surface."""
    from api import main as _m
    from api import providers as _providers
    model = _providers.default_model()
    prompt, _docs = _m._build_rag_prompt(
        [{"role": "user", "content": query}], query, [], 5, model=model)
    try:
        return await _providers.complete(model, [{"role": "user", "content": prompt}])
    except Exception as e:
        return f"(sorry — the brain hit an error: {e})"
