"""
api/integrations/google.py — read-only Gmail + Calendar over OAuth.

The brain reads the operator's email and calendar so it can answer "what's on my
schedule" / "summarize my recent email" agentically. Read-only by design: scopes
are gmail.readonly + calendar.readonly, and there is no send/modify path — that
would be a RED-tier capability and is intentionally absent (THREAT_MODEL).

Setup (operator, one-time):
  1. Google Cloud console → enable Gmail API + Calendar API.
  2. OAuth consent screen → add yourself as a Test user (skips verification for
     these sensitive scopes).
  3. Create an OAuth Web client; redirect URI = <PUBLIC_API_BASE>/integrations/
     google/callback.
  4. Set GOOGLE_OAUTH_CLIENT_ID + GOOGLE_OAUTH_CLIENT_SECRET (env or sidecar).

The refresh token is held in the settings sidecar (settings_store), never
returned to any client. Access tokens are minted on demand from the refresh
token and never persisted.
"""
from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from api import settings_store

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
CALENDAR_EVENTS = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
GMAIL_MESSAGES = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "openid",
    "email",
]

# The capabilities this one Google connection grants — surfaced in the UI so it
# reads as distinct features, not one opaque "Google" blob.
CAPABILITIES = [
    {"key": "calendar", "label": "Calendar", "tool": "calendar_read", "desc": "upcoming events"},
    {"key": "gmail", "label": "Gmail", "tool": "gmail_read", "desc": "recent mail (with search)"},
    {"key": "drive", "label": "Drive", "tool": "drive_search", "desc": "find files by name or content"},
]


def _client() -> tuple[str, str]:
    return (os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip(),
            os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip())


def redirect_uri() -> str:
    base = os.getenv("PUBLIC_API_BASE", "https://hbar.brainfoundry.ai").rstrip("/")
    return f"{base}/integrations/google/callback"


def is_configured() -> bool:
    cid, cs = _client()
    return bool(cid and cs)


def is_connected() -> bool:
    return bool(settings_store.get_google_oauth().get("refresh_token"))


def status() -> Dict[str, Any]:
    info = settings_store.get_google_oauth()
    return {
        "configured": is_configured(),
        "connected": bool(info.get("refresh_token")),
        "email": info.get("email"),
        "connected_at": info.get("connected_at"),
        "redirect_uri": redirect_uri(),
        "capabilities": CAPABILITIES,
    }


def auth_url(state: str) -> str:
    cid, _ = _client()
    params = {
        "client_id": cid,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",          # force refresh_token on every connect
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> Dict[str, Any]:
    """Exchange an auth code for tokens; persist the refresh token + email."""
    cid, cs = _client()
    data = {
        "code": code,
        "client_id": cid,
        "client_secret": cs,
        "redirect_uri": redirect_uri(),
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=20)) as http:
        r = await http.post(TOKEN_URL, data=data)
        r.raise_for_status()
        tok = r.json()
        email = None
        access = tok.get("access_token")
        if access:
            try:
                ui = await http.get(USERINFO_URL, headers={"Authorization": f"Bearer {access}"})
                if ui.status_code == 200:
                    email = ui.json().get("email")
            except Exception:
                pass
    refresh = tok.get("refresh_token")
    if not refresh:
        raise RuntimeError("Google did not return a refresh token (re-consent with "
                           "prompt=consent / access_type=offline).")
    info = {
        "refresh_token": refresh,
        "email": email,
        "scope": tok.get("scope"),
        "connected_at": int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
    }
    settings_store.set_google_oauth(info)
    return {"email": email}


async def _access_token() -> str:
    info = settings_store.get_google_oauth()
    refresh = info.get("refresh_token")
    if not refresh:
        raise RuntimeError("Google is not connected")
    cid, cs = _client()
    data = {
        "refresh_token": refresh,
        "client_id": cid,
        "client_secret": cs,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=20)) as http:
        r = await http.post(TOKEN_URL, data=data)
        r.raise_for_status()
        return r.json()["access_token"]


