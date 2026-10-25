"""
Radio subscribe token (2026-10-25): the taste note a brain hands to a radio station.

The brain decides what it says. It searches its own memory (open chunks only, the
closed view: the note leaves the box), reduces the hits to a short plain-text
note, and signs it as a federation assertion addressed to the station. The
station verifies the signature against GET /identity and renders from the note;
the memory itself never leaves. Pure functions here; the route is in main.py.
"""
import re
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote

from api.identity.core import issue_federation_assertion

QUERIES = ["music I like, artists, genres, tracks, DJ sets, loops"]
TOP_CHUNKS = 8
TASTE_MAX = 600
NO_MUSIC = "no music memory yet"
AUDIENCE = "orfeo.music"
SUBJECT = "radio.subscribe"
TTL_SECONDS = 600

_GENRES = (
    "ambient techno house minimal trance dnb jungle dubstep "
    "garage breakbeat electro electronica idm downtempo rap r&b soul funk jazz "
    "blues rock indie punk metal folk classical baroque opera pop disco synthwave lo-fi lofi "
    "dub reggae afrobeat latin cumbia drone noise experimental industrial "
    "chillout psytrance hardstyle grime"
).split()
_GENRE_PHRASES = [
    "deep house", "tech house", "drum and bass", "trip hop", "hip hop", "bossa nova",
    "uk garage", "world music",
]
_INSTRUMENTS = (
    "piano synth synthesizer guitar bass drums violin cello saxophone trumpet flute organ "
    "modular sampler vocals voice strings harp"
).split()
_MOODS = (
    "dark warm melancholic euphoric driving hypnotic uplifting calm dreamy aggressive "
    "nocturnal groovy minimal atmospheric lush raw slow fast"
).split()
_MUSIC_WORDS = {"music", "artist", "artists", "track", "tracks", "dj", "set", "sets", "loop", "loops",
                "genre", "genres", "song", "songs", "album", "albums", "listen", "listening"}
# "Artist - Title" or "by Name" or "artists: A, B"
_NAME = r"[A-Z][\w'&.-]+(?:\s+[A-Z][\w'&.-]+){0,3}"
_BY = re.compile(r"\b(?i:by|artists?|listen(?:ing)? to|fan of|love|like)\s*:?\s+"
                 rf"({_NAME}(?:\s*(?:,|and|&)\s+{_NAME})*)")


def _text_of(chunk: Dict[str, Any]) -> str:
    return str(chunk.get("content") or chunk.get("text") or chunk.get("chunk") or "")


def build_taste(chunks: List[Dict[str, Any]], max_chars: int = TASTE_MAX) -> str:
    """Reduce memory chunks to a plain-text taste note: artists, genres, moods, instruments."""
    text = "\n".join(_text_of(c) for c in (chunks or []))
    low = text.lower()
    if not text.strip() or not (set(re.findall(r"[a-z]+", low)) & _MUSIC_WORDS
                                or any(g in low for g in _GENRE_PHRASES)
                                or any(re.search(rf"\b{re.escape(g)}\b", low) for g in _GENRES)):
        return NO_MUSIC

    def found(words, phrases=()):
        out: List[str] = []
        for p in list(phrases) + list(words):
            if re.search(rf"(?<![a-z]){re.escape(p)}(?![a-z])", low) and not any(p in o for o in out):
                out.append(p)
        return out

    genres = found(_GENRES, _GENRE_PHRASES)
    moods = found(_MOODS)
    instruments = found(_INSTRUMENTS)
    artists: List[str] = []
    for m in _BY.finditer(text):
        for name in re.split(r"\s*(?:,|\band\b|&)\s*", m.group(1)):
            name = name.strip(" .,'-")
            if name and name.lower() not in {a.lower() for a in artists} and name.lower() not in _MUSIC_WORDS:
                artists.append(name)
    parts = []
    if artists:
        parts.append("artists: " + ", ".join(artists[:12]))
    if genres:
        parts.append("genres: " + ", ".join(genres[:12]))
    if moods:
        parts.append("moods: " + ", ".join(moods[:8]))
    if instruments:
        parts.append("instruments: " + ", ".join(instruments[:8]))
    if not parts:
        return NO_MUSIC
    return "; ".join(parts)[:max_chars].strip()


