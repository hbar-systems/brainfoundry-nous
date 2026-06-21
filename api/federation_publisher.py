"""Federation publisher — sign + POST signed posts to the hbar.social relay.

Implements the brain-side of PROTOCOL_CONTRACT v0.5 §8: build a v0.5 payload,
canonicalize with JCS (api/federation_jcs.py — NOT federation_dm.py's
_canonical), sign with the brain's ED25519 key, POST to the relay, and record
the result in a local outbox.

Endpoints (all operator-auth, same X-API-Key as the rest of the brain):
- POST /v1/federation/social/publish  — build + sign + POST one post
- GET  /v1/federation/social/outbox   — list published posts, newest first

The Federation tab UI wires onto these once the first real post lands.
Created 2026-06-21.
"""
from __future__ import annotations

import base64
import json
import os
import time
import uuid
from typing import Any, Optional

import httpx
import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from api.federation_jcs import sign_payload, signing_bytes


router = APIRouter(prefix="/v1/federation/social", tags=["federation-social"])

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

RELAY_URL = os.getenv("HBAR_SOCIAL_RELAY_URL", "https://hbar.social/v1/relay/post")
PROTOCOL_VERSION = "0.5"
VALID_POST_TYPES = {
    "text", "fivefield", "thought_drop", "project_announcement", "brain_summary",
}


def _operator_auth(x_api_key: str = Security(_api_key_header)) -> str:
    """Operator-only gate. Same X-API-Key as the rest of the brain."""
    expected = os.getenv("BRAIN_API_KEY", "")
    env = os.getenv("BRAIN_ENV", "dev").lower()
    if not expected:
        if env != "dev":
            raise HTTPException(500, "Server misconfigured: BRAIN_API_KEY not set.")
        return "dev_mode"
    if not x_api_key or x_api_key != expected:
        raise HTTPException(401, "Invalid API key")
    return x_api_key


def _db():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise HTTPException(500, "DATABASE_URL not configured")
    return psycopg2.connect(url)


# ─── Schema ──────────────────────────────────────────────────────────────────

OUTBOX_DDL = """
CREATE TABLE IF NOT EXISTS federation_social_outbox (
    id            SERIAL PRIMARY KEY,
    post_id       TEXT,
    post_type     TEXT NOT NULL,
    content       JSONB NOT NULL,
    authorship    REAL NOT NULL,
    visibility    TEXT NOT NULL,
    in_reply_to   TEXT,
    payload_ts    BIGINT NOT NULL,
    nonce         TEXT NOT NULL,
    signature     TEXT NOT NULL,
    relay_url     TEXT NOT NULL,
    delivered     BOOLEAN DEFAULT FALSE,
    http_code     INT,
    stored_at     TEXT,
    error         TEXT,
    created_at    TIMESTAMP DEFAULT NOW(),
    UNIQUE (post_id)
);
CREATE INDEX IF NOT EXISTS federation_social_outbox_created_idx
    ON federation_social_outbox (created_at DESC);
"""


def init_tables() -> None:
    """Idempotent table create. Called from main.py startup hook."""
    if not os.getenv("DATABASE_URL"):
        return
    try:
        with _db() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(OUTBOX_DDL)
    except Exception as e:
        print(f"[federation_publisher] table init skipped: {e}", flush=True)


# ─── Core publish logic ──────────────────────────────────────────────────────

def _brain_keys() -> tuple[str, str]:
    """Return (private_key_b64url, public_key_b64url). Public key derived from
    the private key if BRAIN_PUBLIC_KEY is unset, so the two can never disagree."""
    priv = os.getenv("BRAIN_PRIVATE_KEY", "")
    if not priv:
        raise HTTPException(
            500, "BRAIN_PRIVATE_KEY not configured — run scripts/generate_keypair.py"
        )
    pub = os.getenv("BRAIN_PUBLIC_KEY", "")
    if not pub:
        seed = base64.urlsafe_b64decode(priv + "=" * (-len(priv) % 4))
        raw_pub = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()
        pub = base64.urlsafe_b64encode(raw_pub).rstrip(b"=").decode()
    return priv, pub


def build_payload(
    *,
    post_type: str,
    content: dict,
    authorship: float,
    brain_handle: str,
    brain_pubkey: str,
    visibility: str = "public",
    in_reply_to: Optional[str] = None,
    ts: Optional[int] = None,
    nonce: Optional[str] = None,
) -> dict:
    """Assemble an unsigned v0.5 payload (PROTOCOL_CONTRACT §2.1). Unsigned —
    pass through sign_payload() before POSTing."""
    return {
        "protocol_version": PROTOCOL_VERSION,
        "brain_pubkey": brain_pubkey,
        "brain_handle": brain_handle,
        "post_type": post_type,
        "content": content,
        "authorship": float(authorship),
        "visibility": visibility,
        "in_reply_to": in_reply_to,
        "ts": int(ts if ts is not None else time.time()),
        "nonce": nonce or uuid.uuid4().hex,
    }