async def list_events(max_results: int = 10, time_min: Optional[str] = None) -> List[Dict[str, Any]]:
    """Upcoming events on the primary calendar (soonest first)."""
    at = await _access_token()
    tmin = time_min or datetime.datetime.now(datetime.timezone.utc).isoformat()
    params = {
        "maxResults": max(1, min(int(max_results), 25)),
        "orderBy": "startTime",
        "singleEvents": "true",
        "timeMin": tmin,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=20)) as http:
        r = await http.get(CALENDAR_EVENTS, headers={"Authorization": f"Bearer {at}"}, params=params)
        r.raise_for_status()
        items = r.json().get("items", [])
    out = []
    for ev in items:
        start = ev.get("start", {})
        out.append({
            "summary": ev.get("summary", "(no title)"),
            "start": start.get("dateTime") or start.get("date") or "",
            "location": ev.get("location", ""),
            "attendees": [a.get("email") for a in ev.get("attendees", []) if a.get("email")],
            "organizer": (ev.get("organizer") or {}).get("email", ""),
        })
    return out


async def list_messages(query: str = "", max_results: int = 10) -> List[Dict[str, Any]]:
    """Recent Gmail messages (metadata only — From/Subject/Date/snippet)."""
    at = await _access_token()
    headers = {"Authorization": f"Bearer {at}"}
    n = max(1, min(int(max_results), 20))
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=20)) as http:
        params: Dict[str, Any] = {"maxResults": n}
        if query:
            params["q"] = query
        r = await http.get(GMAIL_MESSAGES, headers=headers, params=params)
        r.raise_for_status()
        ids = [m["id"] for m in r.json().get("messages", [])][:n]
        msgs = []
        for mid in ids:
            rm = await http.get(
                f"{GMAIL_MESSAGES}/{mid}",
                headers=headers,
                params={"format": "metadata",
                        "metadataHeaders": ["From", "Subject", "Date"]},
            )
            if rm.status_code != 200:
                continue
            j = rm.json()
            hdrs = {h["name"]: h["value"] for h in j.get("payload", {}).get("headers", [])}
            msgs.append({
                "from": hdrs.get("From", ""),
                "subject": hdrs.get("Subject", "(no subject)"),
                "date": hdrs.get("Date", ""),
                "snippet": j.get("snippet", ""),
                "unread": "UNREAD" in (j.get("labelIds") or []),
            })
    return msgs


async def list_files(query: str = "", max_results: int = 10) -> List[Dict[str, Any]]:
    """Search the operator's Google Drive by name/content (most-recent first)."""
    at = await _access_token()
    n = max(1, min(int(max_results), 25))
    params: Dict[str, Any] = {
        "pageSize": n,
        "orderBy": "modifiedTime desc",
        "fields": "files(id,name,mimeType,modifiedTime,webViewLink,owners(displayName))",
        "spaces": "drive",
    }
    q = (query or "").strip().replace("\\", "\\\\").replace("'", "\\'")
    if q:
        params["q"] = f"(name contains '{q}' or fullText contains '{q}') and trashed = false"
    else:
        params["q"] = "trashed = false"
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=20)) as http:
        r = await http.get(DRIVE_FILES, headers={"Authorization": f"Bearer {at}"}, params=params)
        r.raise_for_status()
        files = r.json().get("files", [])
    out = []
    for f in files:
        mime = f.get("mimeType", "")
        kind = mime.split(".")[-1] if mime.startswith("application/vnd.google-apps") else mime
        out.append({
            "name": f.get("name", "(unnamed)"),
            "kind": kind,
            "modified": f.get("modifiedTime", ""),
            "link": f.get("webViewLink", ""),
            "owner": (f.get("owners") or [{}])[0].get("displayName", ""),
        })
    return out
