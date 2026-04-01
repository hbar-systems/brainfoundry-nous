from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


import json
from pathlib import Path


_OPERATORS_PATH = Path(__file__).parent / "operators.json"


def load_operator(operator_id: str) -> Dict[str, Any]:
    if not _OPERATORS_PATH.exists():
        raise ValueError("operator_registry_missing")

    data = json.loads(_OPERATORS_PATH.read_text())
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


def issue_permit(*, secret: str, claims: Dict[str, Any]) -> str:
    """
    Issues a compact, signed permit token.

    Format: base64url(header).base64url(claims).base64url(signature)
    Signature covers "header.payload" (HMAC-SHA256).
    """
    header = {"alg": "HS256", "typ": "HBAR_PERMIT", "v": 1}
    header_b64 = _b64url_json(header)
    claims_b64 = _b64url_json(claims)
    signing_input = f"{header_b64}.{claims_b64}"
    sig_b64 = _sign(secret, signing_input)
    return f"{signing_input}.{sig_b64}"


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
        "iss": "hbar-brain",
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


