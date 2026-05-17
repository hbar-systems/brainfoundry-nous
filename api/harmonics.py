"""hbar.harmonics — the operational economic layer.

Records and scores coherence events between brains; exposes standing.

This module owns:
- the `coherence_events` table (Postgres, append-only)
- the coherence measurement function (SPEC s3): cos/sin geometry over the
  brain's embedding model
- ED25519 signing of each event with this brain's BRAIN_PRIVATE_KEY
- standing: the decayed sum of this brain's contribution scores, on read

Spec:    hbar.world/systems/hbar.harmonics/repos/spec/SPEC.md
Charter: hbar.world/systems/hbar.harmonics/README.md

Out of scope (do not add here):
- cross-brain bilateral exchange over federation — federation_dm integration,
  the next layer
- voting / multisig          — lives in hbar.vote
- what value means           — lives in hbar.economy (constitutional)
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import time
import uuid
from typing import Any, Dict, Optional, Tuple

import httpx
import numpy as np
import psycopg2
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.federation_dm import _operator_auth


# ─── Constants ──────────────────────────────────────────────────────────────

HALF_LIFE_DAYS = 75.0   # SPEC s4.1 — load-bearing, configurable
_DAY = 86400.0
_LN2 = math.log(2.0)
_QUANT = 9              # quantize before signing so two brains' independently
                        # computed scores produce byte-identical payloads


# ─── Schema ─────────────────────────────────────────────────────────────────

COHERENCE_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS coherence_events (
    id              SERIAL PRIMARY KEY,
    peer_pubkey     TEXT NOT NULL,
    role            TEXT NOT NULL,            -- 'contributor' | 'receiver'
    cos             DOUBLE PRECISION NOT NULL,
    sin             DOUBLE PRECISION NOT NULL,
    score           DOUBLE PRECISION NOT NULL,
    content_hash    TEXT NOT NULL,
    sig             TEXT,                     -- ed25519:<b64url> over the event
    event_timestamp BIGINT NOT NULL,          -- unix epoch seconds, UTC
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ce_role_idx ON coherence_events (role);
CREATE INDEX IF NOT EXISTS ce_peer_idx ON coherence_events (peer_pubkey);
"""


def init_tables(conn=None) -> None:
    """Idempotent table create. Called from main.py startup hook (fail-soft)."""
    if not os.getenv("DATABASE_URL"):
        return
    try:
        owns_conn = conn is None
        if owns_conn:
            conn = psycopg2.connect(os.environ["DATABASE_URL"])
            conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(COHERENCE_EVENTS_DDL)
        if owns_conn:
            conn.close()
    except Exception as e:
        print(f"[harmonics] table init skipped: {e}", flush=True)


# ─── Crypto helpers (canonical form matches substrate.py / federation_dm.py) ─

def _b64url_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _canonical(payload: Dict[str, Any]) -> bytes:
    """Deterministic JSON-bytes for signing. Sorted keys, no whitespace."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def _load_private_key() -> Ed25519PrivateKey:
    pk_b64 = os.getenv("BRAIN_PRIVATE_KEY", "")
    if not pk_b64:
        raise RuntimeError(
            "BRAIN_PRIVATE_KEY not configured — run scripts/generate_keypair.py"
        )
    return Ed25519PrivateKey.from_private_bytes(_b64url_decode(pk_b64))


def sign_with_brain_key(payload: Dict[str, Any]) -> str:
    """Sign a canonicalized payload with this brain's ED25519 private key."""
    return _b64url_nopad(_load_private_key().sign(_canonical(payload)))


def verify_with_pubkey(pubkey_b64: str, signature_b64: str,
                       payload: Dict[str, Any]) -> bool:
    """Verify an ED25519 signature over a canonicalized payload."""
    try:
        pub = Ed25519PublicKey.from_public_bytes(_b64url_decode(pubkey_b64))
        pub.verify(_b64url_decode(signature_b64), _canonical(payload))
        return True
    except Exception:
        return False


# ─── Measurement function (SPEC s3) ─────────────────────────────────────────