def collect_taste(search: Callable[..., List[Dict[str, Any]]]) -> str:
    """Run the brain's own memory search (open chunks only) and build the note."""
    chunks: List[Dict[str, Any]] = []
    for q in QUERIES:
        chunks.extend(search(q, TOP_CHUNKS, allow_local_only=False) or [])
    return build_taste(chunks[:TOP_CHUNKS])


def normalise_station(station: Optional[str]) -> str:
    s = (station or "https://orfeo.music").strip().rstrip("/")
    if not s.startswith("https://"):
        raise ValueError("station must be an https URL")
    return s


def issue_token(*, taste: str, private_key: str, brain_id: str, endpoint: str) -> str:
    return issue_federation_assertion(
        private_key_b64=private_key,
        issuer_brain_id=brain_id,
        audience_brain_id=AUDIENCE,
        subject=SUBJECT,
        ttl_seconds=TTL_SECONDS,
        claims={"taste": taste[:TASTE_MAX], "issuer_endpoint": endpoint},
    )


def station_url(station: str, token: str) -> str:
    return f"{station}/radio?token={quote(token, safe='')}"


# ─── The first harmonics event (2026-10-25) ─────────────────────────────────
# After issuing the token the brain performs the exchange itself: it posts the token to the
# station, gets the sequence and the station's receipt, scores taste against the station's
# render with the harmonics module's own coherence(), and appends one ledger row. Never money.

import base64
import hashlib
import json
import time

import httpx

UNSIGNED_PEER = "orfeo.music:unsigned"
CONTEXT_TRACKS = 12
HTTP_TIMEOUT = 10.0


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _http_get(url: str) -> httpx.Response:
    return httpx.get(url, timeout=HTTP_TIMEOUT, follow_redirects=False)


def _http_post(url: str, body: Dict[str, Any]) -> httpx.Response:
    return httpx.post(url, json=body, timeout=HTTP_TIMEOUT, follow_redirects=False)


def build_context(sequence: List[str], tracks: List[Dict[str, Any]], n: int = CONTEXT_TRACKS) -> str:
    """R: the ordered 'title - artist' of the first n tracks of the returned sequence, joined by ' | '."""
    by_id = {str(t.get("id")): t for t in tracks or []}
    parts = []
    for tid in (sequence or [])[:n]:
        t = by_id.get(str(tid))
        if not t:
            continue
        title, artist = str(t.get("title") or "").strip(), str(t.get("artist") or t.get("channel") or "").strip()
        parts.append(f"{title} - {artist}" if artist else title)
    return " | ".join(parts)


def receipt_content_hash(taste: str, context: str) -> str:
    """The hash the station puts in its receipt: sha256 hex of taste + ' | ' + R."""
    return hashlib.sha256((taste + " | " + context).encode("utf-8")).hexdigest()


