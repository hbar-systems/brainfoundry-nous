"""
Orfeo door (2026-11-03): this brain posts a loop or track to a radio station (orfeo.music).

The post is a federation assertion (sub orfeo.post, aud orfeo.music, 10 minutes) carrying the
title, kind, an https audio URL and the audio's sha256. The station verifies it against this
brain's GET /identity and keeps it pending until its owner approves. The route in main.py is
owner-gated; on a console brain the bridge raises a permit card before it calls the route.
"""
import re
from typing import Any, Callable, Dict, Optional

import httpx

from api.identity.core import issue_federation_assertion

AUDIENCE = "orfeo.music"
SUBJECT = "orfeo.post"
TTL_SECONDS = 600
HTTP_TIMEOUT = 10.0


def clean_post(p: Dict[str, Any]) -> Dict[str, Any]:
    """The claims the station accepts, checked the way it checks them. Raises ValueError."""
    kind = p.get("kind")
    if kind not in ("loop", "track"):
        raise ValueError("kind must be loop or track")
    title = str(p.get("title") or "").strip()
    if not title or len(title) > 120:
        raise ValueError("title missing or over 120 characters")
    url = str(p.get("audio_url") or "")
    if not url.startswith("https://") or len(url) > 2048:
        raise ValueError("audio_url must be https")
    sha = str(p.get("audio_sha256") or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("audio_sha256 must be 64 hex")
    out: Dict[str, Any] = {"kind": kind, "title": title, "audio_url": url, "audio_sha256": sha,
                           "note": str(p.get("note") or "")[:600]}
    for k, lo, hi in (("bpm", 20, 400), ("duration_s", 0, 7200)):
        v = p.get(k)
        if isinstance(v, (int, float)) and lo < v < hi:
            out[k] = v
    if isinstance(p.get("key"), str) and len(p["key"]) <= 12:
        out["key"] = p["key"]
    return out


def issue_post_token(*, post: Dict[str, Any], private_key: str, brain_id: str, endpoint: str) -> str:
    return issue_federation_assertion(
        private_key_b64=private_key, issuer_brain_id=brain_id, audience_brain_id=AUDIENCE,
        subject=SUBJECT, ttl_seconds=TTL_SECONDS, claims={**clean_post(post), "issuer_endpoint": endpoint},
    )


def normalise_station(station: Optional[str], allow_http: str = "") -> str:
    s = (station or "https://orfeo.music").strip().rstrip("/")
    if s.startswith("https://") or (allow_http and s == allow_http.rstrip("/")):
        return s
    raise ValueError("station must be an https URL")


def send(station: str, token: str, http_post: Optional[Callable] = None) -> Dict[str, Any]:
    """POST the token to the station. Returns {ok, status, id?, reason?}; never raises."""
    post = http_post or (lambda u, b: httpx.post(u, json=b, timeout=HTTP_TIMEOUT, follow_redirects=False))
    try:
        r = post(f"{station}/api/radio/post", {"token": token})
        try:
            body = r.json()
        except Exception:
            body = {}
        if r.status_code == 202 and body.get("ok"):
            return {"ok": True, "status": body.get("status", "pending"), "id": body.get("id")}
        return {"ok": False, "status": r.status_code, "reason": body.get("reason") or f"station answered {r.status_code}"}
    except Exception as e:
        return {"ok": False, "status": 0, "reason": f"{type(e).__name__}: {e}"[:200]}