def coherence(text_c: str, text_r: str) -> Tuple[float, float, float]:
    """Score one coherence event (c -> R). Returns (cos, sin, score).

    Uses the brain's configured embedding model — whatever EMBEDDING_MODEL_NAME
    resolves to (bge-large-en-v1.5 by default; 1024-dim, normalized). The
    cos/sin geometry is model-agnostic, but both sides must be embedded in the
    SAME space the brain runs, so this calls the brain's own model.

      cos   -- alignment / overlap, clamped to [0, 1]
      sin   -- orthogonal / novelty
      score -- cos * sin, the balanced scalar (SPEC s3.1), range [0, 0.5]
    """
    from api.embeddings.model import get_model

    model = get_model()
    a = np.asarray(model.encode(text_c, normalize_embeddings=True),
                   dtype=np.float64)
    b = np.asarray(model.encode(text_r, normalize_embeddings=True),
                   dtype=np.float64)
    cos = float(np.dot(a, b))
    cos = max(0.0, min(1.0, cos))   # SPEC s3: clamp negatives (malformed input)
    sin = math.sqrt(max(0.0, 1.0 - cos * cos))
    score = cos * sin
    return round(cos, _QUANT), round(sin, _QUANT), round(score, _QUANT)


def content_hash(c: str, r: str) -> str:
    """sha256:<hex> over the canonical serialization of the (c, R) pair — SPEC s4."""
    canon = json.dumps({"c": c, "r": r}, separators=(",", ":"), sort_keys=True)
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


# ─── Ledger (SPEC s4) ───────────────────────────────────────────────────────

def record_event(
    *,
    peer_pubkey: str,
    role: str,
    cos: float,
    sin: float,
    score: float,
    content_hash: str,
    event_timestamp: Optional[int] = None,
    conn=None,
) -> int:
    """Append one signed event to the append-only ledger. Returns the row id.

    The event is signed with this brain's ED25519 key over the canonical
    payload (SPEC s4). `role` is 'contributor' or 'receiver'.
    """
    ts = int(event_timestamp if event_timestamp is not None else time.time())
    sig_payload = {
        "peer_pubkey": peer_pubkey,
        "role": role,
        "cos": cos,
        "sin": sin,
        "score": score,
        "content_hash": content_hash,
        "event_timestamp": ts,
    }
    sig = "ed25519:" + sign_with_brain_key(sig_payload)

    owns_conn = conn is None
    if owns_conn:
        if not os.getenv("DATABASE_URL"):
            raise RuntimeError("DATABASE_URL not configured")
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO coherence_events
                    (peer_pubkey, role, cos, sin, score, content_hash, sig,
                     event_timestamp)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (peer_pubkey, role, cos, sin, score, content_hash, sig, ts),
            )
            row = cur.fetchone()
        if owns_conn:
            conn.commit()
    finally:
        if owns_conn:
            conn.close()
    return row[0]


def standing(now: Optional[float] = None,
             half_life_days: float = HALF_LIFE_DAYS,
             conn=None) -> float:
    """This brain's standing — SPEC s4.1.

    Decayed sum of scores over events where this brain was the CONTRIBUTOR.
    Computed on read, never stored. Receiving earns no standing — it is
    directional.
    """
    now = time.time() if now is None else now
    owns_conn = conn is None
    if owns_conn:
        if not os.getenv("DATABASE_URL"):
            return 0.0
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT score, event_timestamp FROM coherence_events "
                    "WHERE role = 'contributor'"
                )
                rows = cur.fetchall()
            except psycopg2.errors.UndefinedTable:
                conn.rollback()
                rows = []
    finally:
        if owns_conn:
            conn.close()
    total = 0.0
    for score, ts in rows:
        age_days = (now - ts) / _DAY
        total += score * math.exp(-_LN2 * age_days / half_life_days)
    return total


# ─── HTTP endpoints ─────────────────────────────────────────────────────────

router = APIRouter()


class ScoreRequest(BaseModel):
    contribution: str = Field(..., description="the contribution artifact c")
    receiver_context: str = Field(..., description="the receiver context R")
    peer_pubkey: str = Field(default="",
                             description="contributing peer's ED25519 public key")
    record: bool = Field(default=False,
                         description="append this event to the ledger")


class ScoreResponse(BaseModel):
    cos: float
    sin: float
    score: float
    content_hash: str
    event_id: Optional[int] = None


