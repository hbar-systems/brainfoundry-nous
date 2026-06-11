"""
api/integrations/calendar_ics.py — read upcoming events from an ICS calendar feed.

The simple, no-OAuth path (parallels IMAP email): the operator pastes the private
"secret iCal URL" their calendar already exposes — Google Calendar (Settings →
"Secret address in iCal format"), Outlook, iCloud, Fastmail, Nextcloud all offer
one. The brain fetches that URL and parses the VEVENTs. Read-only by nature.

SSRF-guarded (operator-set, but still validated): http(s) only, public host only.
"""
from __future__ import annotations

import asyncio
import datetime
import ipaddress
import socket
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx

from api import settings_store

_MAX_BYTES = 4_000_000


def is_configured() -> bool:
    return bool(settings_store.get_calendar_ics())


def status() -> Dict[str, Any]:
    url = settings_store.get_calendar_ics()
    host = urlparse(url).hostname if url else None
    return {"configured": bool(url), "host": host}


def _public(host: str) -> bool:
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return False
        return True
    except Exception:
        return False


def _unfold(text: str) -> str:
    # ICS line folding: a CRLF followed by space/tab continues the previous line.
    return (text.replace("\r\n ", "").replace("\r\n\t", "")
                .replace("\n ", "").replace("\n\t", ""))


def _parse_dt(value: str, key: str):
    """Parse an ICS DTSTART value → (datetime|date, iso_string). Best-effort."""
    v = value.strip()
    try:
        if "VALUE=DATE" in key or (len(v) == 8 and v.isdigit()):
            d = datetime.datetime.strptime(v[:8], "%Y%m%d").date()
            return d, d.isoformat()
        if v.endswith("Z"):
            dt = datetime.datetime.strptime(v, "%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc)
            return dt, dt.isoformat()
        dt = datetime.datetime.strptime(v[:15], "%Y%m%dT%H%M%S")
        return dt, dt.isoformat()
    except Exception:
        return None, v


def _to_utc(dt):
    if isinstance(dt, datetime.datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)
    if isinstance(dt, datetime.date):
        return datetime.datetime(dt.year, dt.month, dt.day, tzinfo=datetime.timezone.utc)
    return None


def _parse_events(ics: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    cur = None
    for line in _unfold(ics).splitlines():
        if line.startswith("BEGIN:VEVENT"):
            cur = {}
        elif line.startswith("END:VEVENT"):
            if cur is not None:
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            key, _, val = line.partition(":")
            name = key.split(";")[0].upper()
            if name == "SUMMARY":
                cur["summary"] = val.replace("\\,", ",").replace("\\n", " ")
            elif name == "LOCATION":
                cur["location"] = val.replace("\\,", ",")
            elif name == "DTSTART":
                dt, iso = _parse_dt(val, key)
                cur["_dt"] = dt
                cur["start"] = iso
    return events


def _sync_list(url: str, max_results: int) -> List[Dict[str, Any]]:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname or not _public(p.hostname):
        raise RuntimeError("calendar URL must be a public http(s) address")
    with httpx.Client(timeout=httpx.Timeout(10, read=20), follow_redirects=True) as http:
        r = http.get(url, headers={"User-Agent": "brainfoundry-calendar/1.0"})
        r.raise_for_status()
        ics = r.content[:_MAX_BYTES].decode("utf-8", "replace")
    if "BEGIN:VCALENDAR" not in ics:
        raise RuntimeError(
            "that URL isn't an iCal feed (it returned a web page, not calendar data). "
            "In Google Calendar use Settings → your calendar → 'Secret address in "
            "iCal format' — the link that ends in .ics.")
    now = datetime.datetime.now(datetime.timezone.utc)
    upcoming = []
    for ev in _parse_events(ics):
        u = _to_utc(ev.get("_dt"))
        if u is None or u < now - datetime.timedelta(hours=12):
            continue
        upcoming.append({"summary": ev.get("summary", "(no title)"),
                         "start": ev.get("start", ""), "location": ev.get("location", ""),
                         "_sort": u})
    upcoming.sort(key=lambda e: e["_sort"])
    for e in upcoming:
        e.pop("_sort", None)
    return upcoming[:max_results]


async def list_events(max_results: int = 10) -> List[Dict[str, Any]]:
    url = settings_store.get_calendar_ics()
    if not url:
        raise RuntimeError("No calendar is connected")
    return await asyncio.to_thread(_sync_list, url, max(1, min(int(max_results), 25)))
