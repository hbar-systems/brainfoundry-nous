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