class StandingResponse(BaseModel):
    standing: float
    half_life_days: float


@router.post("/harmonics/score", response_model=ScoreResponse)
def score_exchange(req: ScoreRequest):
    """Score a coherence event (c -> R); optionally record it — SPEC s3."""
    try:
        cos, sin, score = coherence(req.contribution, req.receiver_context)
        ch = content_hash(req.contribution, req.receiver_context)
        event_id = None
        if req.record:
            # v0 records this brain as contributor. The bilateral receiver-side
            # recording over federation is the next layer (federation_dm).
            event_id = record_event(
                peer_pubkey=req.peer_pubkey, role="contributor",
                cos=cos, sin=sin, score=score, content_hash=ch,
            )
        return ScoreResponse(cos=cos, sin=sin, score=score,
                             content_hash=ch, event_id=event_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/harmonics/standing", response_model=StandingResponse)
def get_standing():
    """This brain's standing — decayed sum of contribution scores — SPEC s4.1."""
    try:
        return StandingResponse(standing=standing(),
                                half_life_days=HALF_LIFE_DAYS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class LedgerEvent(BaseModel):
    id: int
    peer_pubkey: str
    role: str
    cos: float
    sin: float
    score: float
    content_hash: str
    sig: Optional[str] = None
    event_timestamp: int


class LedgerResponse(BaseModel):
    events: list[LedgerEvent]
    count: int


@router.get("/harmonics/ledger", response_model=LedgerResponse)
def get_ledger(limit: int = 100):
    """This brain's coherence-event ledger — the signed, append-only record of
    the exchanges it took part in (SPEC s2.5). Newest first. Read-only; rows
    are never updated or deleted."""
    try:
        if not os.getenv("DATABASE_URL"):
            return LedgerResponse(events=[], count=0)
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        "SELECT id, peer_pubkey, role, cos, sin, score, "
                        "content_hash, sig, event_timestamp FROM coherence_events "
                        "ORDER BY event_timestamp DESC, id DESC LIMIT %s",
                        (max(1, min(limit, 500)),),
                    )
                    rows = cur.fetchall()
                except psycopg2.errors.UndefinedTable:
                    conn.rollback()
                    rows = []
        finally:
            conn.close()
        events = [
            LedgerEvent(id=r[0], peer_pubkey=r[1], role=r[2], cos=r[3], sin=r[4],
                        score=r[5], content_hash=r[6], sig=r[7], event_timestamp=r[8])
            for r in rows
        ]
        return LedgerResponse(events=events, count=len(events))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Bilateral cross-brain exchange (SPEC s4 — the federation layer) ─────────
#
# A coherence event is recorded by BOTH brains. The contributor brain calls
# POST /harmonics/contribute, which posts the contribution to the receiver
# brain's POST /harmonics/exchange. The receiver computes its own context R,
# scores the event, records its role='receiver' row, and returns the scored
# event. The contributor then records the matching role='contributor' row.
# Both rows share (cos, sin, score, content_hash, event_timestamp); each is
# signed by its own brain's key, so the pair cross-verifies.


def _fetch_peer(handle: str) -> Tuple[str, str]:
    """Resolve a peer brain's (public_key, endpoint) from its /identity."""
    endpoint = f"https://{handle}.brainfoundry.ai"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{endpoint}/identity")
    except Exception as e:
        raise HTTPException(status_code=502,
                            detail=f"peer {handle} unreachable: {e}")
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"peer {handle} /identity returned {resp.status_code}")
    pubkey = resp.json().get("public_key")
    if not pubkey:
        raise HTTPException(status_code=502,
                            detail=f"peer {handle} /identity has no public_key")
    return pubkey, endpoint


def _receiver_context(contribution: str, conn=None) -> Optional[str]:
    """Compute R — this brain's relevant prior knowledge for a contribution.

    Searches this brain's own document_embeddings for the nearest chunk.
    Returns None when the brain has no corpus to receive the contribution
    against — a brain with no knowledge cannot have a contribution land.
    """
    from api.embeddings.model import get_model

    vec = get_model().encode(contribution, normalize_embeddings=True)
    vec_literal = "[" + ",".join(f"{float(x):.8f}" for x in vec) + "]"

    owns_conn = conn is None
    if owns_conn:
        if not os.getenv("DATABASE_URL"):
            return None
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT content FROM document_embeddings "
                    "ORDER BY embedding <=> %s::vector LIMIT 1",
                    (vec_literal,),
                )
                row = cur.fetchone()
            except psycopg2.errors.UndefinedTable:
                conn.rollback()
                row = None
    finally:
        if owns_conn:
            conn.close()
    return row[0] if row and row[0] else None


