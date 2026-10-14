"""api/privacy.py — the memory privacy gate (2026-10-14).

Every memory chunk carries a privacy level in its metadata JSONB, next to
`layer` and `mem_type`:

  open        — the default. Any reasoner may read it (local Ollama, or a hosted
                API such as Anthropic, OpenAI, Groq).
  local-only  — only reasoners that run on hardware the owner controls may read
                it: the box's own Ollama (OLLAMA_URL) or an Ollama on a tailnet
                spoke (OLLAMA_SPOKE_URL).

A chunk with no `privacy` key is `open`, so brains that predate this change keep
working unchanged with no migration (scripts/migrate_privacy.py only adds the
index and is idempotent).

The rule is FAIL CLOSED at every step:
  - retrieval for a reasoner whose locality is unknown treats it as closed;
  - a closed retrieval keeps only chunks whose privacy is missing or exactly
    `open`, so a misspelt or future level is withheld, never leaked;
  - `search_similar_documents` defaults to the closed view, so a retrieval path
    that forgets to say who will read the result gets the safe answer.

Locality is decided from what the provider layer will actually call: a model is
local only if api.providers routes it to Ollama, it is not an Ollama cloud model
(`:cloud` / `-cloud` tags are forwarded by Ollama to ollama.com), and every
Ollama endpoint it could be sent to (OLLAMA_URL and, when set, OLLAMA_SPOKE_URL)
is on owner-controlled network space (a docker service name, localhost, a
private, link-local or tailnet address, a *.ts.net / *.local / *.internal name,
or a host the owner lists in PRIVACY_LOCAL_HOSTS).

Pure logic plus one optional call into api.providers; no DB, no network.
"""
from __future__ import annotations

import contextvars
import ipaddress
import os
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

OPEN = "open"
LOCAL_ONLY = "local-only"
LEVELS = (OPEN, LOCAL_ONLY)

# Accepted spellings on input, normalised to the canonical level before storage.
_ALIASES = {
    "open": OPEN,
    "local-only": LOCAL_ONLY,
    "local_only": LOCAL_ONLY,
    "localonly": LOCAL_ONLY,
    "local": LOCAL_ONLY,
}

# SQL fragment for a CLOSED retrieval: keep untagged and explicitly-open chunks,
# drop everything else (local-only, and any value this code does not know).
SQL_OPEN_ONLY = " AND COALESCE(metadata->>'privacy', 'open') = 'open'"


def normalize_level(value: Any, *, default: Optional[str] = OPEN) -> Optional[str]:
    """Canonical privacy level for an input value. None/'' -> `default`.
    Raises ValueError on an unknown level (the caller turns that into a 400)."""
    if value is None:
        return default
    s = str(value).strip().lower()
    if not s:
        return default
    if s not in _ALIASES:
        raise ValueError(f"unknown privacy level {value!r} (expected one of {', '.join(LEVELS)})")
    return _ALIASES[s]


def level_of(metadata: Optional[Dict[str, Any]]) -> str:
    """Privacy level of a chunk from its metadata. Missing -> open; any value
    that is not exactly open is reported local-only (fail closed)."""
    v = (metadata or {}).get("privacy")
    if v is None or v == OPEN:
        return OPEN
    return LOCAL_ONLY


def stricter(*levels: Optional[str]) -> Optional[str]:
    """The most restrictive of the given levels; None if all are None."""
    present = [l for l in levels if l]
    if not present:
        return None
    return LOCAL_ONLY if any(l != OPEN for l in present) else OPEN


def sql_clause(allow_local_only: bool) -> str:
    """WHERE fragment to AND onto a document_embeddings query."""
    return "" if allow_local_only else SQL_OPEN_ONLY


def filter_docs(docs: Iterable[Dict[str, Any]], allow_local_only: bool) -> List[Dict[str, Any]]:
    """Second line of defence after the SQL filter: drop non-open chunks for a
    closed reader. Applied to every result list a model can see."""
    docs = list(docs or [])
    if allow_local_only:
        return docs
    return [d for d in docs if level_of(d.get("metadata")) == OPEN]


def has_local_only(docs: Iterable[Dict[str, Any]]) -> bool:
    return any(level_of(d.get("metadata")) != OPEN for d in (docs or []))


# ── locality of a reasoner ──────────────────────────────────────────────────

