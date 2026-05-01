"""Federation DM v0.5 — brain↔brain direct messaging.

This is the lightweight DM layer, separate from /v1/federation/assertion
(which is the high-security trust handshake using pinned-peer TOML).

Trust model for v0.5:
- Sender signs the payload with their brain's private key.
- Recipient fetches sender's /identity to learn their public key, verifies sig.
- T1-vulnerable: a malicious peer could claim to be alice and serve their own
  pubkey at alice.brainfoundry.ai/identity. Acceptable for first-friend test;
  upgrade to known_peers.toml-pinned auth in v0.6+.

Endpoints:
- POST /v1/federation/dm/send       (operator-auth) — sign + deliver
- POST /v1/federation/dm/receive    (public)        — accept signed DM
- GET  /v1/federation/dm/inbox      (operator-auth) — list received
- GET  /v1/federation/dm/outbox     (operator-auth) — list sent
"""
from __future__ import annotations

import base64
import json
import os
import time
import uuid
from typing import Optional

import httpx
import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


router = APIRouter(prefix="/v1/federation/dm", tags=["federation-dm"])

# Reuse the same X-API-Key header as the rest of the brain.
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _operator_auth(x_api_key: str = Security(_api_key_header)) -> str:
    """Operator-only gate. Same X-API-Key as rest of brain."""
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

INBOX_DDL = """
CREATE TABLE IF NOT EXISTS federation_inbox (
    id          SERIAL PRIMARY KEY,
    from_brain  TEXT NOT NULL,
    from_pubkey TEXT NOT NULL,
    message     TEXT NOT NULL,
    payload_ts  BIGINT NOT NULL,
    nonce       TEXT NOT NULL,
    signature   TEXT NOT NULL,
    received_at TIMESTAMP DEFAULT NOW(),
    read_at     TIMESTAMP,
    UNIQUE (from_brain, nonce)
);
CREATE INDEX IF NOT EXISTS federation_inbox_received_idx ON federation_inbox (received_at DESC);
"""

OUTBOX_DDL = """
CREATE TABLE IF NOT EXISTS federation_outbox (
    id            SERIAL PRIMARY KEY,
    to_brain      TEXT NOT NULL,
    to_endpoint   TEXT NOT NULL,
    message       TEXT NOT NULL,
    payload_ts    BIGINT NOT NULL,
    nonce         TEXT NOT NULL,
    signature     TEXT NOT NULL,
    sent_at       TIMESTAMP DEFAULT NOW(),
    delivered     BOOLEAN DEFAULT FALSE,
    delivery_code INT,
    delivery_err  TEXT
);
CREATE INDEX IF NOT EXISTS federation_outbox_sent_idx ON federation_outbox (sent_at DESC);
"""


def init_tables() -> None:
    """Idempotent table create. Called from main.py startup hook."""
    if not os.getenv("DATABASE_URL"):
        return
    try:
        with _db() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(INBOX_DDL)
                cur.execute(OUTBOX_DDL)
    except Exception as e:
        print(f"[federation_dm] table init skipped: {e}", flush=True)


# ─── Crypto helpers ──────────────────────────────────────────────────────────