class ExchangeRequest(BaseModel):
    from_brain: str
    from_pubkey: str
    contribution: str
    ts: int
    nonce: str
    signature: str


@router.post("/harmonics/exchange")
def harmonics_exchange(req: ExchangeRequest):
    """Receiver side of a bilateral coherence event (SPEC s4). Public.

    Verifies the contributor's signature, computes this brain's receiver
    context R, scores the event, records the role='receiver' row, and returns
    the scored event so the contributor can record the matching row.
    """
    now = int(time.time())
    if abs(now - req.ts) > 300:
        raise HTTPException(status_code=401, detail="ts outside 5-minute window")

    sig_payload = {
        "from_brain": req.from_brain,
        "from_pubkey": req.from_pubkey,
        "contribution": req.contribution,
        "ts": req.ts,
        "nonce": req.nonce,
    }
    if not verify_with_pubkey(req.from_pubkey, req.signature, sig_payload):
        raise HTTPException(status_code=401, detail="signature verification failed")

    R = _receiver_context(req.contribution)
    if R is None:
        return {"recorded": False,
                "reason": "receiver has no corpus context to receive against"}

    cos, sin, score = coherence(req.contribution, R)
    ch = content_hash(req.contribution, R)
    event_id = record_event(
        peer_pubkey=req.from_pubkey, role="receiver",
        cos=cos, sin=sin, score=score, content_hash=ch,
        event_timestamp=req.ts,
    )
    return {
        "recorded": True,
        "event_id": event_id,
        "cos": cos, "sin": sin, "score": score,
        "content_hash": ch,
        "event_timestamp": req.ts,
        "receiver_pubkey": os.getenv("BRAIN_PUBLIC_KEY", ""),
    }


class ContributeRequest(BaseModel):
    to: str = Field(..., description="peer brain handle, e.g. 'yury'")
    contribution: str = Field(..., description="the contribution artifact c")


@router.post("/harmonics/contribute")
def harmonics_contribute(req: ContributeRequest,
                         _auth: str = Depends(_operator_auth)):
    """Contributor side of a bilateral coherence event (SPEC s4). Operator-only.

    Signs and posts a contribution to the peer brain's /harmonics/exchange,
    then records the matching role='contributor' row from the peer's scored
    response. Both brains end up with a signed row for the same event.
    """
    my_brain = os.getenv("BRAIN_ID", "")
    my_pubkey = os.getenv("BRAIN_PUBLIC_KEY", "")
    if not my_brain or not my_pubkey:
        raise HTTPException(status_code=500,
                            detail="BRAIN_ID or BRAIN_PUBLIC_KEY not configured")

    peer_pubkey, peer_endpoint = _fetch_peer(req.to)

    payload = {
        "from_brain": my_brain,
        "from_pubkey": my_pubkey,
        "contribution": req.contribution,
        "ts": int(time.time()),
        "nonce": uuid.uuid4().hex,
    }
    body = {**payload, "signature": sign_with_brain_key(payload)}

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{peer_endpoint}/harmonics/exchange", json=body)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"peer unreachable: {e}")
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"peer /harmonics/exchange returned {resp.status_code}: "
                   f"{resp.text[:200]}")

    result = resp.json()
    if not result.get("recorded"):
        return {"recorded": False,
                "reason": result.get("reason", "peer did not record the event")}

    event_id = record_event(
        peer_pubkey=peer_pubkey, role="contributor",
        cos=result["cos"], sin=result["sin"], score=result["score"],
        content_hash=result["content_hash"],
        event_timestamp=result["event_timestamp"],
    )
    return {
        "recorded": True,
        "event_id": event_id,
        "peer": req.to,
        "cos": result["cos"], "sin": result["sin"], "score": result["score"],
    }
