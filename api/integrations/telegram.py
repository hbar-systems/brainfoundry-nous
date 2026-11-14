"""
api/integrations/telegram.py — chat with the brain from Telegram.

The operator creates a bot with @BotFather, pastes the token; the brain registers
a webhook (https://<public-api>/integrations/telegram/webhook) protected by a
secret token, and answers incoming messages from its own memory + reasoner.

Privacy: the bot answers one chat, its owner. Since 2026-11-14 the owner is the chat that
sends the one-time pairing code made in the console (/pair 123456, or the link
t.me/<bot>?start=123456); before, it was the first chat that wrote. Everyone else is told
the brain is private. Read/answer only; it never
takes actions from a Telegram message.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets as _secrets
import time
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
        "owner_pinned": t.get("owner_chat_id") is not None,
        "pair_pending": pair_pending(),
    }


def webhook_url() -> str:
    """This brain's own webhook address. PUBLIC_API_BASE, else BRAIN_PUBLIC_URL; never a
    built-in host (audit 2026-11-13: the old fallback sent every brain's bot updates and
    webhook secret to another operator's server). Raises RuntimeError when neither is set."""
    base = (os.getenv("PUBLIC_API_BASE") or os.getenv("BRAIN_PUBLIC_URL") or "").strip().rstrip("/")
    if not base.startswith("https://"):
        raise RuntimeError("set BRAIN_PUBLIC_URL (or PUBLIC_API_BASE) to this brain's public "
                           "https address before connecting Telegram")
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
    try:
        hook_url = webhook_url()
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    settings_store.set_telegram({"token": token.strip()})
    me = await get_me()
    if not me.get("ok"):
        settings_store.clear_telegram()
        return {"ok": False, "error": "Invalid bot token (Telegram rejected getMe)."}
    username = (me.get("result") or {}).get("username")
    secret = _secrets.token_urlsafe(24)
    settings_store.set_telegram({"username": username, "webhook_secret": secret})
    hook = await _call("setWebhook", url=hook_url, secret_token=secret,
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


# ---- pairing (2026-11-14): same rule as the bridge's bot (scripts/cc/cc_extras.py) ----
PAIR_TTL = 600
PAIR_TRIES = 5
PAIR_RE = re.compile(r"^/(?:pair|start)(?:@\w+)?\s+(\d{6})\s*$")


def _pair_hash(code: str) -> str:
    return hashlib.sha256(("tg-pair:" + code).encode()).hexdigest()


def new_pair_code(now: Optional[float] = None) -> Dict[str, Any]:
    """A 6-digit code, valid PAIR_TTL seconds, once; only its hash is stored."""
    now = time.time() if now is None else now
    code = f"{_secrets.randbelow(10 ** 6):06d}"
    settings_store.set_telegram({"pair_hash": _pair_hash(code), "pair_expires": now + PAIR_TTL,
                                 "pair_tries": 0})
    out: Dict[str, Any] = {"ok": True, "code": code, "expires_at": now + PAIR_TTL}
    username = settings_store.get_telegram().get("username")
    if username:
        out["link"] = f"https://t.me/{username}?start={code}"
    return out


def pair_pending(now: Optional[float] = None) -> bool:
    t = settings_store.get_telegram()
    now = time.time() if now is None else now
    return bool(t.get("pair_hash")) and float(t.get("pair_expires") or 0) > now


def try_pair(chat_id, text: str, now: Optional[float] = None) -> Optional[str]:
    """None: not a pairing message. Else 'paired', 'expired' or 'wrong'. A valid code from
    another chat moves the ownership there (a new phone); PAIR_TRIES wrong codes burn it."""
    m = PAIR_RE.match((text or "").strip())
    if not m:
        return None
    clear = {"pair_hash": None, "pair_expires": None, "pair_tries": 0}
    if not pair_pending(now):
        settings_store.set_telegram(clear)
        return "expired"
    t = settings_store.get_telegram()
    if hmac.compare_digest(_pair_hash(m.group(1)), str(t.get("pair_hash") or "")):
        settings_store.set_telegram({"owner_chat_id": chat_id, **clear})
        return "paired"
    tries = int(t.get("pair_tries") or 0) + 1
    settings_store.set_telegram(clear if tries >= PAIR_TRIES else {"pair_tries": tries})
    return "wrong"


def unpair() -> None:
    settings_store.set_telegram({"owner_chat_id": None, "pair_hash": None, "pair_expires": None,
                                 "pair_tries": 0})


async def answer(query: str) -> str:
    """Answer a message from the brain's memory + reasoner (flat RAG + the
    default model). Kept simple: no agentic tools over the Telegram surface."""
    from api import main as _m
    from api import providers as _providers
    model = _providers.default_model()
    # Privacy gate: the answer travels through Telegram's servers, so this
    # surface gets the open view even when the reasoner is local.
    prompt, _docs = _m._build_rag_prompt(
        [{"role": "user", "content": query}], query, [], 5, model=model,
        allow_local_only=False)
    try:
        return await _providers.complete(model, [{"role": "user", "content": prompt}])
    except Exception as e:
        return f"(sorry — the brain hit an error: {e})"