def _canonical(payload: dict) -> bytes:
    """Deterministic JSON-bytes for signing. Sorted keys, no whitespace."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def _load_private_key() -> Ed25519PrivateKey:
    pk_b64 = os.getenv("BRAIN_PRIVATE_KEY", "")
    if not pk_b64:
        raise HTTPException(500, "BRAIN_PRIVATE_KEY not configured — run scripts/generate_keypair.py")
    raw = base64.urlsafe_b64decode(pk_b64 + "==")
    return Ed25519PrivateKey.from_private_bytes(raw)


def _verify_with_pubkey(pubkey_b64: str, signature_b64: str, msg_bytes: bytes) -> bool:
    try:
        pub_raw = base64.urlsafe_b64decode(pubkey_b64 + "==")
        sig_raw = base64.urlsafe_b64decode(signature_b64 + "==")
        Ed25519PublicKey.from_public_bytes(pub_raw).verify(sig_raw, msg_bytes)
        return True
    except Exception:
        return False


# ─── Identity discovery (T1-vulnerable for v0.5) ─────────────────────────────

async def _fetch_peer_pubkey(handle: str) -> tuple[str, str]:
    """Fetch peer's /identity to learn their public key.

    Returns (pubkey_b64, endpoint). Raises HTTPException if unreachable
    or malformed. T1: if attacker controls the endpoint, they pick the key.
    Fine for first-friend test; pinned-peers in v0.6.
    """
    endpoint = f"https://{handle}.brainfoundry.ai"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{endpoint}/identity")
        if r.status_code != 200:
            raise HTTPException(502, f"Peer {handle} /identity returned {r.status_code}")
        data = r.json()
        pubkey = data.get("public_key")
        if not pubkey:
            raise HTTPException(502, f"Peer {handle} /identity missing public_key")
        return pubkey, endpoint
    except httpx.RequestError as e:
        raise HTTPException(502, f"Peer {handle} unreachable: {e}")


# ─── Models ──────────────────────────────────────────────────────────────────

class SendDMRequest(BaseModel):
    to: str       # recipient handle, e.g. "yury"
    message: str  # message text


class ReceiveDMRequest(BaseModel):
    from_brain: str
    from_pubkey: str
    message: str
    ts: int
    nonce: str
    signature: str


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/send")
async def send_dm(req: SendDMRequest, _auth: str = Depends(_operator_auth)):
    """Sign + deliver a DM to another brain. Operator-only."""
    if not req.to or not req.message.strip():
        raise HTTPException(400, "to and message required")
    if len(req.message) > 8000:
        raise HTTPException(400, "message too long (max 8000 chars)")

    my_brain = os.getenv("BRAIN_ID", "")
    my_pubkey = os.getenv("BRAIN_PUBLIC_KEY", "")
    if not my_brain or not my_pubkey:
        raise HTTPException(500, "BRAIN_ID or BRAIN_PUBLIC_KEY not configured")

    peer_pubkey, peer_endpoint = await _fetch_peer_pubkey(req.to)

    nonce = uuid.uuid4().hex
    ts = int(time.time())
    payload = {
        "from_brain": my_brain,
        "from_pubkey": my_pubkey,
        "message": req.message,
        "ts": ts,
        "nonce": nonce,
    }
    sig_raw = _load_private_key().sign(_canonical(payload))
    signature = base64.urlsafe_b64encode(sig_raw).decode().rstrip("=")
    body = {**payload, "signature": signature}

    delivered = False
    delivery_code = None
    delivery_err = None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{peer_endpoint}/v1/federation/dm/receive", json=body)
        delivery_code = r.status_code
        if r.status_code == 200:
            delivered = True
        else:
            delivery_err = r.text[:300]
    except Exception as e:
        delivery_err = str(e)[:300]

    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO federation_outbox
                   (to_brain, to_endpoint, message, payload_ts, nonce, signature,
                    delivered, delivery_code, delivery_err)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (req.to, peer_endpoint, req.message, ts, nonce, signature,
                 delivered, delivery_code, delivery_err),
            )
            new_id = cur.fetchone()[0]
        conn.commit()

    return {"id": new_id, "delivered": delivered, "delivery_code": delivery_code, "error": delivery_err}


@router.post("/receive")
async def receive_dm(req: ReceiveDMRequest):
    """Accept a signed DM from another brain. Public — no auth required."""
    if not req.from_brain or not req.message.strip():
        raise HTTPException(400, "from_brain and message required")

    # Anti-clock-skew + replay window: reject DMs older than 5 min or future-dated
    now = int(time.time())
    if abs(now - req.ts) > 300:
        raise HTTPException(401, "ts outside 5-minute window")

    payload_for_sig = {
        "from_brain": req.from_brain,
        "from_pubkey": req.from_pubkey,
        "message": req.message,
        "ts": req.ts,
        "nonce": req.nonce,
    }
    if not _verify_with_pubkey(req.from_pubkey, req.signature, _canonical(payload_for_sig)):
        raise HTTPException(401, "signature verification failed")

    # Optional: fetch sender's /identity and confirm pubkey matches what they advertise.
    # Skipped for v0.5 — sender is allowed to assert their own pubkey + sign with it.
    # T1-aware: an attacker could send a DM claiming to be alice with their own pubkey.
    # The recipient sees from_brain=alice, from_pubkey=<attacker_key>. Mitigation: UI
    # shows pubkey alongside handle so operator notices a different key for a known peer.

    try:
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO federation_inbox
                       (from_brain, from_pubkey, message, payload_ts, nonce, signature)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (from_brain, nonce) DO NOTHING
                       RETURNING id""",
                    (req.from_brain, req.from_pubkey, req.message, req.ts, req.nonce, req.signature),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            return {"received": True, "duplicate": True}
        return {"received": True, "id": row[0]}
    except Exception as e:
        raise HTTPException(500, f"DM persist failed: {e}")


@router.get("/inbox")
def list_inbox(limit: int = 50, _auth: str = Depends(_operator_auth)):
    """List received DMs, newest first. Operator-only."""
    limit = max(1, min(int(limit), 200))
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, from_brain, from_pubkey, message, payload_ts, nonce,
                          received_at, read_at
                   FROM federation_inbox
                   ORDER BY received_at DESC LIMIT %s""",
                (limit,),
            )
            rows = cur.fetchall()
    return {
        "messages": [
            {
                "id": r[0], "from_brain": r[1], "from_pubkey": r[2], "message": r[3],
                "payload_ts": r[4], "nonce": r[5],
                "received_at": r[6].isoformat() if r[6] else None,
                "read_at": r[7].isoformat() if r[7] else None,
            }
            for r in rows
        ]
    }


@router.get("/outbox")
def list_outbox(limit: int = 50, _auth: str = Depends(_operator_auth)):
    """List sent DMs, newest first. Operator-only."""
    limit = max(1, min(int(limit), 200))
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, to_brain, to_endpoint, message, payload_ts, nonce,
                          sent_at, delivered, delivery_code, delivery_err
                   FROM federation_outbox
                   ORDER BY sent_at DESC LIMIT %s""",
                (limit,),
            )
            rows = cur.fetchall()
    return {
        "messages": [
            {
                "id": r[0], "to_brain": r[1], "to_endpoint": r[2], "message": r[3],
                "payload_ts": r[4], "nonce": r[5],
                "sent_at": r[6].isoformat() if r[6] else None,
                "delivered": r[7], "delivery_code": r[8], "delivery_err": r[9],
            }
            for r in rows
        ]
    }


@router.post("/inbox/{msg_id}/read")
def mark_read(msg_id: int, _auth: str = Depends(_operator_auth)):
    """Mark a received DM as read."""
    with _db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE federation_inbox SET read_at = NOW() WHERE id = %s AND read_at IS NULL RETURNING id",
                (msg_id,),
            )
            updated = cur.fetchone()
        conn.commit()
    return {"id": msg_id, "marked_read": bool(updated)}