def _extra_local_hosts() -> set:
    raw = os.getenv("PRIVACY_LOCAL_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def is_owner_host(url: str) -> bool:
    """Is this Ollama endpoint on network space the owner controls?
    Unparseable or public -> False."""
    try:
        host = (urlparse(url).hostname or "").strip().lower().rstrip(".")
    except Exception:
        return False
    if not host:
        return False
    if host in _extra_local_hosts():
        return True
    if host == "localhost" or "." not in host and ":" not in host:
        # A bare name is a docker-compose service (the box's own `ollama`) or a
        # hostname resolved on the owner's LAN / tailnet MagicDNS.
        return True
    if host.endswith((".ts.net", ".local", ".internal", ".lan", ".home.arpa")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # a public DNS name: we cannot tell who runs it
    if ip.is_loopback or ip.is_private or ip.is_link_local:
        return True
    if ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"):
        return True  # Tailscale / CGNAT space
    if ip.version == 6 and ip in ipaddress.ip_network("fd7a:115c:a1e0::/48"):
        return True  # Tailscale IPv6
    return False


def _is_ollama_cloud_model(model: str) -> bool:
    m = (model or "").lower()
    tag = m.rsplit(":", 1)[1] if ":" in m else ""
    return tag == "cloud" or tag.endswith("-cloud") or m.endswith("-cloud")


def reasoner_is_local(model: Optional[str], *, resolve=None,
                      ollama_urls: Optional[List[str]] = None) -> bool:
    """True only when `model` will be answered on owner-controlled hardware.
    Any doubt -> False. `resolve` and `ollama_urls` are injectable for tests."""
    if not model or not isinstance(model, str):
        return False
    try:
        if resolve is None or ollama_urls is None:
            from api import providers as _p
            resolve = resolve or _p._resolve
            if ollama_urls is None:
                ollama_urls = [_p.OLLAMA_URL] + ([_p.OLLAMA_SPOKE_URL] if _p.OLLAMA_SPOKE_URL else [])
        client_type = resolve(model)[0]
    except Exception:
        return False
    if client_type != "ollama":
        return False
    if _is_ollama_cloud_model(model):
        return False
    urls = [u for u in (ollama_urls or []) if u]
    if not urls:
        return False
    return all(is_owner_host(u) for u in urls)


# ── per-turn reader for tools ───────────────────────────────────────────────
# The agentic search_memory tool runs inside a model turn but does not know
# which model it serves. /chat/rag sets this for the duration of the turn; the
# default (False) is the closed view.
_turn_allows_local_only: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "privacy_turn_allows_local_only", default=False)


def set_turn_allows_local_only(allowed: bool):
    return _turn_allows_local_only.set(bool(allowed))


def reset_turn(token) -> None:
    try:
        _turn_allows_local_only.reset(token)
    except Exception:
        _turn_allows_local_only.set(False)


def turn_allows_local_only() -> bool:
    return _turn_allows_local_only.get()


# ── schema / migration ──────────────────────────────────────────────────────
# The level lives in metadata JSONB (same pattern as `layer` and `mem_type`), so
# there is no column change. The only schema object is a partial index, kept in
# step in three places: vector-db/init.sql (new brains), the API startup hook
# (every boot) and scripts/migrate_privacy.py (an existing brain, on demand).
INDEX_NAME = "document_embeddings_privacy_idx"
INDEX_SQL = (
    f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} "
    "ON document_embeddings ((metadata->>'privacy')) "
    "WHERE metadata->>'privacy' IS NOT NULL"
)


def migrate(conn) -> Dict[str, Any]:
    """Bring an existing brain's schema up to the privacy gate. Idempotent:
    creates the partial index only if it is missing, rewrites no rows (a chunk
    without the key is already `open`). Returns what it found and did."""
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (INDEX_NAME,))
    existed = cur.fetchone() is not None
    if not existed:
        cur.execute(INDEX_SQL)
    cur.execute(
        "SELECT COUNT(*) FILTER (WHERE metadata->>'privacy' = 'local-only'), "
        "       COUNT(*) FILTER (WHERE metadata->>'privacy' IS NOT NULL "
        "                          AND metadata->>'privacy' NOT IN ('open', 'local-only')), "
        "       COUNT(*) "
        "FROM document_embeddings"
    )
    local_only, unknown, total = cur.fetchone()
    conn.commit()
    cur.close()
    return {"index_created": not existed, "chunks": total,
            "local_only_chunks": local_only, "unknown_level_chunks": unknown}
