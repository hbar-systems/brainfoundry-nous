"""
api/integrations/email_imap.py — read the operator's email over IMAP.

The simple, provider-agnostic path (the Odysseus model): the operator gives a
host + email + app password — no OAuth, no cloud console. Works with Gmail
(imap.gmail.com + a Google App Password), Outlook, Fastmail, self-hosted, etc.

Read-only: we open the mailbox readonly and only fetch headers (From/Subject/
Date) + the server-provided preview. No send/delete path — sending would be a
RED-tier capability and is intentionally absent (THREAT_MODEL).

imaplib is blocking, so the connector runs in a worker thread (asyncio.to_thread)
and the tool layer awaits it — the chat event loop is never blocked.
"""
from __future__ import annotations

import asyncio
import email
import imaplib
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any, Dict, List

from api import settings_store

COMMON_HOSTS = {
    "gmail.com": "imap.gmail.com",
    "googlemail.com": "imap.gmail.com",
    "outlook.com": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com",
    "office365.com": "outlook.office365.com",
    "fastmail.com": "imap.fastmail.com",
    "icloud.com": "imap.mail.me.com",
    "yahoo.com": "imap.mail.yahoo.com",
}


def guess_host(user: str) -> str:
    domain = user.split("@")[-1].lower().strip() if "@" in (user or "") else ""
    return COMMON_HOSTS.get(domain, "")


def is_configured() -> bool:
    c = settings_store.get_email_account()
    return bool(c.get("imap_host") and c.get("imap_user") and c.get("imap_password"))


def status() -> Dict[str, Any]:
    c = settings_store.get_email_account()
    return {
        "configured": is_configured(),
        "user": c.get("imap_user"),
        "host": c.get("imap_host"),
        "port": c.get("imap_port", 993),
    }


def _decode(value: str) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _sync_list(query: str, max_results: int, unread_only: bool) -> List[Dict[str, Any]]:
    c = settings_store.get_email_account()
    host = c["imap_host"]
    port = int(c.get("imap_port", 993))
    use_ssl = c.get("imap_ssl", True)
    M = (imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port))
    try:
        M.login(c["imap_user"], c["imap_password"])
        M.select("INBOX", readonly=True)
        criteria: List[str] = ["UNSEEN"] if unread_only else ["ALL"]
        # Server-side TEXT search only for ASCII terms — imaplib ASCII-encodes
        # search args (non-ASCII -> UnicodeEncodeError), and a raw double-quote
        # would break IMAP token framing. Strip quotes; skip search if non-ASCII.
        q = (query or "").replace('"', " ").replace("\\", " ").strip()
        if q and q.isascii():
            criteria = ["TEXT", f'"{q}"'] + (["UNSEEN"] if unread_only else [])
        typ, data = M.search(None, *criteria)
        ids = (data[0].split() if data and data[0] else [])
        ids = ids[-max_results:][::-1]  # most recent first
        out: List[Dict[str, Any]] = []
        for mid in ids:
            typ, d = M.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)] FLAGS)")
            if typ != "OK" or not d:
                continue
            # FLAGS can land in any element of the multi-part FETCH response
            # (often a trailing bytes item AFTER the body literal), not d[0][0].
            # Collect every bytes fragment and the header literal across all parts.
            raw = b""
            flagblob = b""
            for part in d:
                if isinstance(part, tuple):
                    flagblob += part[0] or b""
                    if part[1]:
                        raw = part[1]
                elif isinstance(part, (bytes, bytearray)):
                    flagblob += bytes(part)
            flags = flagblob.decode("utf-8", "replace")
            msg = email.message_from_bytes(raw)
            from_name, from_addr = parseaddr(_decode(msg.get("From", "")))
            date_str = msg.get("Date", "")
            try:
                date_str = parsedate_to_datetime(date_str).isoformat()
            except Exception:
                pass
            out.append({
                "from": (f"{from_name} <{from_addr}>" if from_name else from_addr),
                "subject": _decode(msg.get("Subject", "(no subject)")),
                "date": date_str,
                "unread": "\\Seen" not in flags,
            })
        return out
    finally:
        try:
            M.logout()
        except Exception:
            pass


async def list_messages(query: str = "", max_results: int = 10,
                        unread_only: bool = False) -> List[Dict[str, Any]]:
    n = max(1, min(int(max_results), 25))
    return await asyncio.to_thread(_sync_list, query or "", n, unread_only)


async def verify() -> Dict[str, Any]:
    """Test the stored credentials by listing one message. Returns {ok, error?}."""
    try:
        await list_messages(max_results=1)
        return {"ok": True}
    except imaplib.IMAP4.error as e:
        return {"ok": False, "error": f"IMAP login failed: {e}. For Gmail/Outlook use an "
                "app password, not your normal password."}
    except Exception as e:
        return {"ok": False, "error": str(e)}
