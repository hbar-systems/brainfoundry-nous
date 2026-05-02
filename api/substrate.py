"""Substrate floor — Layer 1 of federation trust mechanisms.

Per-brain attestation ledger + signed `/v1/federation/substrate-depth` endpoint
+ handshake gate. Defends federation membership against empty/spam brains
without verifying personhood.

Design rationale:
    hbar.world/discussions/2026-05-01_federation-trust-mechanisms.md

This module owns:
- the `artifact_attestations` table (Postgres, sibling to `document_embeddings`)
- attestation recording at ingestion time
- depth computation + ED25519 signing of the depth payload (BRAIN_PRIVATE_KEY)
- cached signed payload (5-minute TTL, env-tunable)
- threshold check for incoming federation candidates

Out of scope (do not add here):
- Layer 2 probationary minting cap   — lives in hbar.economy
- Layer 3 vouching with sponsor stake — lives in hbar.economy + later integration
- coherence-service R/Q/H minting     — lives in hbar.economy
- owner-identity verification         — explicitly excluded by design
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


# ─── Constants ──────────────────────────────────────────────────────────────

ALLOWED_SOURCE_TYPES = {
    "journal",
    "note",
    "document",
    "conversation",
    "work_output",
    "other",
}

ALLOWED_FIRST_PERSON = {
    "authored_by_owner",
    "addressed_to_owner",
    "collected_by_owner",
    "derived",
}


# ─── Schema ─────────────────────────────────────────────────────────────────

ATTESTATIONS_DDL = """
CREATE TABLE IF NOT EXISTS artifact_attestations (
    id                       SERIAL PRIMARY KEY,
    content_hash             TEXT NOT NULL UNIQUE,
    timestamp_ingested       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_type              TEXT NOT NULL,
    byte_size                BIGINT NOT NULL,
    owner_signature          TEXT NOT NULL,
    first_person_attestation TEXT NOT NULL,
    backfilled               BOOLEAN NOT NULL DEFAULT FALSE,
    document_name            TEXT
);
CREATE INDEX IF NOT EXISTS aa_source_type_idx
    ON artifact_attestations (source_type);
CREATE INDEX IF NOT EXISTS aa_first_person_idx
    ON artifact_attestations (first_person_attestation);
CREATE INDEX IF NOT EXISTS aa_ts_idx
    ON artifact_attestations (timestamp_ingested);
"""


def init_tables(conn=None) -> None:
    """Idempotent table create. Called from main.py startup hook.

    Fail-soft: a missing table is reported and skipped, not raised. Federation
    will then refuse handshakes (substrate_floor_not_met) until the DB is reachable
    — which is the correct behavior.
    """
    if not os.getenv("DATABASE_URL"):
        return
    try:
        owns_conn = conn is None
        if owns_conn:
            conn = psycopg2.connect(os.environ["DATABASE_URL"])
            conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(ATTESTATIONS_DDL)
        if owns_conn:
            conn.close()
    except Exception as e:
        print(f"[substrate] table init skipped: {e}", flush=True)


# ─── Crypto helpers ─────────────────────────────────────────────────────────


def _b64url_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _canonical(payload: Dict[str, Any]) -> bytes:
    """Deterministic JSON-bytes for signing. Sorted keys, no whitespace.

    Matches federation_dm._canonical so peers using either path produce
    identical canonical bytes.
    """
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def _load_private_key() -> Ed25519PrivateKey:
    pk_b64 = os.getenv("BRAIN_PRIVATE_KEY", "")
    if not pk_b64:
        raise RuntimeError(
            "BRAIN_PRIVATE_KEY not configured — run scripts/generate_keypair.py"
        )
    raw = _b64url_decode(pk_b64)
    return Ed25519PrivateKey.from_private_bytes(raw)


def sign_with_brain_key(payload: Dict[str, Any]) -> str:
    """Sign canonicalized payload with this brain's ED25519 private key."""
    return _b64url_nopad(_load_private_key().sign(_canonical(payload)))


def verify_with_pubkey(pubkey_b64: str, signature_b64: str, payload: Dict[str, Any]) -> bool:
    """Verify ED25519 signature over canonicalized payload."""
    try:
        pub = Ed25519PublicKey.from_public_bytes(_b64url_decode(pubkey_b64))
        pub.verify(_b64url_decode(signature_b64), _canonical(payload))
        return True
    except Exception:
        return False


