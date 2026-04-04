from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


import json
import os
from pathlib import Path


_OPERATORS_PATH = Path(__file__).parent / "operators.json"


def load_operator(operator_id: str) -> Dict[str, Any]:
    if not _OPERATORS_PATH.exists():
        raise ValueError("operator_registry_missing")

    raw = _OPERATORS_PATH.read_text()
    # Resolve ${VAR} placeholders using environment variables
    for key, val in os.environ.items():
        raw = raw.replace(f"${{{key}}}", val)
    data = json.loads(raw)
    for op in data.get("operators", []):
        if op.get("operator_id") == operator_id and op.get("active") is True:
            return op

    raise ValueError("operator_not_found")


@dataclass(frozen=True)
class IdentityContext:
    operator_id: str
    trust_tier: str  # public | member | collab | operator | root
    client_id: str


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_json(obj: Dict[str, Any]) -> str:
    raw = json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _b64url(raw)


def _sign(secret: str, msg: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()
    return _b64url(sig)


def verify_permit(*, secret: str, token: str) -> Dict[str, Any]:
    """
    Verifies signature + basic expiry.
    Returns decoded claims dict on success.
    Raises ValueError on failure.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid_token_format")

    header_b64, claims_b64, sig_b64 = parts
    signing_input = f"{header_b64}.{claims_b64}"
    expected = _sign(secret, signing_input)

    if not hmac.compare_digest(expected, sig_b64):
        raise ValueError("invalid_signature")

    # Decode claims
    padded = claims_b64 + "=" * (-len(claims_b64) % 4)
    claims_raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
    claims = json.loads(claims_raw.decode("utf-8"))

    exp = claims.get("exp")
    now = int(time.time())
    if exp is not None:
        try:
            exp_int = int(exp)
        except Exception:
            raise ValueError("invalid_exp")
        if now >= exp_int:
            raise ValueError("expired")

    return claims


def build_basic_permit_claims(
    *,
    permit_id: str,
    permit_type: str,
    strain_id: str,
    subject: str,
    audience: str,
    ttl_seconds: int,
    reason: str,
    constraints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = int(time.time())
    return {
        "permit_id": permit_id,
        "permit_type": permit_type,
        "strain_id": strain_id,
        "sub": subject,
        "aud": audience,
        "iat": now,
        "exp": now + int(ttl_seconds),
        "ttl_seconds": int(ttl_seconds),
        "reason": reason,
        "constraints": constraints or {},
        "v": 1,
    }


def issue_permit(
    *,
    secret: str,
    operator_id: str,
    client_id: str,
    permit_type: str,
    ttl_seconds: int,
    reason: str,
    constraints: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Issues a signed permit token using the same HS256 token format as assertions.
    Token structure: base64url(header).base64url(claims).base64url(sig)
    """
    from api.identity.permits import build_permit

    claims = build_permit(
        permit_type=permit_type,
        operator_id=operator_id,
        client_id=client_id,
        ttl_seconds=ttl_seconds,
        reason=reason,
        constraints=constraints,
    )

    header = {"alg": "HS256", "typ": "HBAR_PERMIT", "v": 1}
    header_b64 = _b64url_json(header)
    claims_b64 = _b64url_json(claims)
    signing_input = f"{header_b64}.{claims_b64}"
    sig_b64 = _sign(secret, signing_input)
    return f"{signing_input}.{sig_b64}"

def issue_assertion(
    *,
    secret: str,
    operator_id: str,
    client_id: str,
    strain_id: str,
    ttl_seconds: int = 900,
) -> str:
    operator = load_operator(operator_id)

    now = int(time.time())
    claims = {
        "iss": os.getenv("BRAIN_ID", "brainfoundry-node"),
        "sub": operator_id,
        "aud": client_id,
        "strain_id": strain_id,
        "trust_tier": operator.get("trust_tier"),
        "iat": now,
        "exp": now + int(ttl_seconds),
        "v": 1,
    }

    header = {"alg": "HS256", "typ": "HBAR_ASSERTION", "v": 1}
    header_b64 = _b64url_json(header)
    claims_b64 = _b64url_json(claims)
    signing_input = f"{header_b64}.{claims_b64}"
    sig_b64 = _sign(secret, signing_input)
    return f"{signing_input}.{sig_b64}"




def verify_assertion(*, secret: str, token: str, expected_aud: str) -> Dict[str, Any]:
    """
    Verifies identity assertion token.
    - signature + exp
    - aud matches expected_aud
    Returns decoded claims.
    """
    claims = verify_permit(secret=secret, token=token)  # same token structure + exp check

    aud = claims.get("aud")
    if aud != expected_aud:
        raise ValueError("aud_mismatch")

    if not claims.get("sub"):
        raise ValueError("missing_sub")

    if not claims.get("strain_id"):
        raise ValueError("missing_strain_id")

    return claims


# ---------------------------------------------------------------------------
# Federation signing — ED25519 (asymmetric, no shared secret)
#
# Intra-brain permits use HMAC-SHA256 (above) — same brain issues and verifies.
# Cross-brain assertions use ED25519 — Brain A signs with private key,
# Brain B fetches Brain A's public key from GET /identity and verifies.
# No secrets are shared. Sovereignty preserved.
# ---------------------------------------------------------------------------

def generate_brain_keypair() -> Tuple[str, str]:
    """
    Generate a new ED25519 keypair for this brain node.
    Run once at brain setup via scripts/generate_keypair.py.

    Returns:
        (private_key_b64, public_key_b64) — both base64url-encoded, no padding.
        Store private_key_b64 as BRAIN_PRIVATE_KEY in .env (never share).
        Store public_key_b64 as BRAIN_PUBLIC_KEY in .env and brain_identity.yaml.
    """
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    public_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return _b64url(private_bytes), _b64url(public_bytes)


def issue_federation_assertion(
    *,
    private_key_b64: str,
    issuer_brain_id: str,
    audience_brain_id: str,
    subject: str,
    ttl_seconds: int = 300,
    claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Issue a cross-brain assertion signed with this brain's ED25519 private key.

    The receiving brain verifies with verify_federation_assertion() using the
    issuing brain's public key (fetched from GET /identity on the issuing brain).

    Args:
        private_key_b64: BRAIN_PRIVATE_KEY from .env (base64url, no padding)
        issuer_brain_id: brain_id of this brain (the signer)
        audience_brain_id: brain_id of the intended recipient
        subject: what this assertion is about (e.g. operator_id or action)
        ttl_seconds: expiry window (default 5 min)
        claims: optional additional claims to include

    Returns:
        Signed token string: base64url(header).base64url(claims).base64url(sig)
    """
    private_bytes = base64.urlsafe_b64decode(private_key_b64 + "==")
    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)

    now = int(time.time())
    payload: Dict[str, Any] = {
        "iss": issuer_brain_id,
        "aud": audience_brain_id,
        "sub": subject,
        "iat": now,
        "exp": now + int(ttl_seconds),
        "v": 1,
    }
    if claims:
        payload.update(claims)

    header = {"alg": "EdDSA", "typ": "HBAR_FED_ASSERTION", "v": 1}
    header_b64 = _b64url_json(header)
    claims_b64 = _b64url_json(payload)
    signing_input = f"{header_b64}.{claims_b64}".encode()
    sig_b64 = _b64url(private_key.sign(signing_input))
    return f"{header_b64}.{claims_b64}.{sig_b64}"


def verify_federation_assertion(
    *,
    public_key_b64: str,
    token: str,
    expected_audience: str,
) -> Dict[str, Any]:
    """
    Verify a cross-brain assertion using the issuing brain's public key.

    Fetch the public key from GET /identity on the issuing brain
    (brain_identity.yaml -> public_key field).

    Args:
        public_key_b64: BRAIN_PUBLIC_KEY of the issuing brain (base64url, no padding)
        token: the signed token string from issue_federation_assertion()
        expected_audience: this brain's brain_id -- rejects tokens not addressed to us

    Returns:
        Decoded claims dict on success.

    Raises:
        ValueError: invalid_token_format | invalid_signature | aud_mismatch | expired
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid_token_format")

    header_b64, claims_b64, sig_b64 = parts
    signing_input = f"{header_b64}.{claims_b64}".encode()

    public_bytes = base64.urlsafe_b64decode(public_key_b64 + "==")
    public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
    sig = base64.urlsafe_b64decode(sig_b64 + "==")

    try:
        public_key.verify(sig, signing_input)
    except Exception:
        raise ValueError("invalid_signature")

    padded = claims_b64 + "=" * (-len(claims_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded).decode())

    if payload.get("aud") != expected_audience:
        raise ValueError("aud_mismatch")

    exp = payload.get("exp")
    if exp is not None and int(time.time()) >= int(exp):
        raise ValueError("expired")

    return payload