def verify_receipt(receipt: Any, public_key_b64: str, *, brain_id: str, jti: str, n: int,
                   taste: str, context: str) -> Dict[str, Any]:
    """Check the station's receipt. Returns {ok, reason, hash_match}.

    ok needs a valid ED25519 signature by the station's published key, typ RADIO_RECEIPT,
    iss orfeo.music, and brain_id, jti and n equal to this exchange. hash_match reports
    whether the receipt's content_hash equals our own taste + R hash; a mismatch does not
    void the receipt (the two sides may order R differently) but is recorded."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    if not isinstance(receipt, dict) or not isinstance(receipt.get("payload"), dict) or not receipt.get("sig"):
        return {"ok": False, "reason": "receipt malformed", "hash_match": False}
    payload, sig = receipt["payload"], str(receipt["sig"])
    if sig.startswith("ed25519:"):
        sig = sig[len("ed25519:"):]
    try:
        pub = Ed25519PublicKey.from_public_bytes(_b64d(public_key_b64))
        raw = _b64d(sig)
    except Exception:
        return {"ok": False, "reason": "receipt key or signature unreadable", "hash_match": False}
    signed = False
    # The station's canonical form is not fixed by the contract: accept sorted-key compact JSON
    # (the harmonics module's form) or compact JSON in the payload's own key order.
    for data in (json.dumps(payload, separators=(",", ":"), sort_keys=True),
                 json.dumps(payload, separators=(",", ":"))):
        try:
            pub.verify(raw, data.encode("utf-8"))
            signed = True
            break
        except Exception:
            continue
    if not signed:
        return {"ok": False, "reason": "receipt signature invalid", "hash_match": False}
    if payload.get("typ") != "RADIO_RECEIPT" or payload.get("iss") != AUDIENCE:
        return {"ok": False, "reason": "receipt is not an orfeo.music radio receipt", "hash_match": False}
    if payload.get("brain_id") != brain_id or payload.get("jti") != jti or payload.get("n") != n:
        return {"ok": False, "reason": "receipt is for another exchange", "hash_match": False}
    h = str(payload.get("content_hash") or "")
    h = h[len("sha256:"):] if h.startswith("sha256:") else h
    return {"ok": True, "reason": "", "hash_match": h == receipt_content_hash(taste, context)}


def _token_jti(token: str) -> str:
    try:
        return str(json.loads(_b64d(token.split(".")[1])).get("jti") or "")
    except Exception:
        return ""


def run_listen_event(*, station: str, token: str, taste: str, brain_id: str,
                     http_get: Optional[Callable] = None, http_post: Optional[Callable] = None) -> Dict[str, Any]:
    """Perform the exchange and write the ledger row. Returns the route's `event` value:
    {score, cos, sin, standing_after, receipt, ...} or {"event": None, "reason": ...}. Never raises."""
    http_get, http_post = http_get or _http_get, http_post or _http_post

    def fail(reason: str) -> Dict[str, Any]:
        return {"event": None, "reason": reason}

    try:
        r = http_post(f"{station}/api/radio/subscribe", {"token": token})
        if r.status_code != 200:
            return fail(f"station answered {r.status_code}")
        body = r.json()
        if body.get("render") != "personal" or not isinstance(body.get("sequence"), list):
            return fail(f"station did not render: {body.get('reason') or body.get('render')}")
        sequence = [str(x) for x in body["sequence"]]
        lib = http_get(f"{station}/api/radio/library")
        if lib.status_code != 200:
            return fail(f"station library answered {lib.status_code}")
        context = build_context(sequence, lib.json().get("tracks") or [])
        if not context:
            return fail("station sequence matched no track in its library")
        pubkey, receipt_state, receipt = None, "none", body.get("receipt")
        ident = http_get(f"{station}/api/radio/identity")
        if ident.status_code == 200:
            pubkey = ident.json().get("public_key") or None
        check = {"ok": False, "reason": "station has no receipt key", "hash_match": False}
        if receipt and pubkey:
            check = verify_receipt(receipt, pubkey, brain_id=brain_id, jti=_token_jti(token),
                                   n=len(sequence), taste=taste, context=context)
            receipt_state = "verified" if check["ok"] else "refused: " + check["reason"]
        elif receipt:
            receipt_state = "refused: station publishes no key"
        from api import harmonics as h
        cos, sin, score = h.coherence(taste, context)
        ch = h.content_hash(taste, context)
        verified = bool(receipt and pubkey and check["ok"])
        h.record_event(
            peer_pubkey=pubkey if verified else UNSIGNED_PEER,
            role="contributor", cos=cos, sin=sin, score=score, content_hash=ch,
            event_timestamp=int(time.time()),
            peer_sig=receipt["sig"] if verified else None,
            peer_payload=json.dumps(receipt["payload"], separators=(",", ":")) if verified else None,
        )
        return {"event": {"score": score, "cos": cos, "sin": sin, "standing_after": h.standing(),
                          "receipt": receipt_state, "receipt_hash_match": bool(check.get("hash_match"))}}
    except Exception as e:
        return fail(f"{type(e).__name__}: {e}"[:200])