async def publish(payload_unsigned: dict, *, private_key_b64url: str,
                  relay_url: str = RELAY_URL) -> dict:
    """Sign + POST one payload to the relay. Returns a result dict
    {delivered, http_code, post_id, stored_at, error, signature}. Never raises
    on a relay error — surfaces it in the result per §8 (no auto-retry on 4xx)."""
    signed = sign_payload(payload_unsigned, private_key_b64url)
    result: dict[str, Any] = {
        "delivered": False, "http_code": None, "post_id": None,
        "stored_at": None, "error": None, "signature": signed["signature"],
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                relay_url, json=signed,
                headers={"Content-Type": "application/json", "Protocol-Version": "0.5"},
            )
        result["http_code"] = r.status_code
        if r.status_code == 200:
            data = r.json()
            result["delivered"] = True
            result["post_id"] = data.get("post_id")
            result["stored_at"] = data.get("stored_at")
        else:
            # 4xx canonical envelope (§4.1) or 5xx — surface, do not auto-retry here.
            result["error"] = r.text[:500]
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"[:500]
    return result


# ─── Models ──────────────────────────────────────────────────────────────────

class PublishRequest(BaseModel):
    post_type: str
    content: dict
    authorship: float
    visibility: str = "public"
    in_reply_to: Optional[str] = None


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/publish")
async def publish_post(req: PublishRequest, _auth: str = Depends(_operator_auth)):
    """Build, sign, and POST one v0.5 post to the hbar.social relay. Operator-only."""
    if req.post_type not in VALID_POST_TYPES:
        raise HTTPException(400, f"post_type must be one of {sorted(VALID_POST_TYPES)}")
    if not isinstance(req.content, dict) or not req.content:
        raise HTTPException(400, "content object required")
    if not (0.0 <= float(req.authorship) <= 1.0):
        raise HTTPException(400, "authorship must be in [0.0, 1.0]")
    if req.visibility not in ("public", "unlisted"):
        raise HTTPException(400, "visibility must be 'public' or 'unlisted'")

    priv, pub = _brain_keys()
    handle = os.getenv("BRAIN_ID", "") or os.getenv("BRAIN_NAME", "")
    if not handle:
        raise HTTPException(500, "BRAIN_ID not configured")

    payload = build_payload(
        post_type=req.post_type, content=req.content, authorship=req.authorship,
        brain_handle=handle, brain_pubkey=pub, visibility=req.visibility,
        in_reply_to=req.in_reply_to,
    )
    result = await publish(payload, private_key_b64url=priv)

    try:
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO federation_social_outbox
                       (post_id, post_type, content, authorship, visibility,
                        in_reply_to, payload_ts, nonce, signature, relay_url,
                        delivered, http_code, stored_at, error)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (post_id) DO NOTHING
                       RETURNING id""",
                    (result["post_id"], req.post_type, json.dumps(req.content),
                     float(req.authorship), req.visibility, req.in_reply_to,
                     payload["ts"], payload["nonce"], result["signature"], RELAY_URL,
                     result["delivered"], result["http_code"], result["stored_at"],
                     result["error"]),
                )
                row = cur.fetchone()
            conn.commit()
        if row:
            result["outbox_id"] = row[0]
    except Exception as e:
        # Persistence is best-effort: the post may already be public. Surface but don't fail.
        result["outbox_error"] = str(e)[:300]

    if not result["delivered"]:
        raise HTTPException(502, {"published": False, **result})
    return {"published": True, **result}


@router.get("/outbox")
def list_outbox(limit: int = 50, _auth: str = Depends(_operator_auth)):
    """List published posts, newest first. Operator-only."""
    limit = max(1, min(int(limit), 200))
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, post_id, post_type, content, authorship, visibility,
                          in_reply_to, payload_ts, nonce, delivered, http_code,
                          stored_at, error, created_at
                   FROM federation_social_outbox
                   ORDER BY created_at DESC LIMIT %s""",
                (limit,),
            )
            rows = cur.fetchall()
    return {
        "posts": [
            {
                "id": r[0], "post_id": r[1], "post_type": r[2], "content": r[3],
                "authorship": r[4], "visibility": r[5], "in_reply_to": r[6],
                "ts": r[7], "nonce": r[8], "delivered": r[9], "http_code": r[10],
                "stored_at": r[11], "error": r[12],
                "created_at": r[13].isoformat() if r[13] else None,
            }
            for r in rows
        ]
    }