def content_hash_of(text: str) -> str:
    """sha256:<hex> over UTF-8 bytes of the source artifact text."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ─── Recording attestations ────────────────────────────────────────────────


def record_attestation(
    *,
    content_hash: str,
    source_type: str,
    byte_size: int,
    first_person_attestation: str,
    document_name: Optional[str] = None,
    backfilled: bool = False,
    timestamp_ingested: Optional[str] = None,
    conn=None,
) -> Optional[int]:
    """Insert an attestation row.

    Returns the new row id, or None if a row with this content_hash already
    exists (idempotent). Raises ValueError on invalid enum values; signing
    errors raised from `sign_with_brain_key` propagate.

    The owner signs a payload that excludes timestamp_ingested (which is set
    by the DB clock) so backfilled rows can sign deterministically.
    """
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise ValueError(f"invalid source_type: {source_type}")
    if first_person_attestation not in ALLOWED_FIRST_PERSON:
        raise ValueError(f"invalid first_person_attestation: {first_person_attestation}")
    if byte_size < 0:
        raise ValueError("byte_size must be >= 0")
    if not content_hash.startswith("sha256:"):
        raise ValueError("content_hash must be sha256:<hex>")

    sig_payload = {
        "content_hash": content_hash,
        "source_type": source_type,
        "byte_size": int(byte_size),
        "first_person_attestation": first_person_attestation,
        "document_name": document_name or "",
        "backfilled": bool(backfilled),
    }
    owner_signature = "ed25519:" + sign_with_brain_key(sig_payload)

    owns_conn = conn is None
    if owns_conn:
        if not os.getenv("DATABASE_URL"):
            raise RuntimeError("DATABASE_URL not configured")
        conn = psycopg2.connect(os.environ["DATABASE_URL"])

    try:
        with conn.cursor() as cur:
            if timestamp_ingested:
                cur.execute(
                    """INSERT INTO artifact_attestations
                        (content_hash, timestamp_ingested, source_type, byte_size,
                         owner_signature, first_person_attestation, backfilled, document_name)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (content_hash) DO NOTHING
                       RETURNING id""",
                    (content_hash, timestamp_ingested, source_type, int(byte_size),
                     owner_signature, first_person_attestation, bool(backfilled),
                     document_name),
                )
            else:
                cur.execute(
                    """INSERT INTO artifact_attestations
                        (content_hash, source_type, byte_size, owner_signature,
                         first_person_attestation, backfilled, document_name)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (content_hash) DO NOTHING
                       RETURNING id""",
                    (content_hash, source_type, int(byte_size), owner_signature,
                     first_person_attestation, bool(backfilled), document_name),
                )
            row = cur.fetchone()
        if owns_conn:
            conn.commit()
    finally:
        if owns_conn:
            conn.close()

    return row[0] if row else None


def record_attestation_safe(**kwargs) -> Optional[int]:
    """Wrapper that swallows attestation errors so RAG ingestion is never blocked.

    The substrate floor is a federation precondition, not a write gate. If the
    ledger is misconfigured we want the user's content to still ingest; the
    federation handshake will simply fail until the operator fixes it.
    """
    try:
        return record_attestation(**kwargs)
    except Exception as e:
        print(f"[substrate] record_attestation skipped: {e}", flush=True)
        return None


# ─── Depth computation ──────────────────────────────────────────────────────


@dataclass
class SubstrateDepth:
    brain_pubkey: str
    artifact_count: int
    total_bytes: int
    oldest_artifact_ts: Optional[str]
    newest_artifact_ts: Optional[str]
    source_diversity: int
    first_person_count: int
    computed_at: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "brain_pubkey": self.brain_pubkey,
            "artifact_count": self.artifact_count,
            "total_bytes": self.total_bytes,
            "oldest_artifact_ts": self.oldest_artifact_ts,
            "newest_artifact_ts": self.newest_artifact_ts,
            "source_diversity": self.source_diversity,
            "first_person_count": self.first_person_count,
            "computed_at": self.computed_at,
        }


def compute_depth(conn=None) -> SubstrateDepth:
    """Aggregate the attestation ledger into a substrate-depth snapshot."""
    pubkey = os.getenv("BRAIN_PUBLIC_KEY", "")
    brain_pubkey = f"ed25519:{pubkey}" if pubkey else ""

    owns_conn = conn is None
    if owns_conn:
        if not os.getenv("DATABASE_URL"):
            return SubstrateDepth(
                brain_pubkey=brain_pubkey,
                artifact_count=0,
                total_bytes=0,
                oldest_artifact_ts=None,
                newest_artifact_ts=None,
                source_diversity=0,
                first_person_count=0,
                computed_at=_iso_now(),
            )
        conn = psycopg2.connect(os.environ["DATABASE_URL"])

    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """SELECT COUNT(*),
                              COALESCE(SUM(byte_size), 0),
                              MIN(timestamp_ingested),
                              MAX(timestamp_ingested),
                              COUNT(DISTINCT source_type),
                              SUM(CASE WHEN first_person_attestation <> 'derived'
                                       THEN 1 ELSE 0 END)
                       FROM artifact_attestations"""
                )
                row = cur.fetchone()
            except psycopg2.errors.UndefinedTable:
                conn.rollback()
                row = (0, 0, None, None, 0, 0)
    finally:
        if owns_conn:
            conn.close()

    count, total, oldest, newest, diversity, first_person = row
    return SubstrateDepth(
        brain_pubkey=brain_pubkey,
        artifact_count=int(count or 0),
        total_bytes=int(total or 0),
        oldest_artifact_ts=oldest.isoformat() if oldest else None,
        newest_artifact_ts=newest.isoformat() if newest else None,
        source_diversity=int(diversity or 0),
        first_person_count=int(first_person or 0),
        computed_at=_iso_now(),
    )


def _iso_now() -> str:
    # UTC, second-precision, Z suffix — matches the spec's example shape.
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def signed_depth_payload(conn=None) -> Dict[str, Any]:
    """Compute depth and produce the externally-published signed payload."""
    depth = compute_depth(conn=conn)
    payload = depth.to_payload()
    signature = sign_with_brain_key(payload)
    return {**payload, "signature": f"ed25519:{signature}"}


# ─── Signed-payload cache (5-minute default) ───────────────────────────────

_CACHE: Dict[str, Any] = {"payload": None, "computed_at": 0.0}


def cache_seconds() -> int:
    try:
        return max(0, int(os.getenv("SUBSTRATE_DEPTH_CACHE_SECONDS", "300")))
    except ValueError:
        return 300


def signed_depth_payload_cached(conn=None) -> Dict[str, Any]:
    """5-min cached signed depth payload. Call from the public endpoint.

    Cache is process-local. With the default 5-min TTL, federation peers
    polling at any rate get the same signed payload until it expires.
    """
    ttl = cache_seconds()
    now = time.time()
    if _CACHE["payload"] is not None and (now - _CACHE["computed_at"]) < ttl:
        return _CACHE["payload"]
    payload = signed_depth_payload(conn=conn)
    _CACHE["payload"] = payload
    _CACHE["computed_at"] = now
    return payload


def cache_clear() -> None:
    _CACHE["payload"] = None
    _CACHE["computed_at"] = 0.0


# ─── Threshold gate ────────────────────────────────────────────────────────


@dataclass
class FloorResult:
    ok: bool
    code: Optional[str]
    details: Dict[str, Any]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def thresholds() -> Dict[str, int]:
    return {
        "min_artifacts":    _env_int("FEDERATION_SUBSTRATE_MIN_ARTIFACTS",     50),
        "min_first_person": _env_int("FEDERATION_SUBSTRATE_MIN_FIRST_PERSON",  25),
        "min_diversity":    _env_int("FEDERATION_SUBSTRATE_MIN_DIVERSITY",      2),
        "min_age_days":     _env_int("FEDERATION_SUBSTRATE_MIN_AGE_DAYS",       7),
    }


def _age_days(oldest_iso: Optional[str], now_epoch: Optional[float] = None) -> Optional[float]:
    if not oldest_iso:
        return None
    if now_epoch is None:
        now_epoch = time.time()
    # Accept both "YYYY-MM-DDTHH:MM:SSZ" (our endpoint output) and "...+00:00"
    # (Postgres TIMESTAMPTZ isoformat with timezone). Normalize to UTC seconds.
    s = oldest_iso.replace("Z", "+00:00")
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(s)
        return (now_epoch - dt.timestamp()) / 86400.0
    except Exception:
        return None


def check_floor(payload: Dict[str, Any]) -> FloorResult:
    """Apply Layer-1 thresholds to a (verified) substrate-depth payload.

    Caller is responsible for verifying the payload signature first.
    Returns FloorResult with machine-readable code + per-check details.
    """
    th = thresholds()
    details: Dict[str, Any] = {}

    artifact_count = int(payload.get("artifact_count", 0))
    first_person_count = int(payload.get("first_person_count", 0))
    source_diversity = int(payload.get("source_diversity", 0))
    age_days = _age_days(payload.get("oldest_artifact_ts"))

    if artifact_count < th["min_artifacts"]:
        details["artifact_count"] = {"got": artifact_count, "required": th["min_artifacts"]}
    if first_person_count < th["min_first_person"]:
        details["first_person_count"] = {"got": first_person_count, "required": th["min_first_person"]}
    if source_diversity < th["min_diversity"]:
        details["source_diversity"] = {"got": source_diversity, "required": th["min_diversity"]}
    if age_days is None or age_days < th["min_age_days"]:
        details["age_days"] = {"got": age_days, "required": th["min_age_days"]}

    if details:
        return FloorResult(ok=False, code="substrate_floor_not_met", details=details)
    return FloorResult(ok=True, code=None, details={})


# ─── Verify a peer's depth payload ─────────────────────────────────────────


def verify_depth_payload(
    *, payload: Dict[str, Any], pinned_pubkey_b64: str
) -> Tuple[bool, str]:
    """Verify a peer's signed substrate-depth payload.

    Returns (ok, error_code). On success error_code is "".

    `pinned_pubkey_b64` is the peer's public key from known_peers.toml — NEVER
    a key fetched from the peer's own /identity. The depth payload's
    `brain_pubkey` field is informational only; we don't trust it for verify.
    """
    sig = payload.get("signature", "")
    if not isinstance(sig, str) or not sig.startswith("ed25519:"):
        return False, "signature_invalid"
    sig_b64 = sig.split(":", 1)[1]

    body = {k: v for k, v in payload.items() if k != "signature"}
    if not verify_with_pubkey(pinned_pubkey_b64, sig_b64, body):
        return False, "signature_invalid"
    return True, ""


# ─── Per-peer depth fetch + check ──────────────────────────────────────────


import httpx  # noqa: E402  (kept after stdlib imports above for clarity)


_PEER_FLOOR_CACHE: Dict[str, Tuple[float, FloorResult]] = {}


def _peer_cache_ttl() -> int:
    try:
        return max(0, int(os.getenv("SUBSTRATE_PEER_CACHE_SECONDS", "300")))
    except ValueError:
        return 300


async def fetch_and_check_peer(
    *, peer_endpoint: str, pinned_pubkey_b64: str, timeout_s: float = 10.0
) -> FloorResult:
    """Fetch a peer's `/v1/federation/substrate-depth`, verify sig, apply floor.

    Cached per-endpoint for SUBSTRATE_PEER_CACHE_SECONDS (default 300) so the
    handshake gate doesn't hammer the peer on every assertion.
    """
    now = time.time()
    cached = _PEER_FLOOR_CACHE.get(peer_endpoint)
    if cached and (now - cached[0]) < _peer_cache_ttl():
        return cached[1]

    url = peer_endpoint.rstrip("/") + "/v1/federation/substrate-depth"
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(url)
        if r.status_code != 200:
            res = FloorResult(
                ok=False,
                code="substrate_depth_unreachable",
                details={"status": r.status_code, "endpoint": url},
            )
            _PEER_FLOOR_CACHE[peer_endpoint] = (now, res)
            return res
        payload = r.json()
    except Exception as e:
        res = FloorResult(
            ok=False,
            code="substrate_depth_unreachable",
            details={"error": str(e)[:200], "endpoint": url},
        )
        _PEER_FLOOR_CACHE[peer_endpoint] = (now, res)
        return res

    ok, err = verify_depth_payload(payload=payload, pinned_pubkey_b64=pinned_pubkey_b64)
    if not ok:
        res = FloorResult(ok=False, code=err, details={"endpoint": url})
        _PEER_FLOOR_CACHE[peer_endpoint] = (now, res)
        return res

    res = check_floor(payload)
    _PEER_FLOOR_CACHE[peer_endpoint] = (now, res)
    return res


def peer_cache_clear() -> None:
    _PEER_FLOOR_CACHE.clear()
