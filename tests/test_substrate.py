"""Substrate-floor acceptance tests.

Covers all 8 criteria from
ops/prompts/2026-05-01_brainfoundry-substrate-floor.md:

    1. empty brain rejected
    2. mature brain accepted
    3. scraped-only brain rejected
    4. too-new brain rejected
    5. single-source brain rejected
    6. signature verification
    7. cache behavior
    8. persistence

Tests 1-7 run pure-Python (no Postgres). Test 8 (persistence) is a live-DB
integration test gated on the SUBSTRATE_PG_TEST=1 environment variable; it
requires a Postgres instance reachable via DATABASE_URL with a writable
artifact_attestations table.

Run from repo root:

    pytest tests/test_substrate.py -v
    SUBSTRATE_PG_TEST=1 DATABASE_URL=... pytest tests/test_substrate.py -v
"""
from __future__ import annotations

import base64
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


# Each test sets BRAIN_PRIVATE_KEY/BRAIN_PUBLIC_KEY before importing substrate
# functions that sign. Use a fresh keypair per test.

def _b64url_nopad(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


@pytest.fixture
def brain_keypair(monkeypatch):
    priv = Ed25519PrivateKey.generate()
    priv_b = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub_b = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    priv_b64 = _b64url_nopad(priv_b)
    pub_b64 = _b64url_nopad(pub_b)
    monkeypatch.setenv("BRAIN_PRIVATE_KEY", priv_b64)
    monkeypatch.setenv("BRAIN_PUBLIC_KEY", pub_b64)
    monkeypatch.setenv("BRAIN_ID", "test-brain")
    return priv_b64, pub_b64


@pytest.fixture(autouse=True)
def reset_caches():
    from api import substrate
    substrate.cache_clear()
    substrate.peer_cache_clear()
    yield
    substrate.cache_clear()
    substrate.peer_cache_clear()


@pytest.fixture(autouse=True)
def default_thresholds(monkeypatch):
    """Pin defaults so tests are independent of operator env."""
    for var in [
        "FEDERATION_SUBSTRATE_MIN_ARTIFACTS",
        "FEDERATION_SUBSTRATE_MIN_FIRST_PERSON",
        "FEDERATION_SUBSTRATE_MIN_DIVERSITY",
        "FEDERATION_SUBSTRATE_MIN_AGE_DAYS",
        "SUBSTRATE_DEPTH_CACHE_SECONDS",
        "SUBSTRATE_PEER_CACHE_SECONDS",
    ]:
        monkeypatch.delenv(var, raising=False)


# ─── Helpers ────────────────────────────────────────────────────────────────


def _signed_payload(brain_keypair, *, count, first_person, diversity, age_days):
    """Build and sign a substrate-depth payload as if the peer produced it."""
    from api import substrate
    pubkey = brain_keypair[1]
    if age_days is None:
        oldest = None
        newest = None
    else:
        oldest_dt = datetime.now(timezone.utc) - timedelta(days=age_days)
        oldest = oldest_dt.replace(microsecond=0).isoformat()
        newest = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = {
        "brain_pubkey": f"ed25519:{pubkey}",
        "artifact_count": count,
        "total_bytes": count * 1000,
        "oldest_artifact_ts": oldest,
        "newest_artifact_ts": newest,
        "source_diversity": diversity,
        "first_person_count": first_person,
        "computed_at": substrate._iso_now(),
    }
    sig = substrate.sign_with_brain_key(payload)
    return {**payload, "signature": f"ed25519:{sig}"}


# ─── Acceptance criterion tests ────────────────────────────────────────────


def test_1_empty_brain_rejected(brain_keypair):
    """Criterion 1: fresh brain with 0 artifacts → substrate_floor_not_met
    citing artifact_count."""
    from api import substrate
    payload = _signed_payload(brain_keypair, count=0, first_person=0,
                              diversity=0, age_days=None)
    ok, err = substrate.verify_depth_payload(
        payload=payload, pinned_pubkey_b64=brain_keypair[1]
    )
    assert ok, err
    res = substrate.check_floor(payload)
    assert not res.ok
    assert res.code == "substrate_floor_not_met"
    assert "artifact_count" in res.details
    assert res.details["artifact_count"] == {"got": 0, "required": 50}


def test_2_mature_brain_accepted(brain_keypair):
    """Criterion 2: 50 artifacts, ≥25 first-person, ≥2 sources, oldest>7d → ok."""
    from api import substrate
    payload = _signed_payload(brain_keypair, count=50, first_person=30,
                              diversity=3, age_days=14)
    ok, err = substrate.verify_depth_payload(
        payload=payload, pinned_pubkey_b64=brain_keypair[1]
    )
    assert ok, err
    res = substrate.check_floor(payload)
    assert res.ok, f"expected accept, got {res.code} / {res.details}"


def test_3_scraped_only_brain_rejected(brain_keypair):
    """Criterion 3: 50 artifacts all derived → first_person_count cited."""
    from api import substrate
    payload = _signed_payload(brain_keypair, count=50, first_person=0,
                              diversity=3, age_days=14)
    res = substrate.check_floor(payload)
    assert not res.ok
    assert "first_person_count" in res.details
    assert res.details["first_person_count"]["got"] == 0


def test_4_too_new_brain_rejected(brain_keypair):
    """Criterion 4: 50 artifacts ingested today → age_days cited."""
    from api import substrate
    payload = _signed_payload(brain_keypair, count=50, first_person=30,
                              diversity=3, age_days=0)
    res = substrate.check_floor(payload)
    assert not res.ok
    assert "age_days" in res.details
    # all other thresholds met:
    assert "artifact_count" not in res.details
    assert "first_person_count" not in res.details
    assert "source_diversity" not in res.details


def test_5_single_source_brain_rejected(brain_keypair):
    """Criterion 5: 50 artifacts all source_type=note → source_diversity cited."""
    from api import substrate
    payload = _signed_payload(brain_keypair, count=50, first_person=30,
                              diversity=1, age_days=14)
    res = substrate.check_floor(payload)
    assert not res.ok
    assert "source_diversity" in res.details
    assert res.details["source_diversity"]["got"] == 1


def test_6_broken_signature_rejected(brain_keypair):
    """Criterion 6: depth payload with broken signature → signature_invalid,
    never reaches threshold check."""
    from api import substrate
    payload = _signed_payload(brain_keypair, count=50, first_person=30,
                              diversity=3, age_days=14)
    # Tamper with the signature.
    payload["signature"] = "ed25519:" + "A" * 86

    ok, err = substrate.verify_depth_payload(
        payload=payload, pinned_pubkey_b64=brain_keypair[1]
    )
    assert not ok
    assert err == "signature_invalid"

    # Missing prefix
    payload["signature"] = "AAAA"
    ok, err = substrate.verify_depth_payload(
        payload=payload, pinned_pubkey_b64=brain_keypair[1]
    )
    assert not ok
    assert err == "signature_invalid"

    # Tampered body but original signature
    good = _signed_payload(brain_keypair, count=50, first_person=30,
                           diversity=3, age_days=14)
    tampered = {**good, "artifact_count": 999_999}
    ok, err = substrate.verify_depth_payload(
        payload=tampered, pinned_pubkey_b64=brain_keypair[1]
    )
    assert not ok
    assert err == "signature_invalid"


def test_6b_wrong_pinned_pubkey_rejected(brain_keypair):
    """Signature verifies against a DIFFERENT pinned pubkey → rejected.

    Closes T1: a peer who serves a depth payload signed with their own key
    but is pinned in our registry under a different key cannot pass.
    """
    from api import substrate
    payload = _signed_payload(brain_keypair, count=50, first_person=30,
                              diversity=3, age_days=14)

    # Generate an unrelated pubkey
    other_priv = Ed25519PrivateKey.generate()
    other_pub = other_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    other_pub_b64 = _b64url_nopad(other_pub)

    ok, err = substrate.verify_depth_payload(
        payload=payload, pinned_pubkey_b64=other_pub_b64
    )
    assert not ok
    assert err == "signature_invalid"


def test_7_cache_behavior(brain_keypair, monkeypatch):
    """Criterion 7: second request within 5 minutes returns cached payload."""
    from api import substrate

    # Make compute_depth deterministic & cheap; capture call count.
    call_count = {"n": 0}

    def fake_compute_depth(conn=None):
        call_count["n"] += 1
        return substrate.SubstrateDepth(
            brain_pubkey=f"ed25519:{brain_keypair[1]}",
            artifact_count=call_count["n"],  # would change every call if cache miss
            total_bytes=0,
            oldest_artifact_ts=None,
            newest_artifact_ts=None,
            source_diversity=0,
            first_person_count=0,
            computed_at=substrate._iso_now(),
        )
    monkeypatch.setattr(substrate, "compute_depth", fake_compute_depth)

    p1 = substrate.signed_depth_payload_cached()
    p2 = substrate.signed_depth_payload_cached()
    assert p1 == p2
    assert call_count["n"] == 1, "second call should hit cache"

    # Expire the cache and confirm recompute.
    substrate.cache_clear()
    p3 = substrate.signed_depth_payload_cached()
    assert call_count["n"] == 2
    assert p3["artifact_count"] != p1["artifact_count"]


def test_7b_cache_ttl_env(brain_keypair, monkeypatch):
    """Cache TTL is env-configurable."""
    from api import substrate
    monkeypatch.setenv("SUBSTRATE_DEPTH_CACHE_SECONDS", "1")
    assert substrate.cache_seconds() == 1

    monkeypatch.setenv("SUBSTRATE_DEPTH_CACHE_SECONDS", "garbage")
    assert substrate.cache_seconds() == 300  # falls back to default


def test_thresholds_env_override(monkeypatch):
    """Operator can lower the floor via env vars (for test brains)."""
    from api import substrate
    monkeypatch.setenv("FEDERATION_SUBSTRATE_MIN_ARTIFACTS", "2")
    monkeypatch.setenv("FEDERATION_SUBSTRATE_MIN_FIRST_PERSON", "1")
    monkeypatch.setenv("FEDERATION_SUBSTRATE_MIN_DIVERSITY", "1")
    monkeypatch.setenv("FEDERATION_SUBSTRATE_MIN_AGE_DAYS", "0")
    th = substrate.thresholds()
    assert th == {"min_artifacts": 2, "min_first_person": 1,
                  "min_diversity": 1, "min_age_days": 0}


def test_canonical_signing_roundtrip(brain_keypair):
    """Sanity check: sign + verify with this brain's own pubkey."""
    from api import substrate
    payload = {"a": 1, "b": "hello", "c": [1, 2, 3]}
    sig = substrate.sign_with_brain_key(payload)
    assert substrate.verify_with_pubkey(brain_keypair[1], sig, payload)
    # Mutated payload must fail
    assert not substrate.verify_with_pubkey(
        brain_keypair[1], sig, {"a": 2, "b": "hello", "c": [1, 2, 3]}
    )


def test_record_attestation_input_validation(brain_keypair):
    """Bad source_type / first_person / hash format raise before DB."""
    from api import substrate
    with pytest.raises(ValueError):
        substrate.record_attestation(
            content_hash="sha256:abc",
            source_type="not_a_real_type",
            byte_size=10,
            first_person_attestation="authored_by_owner",
        )
    with pytest.raises(ValueError):
        substrate.record_attestation(
            content_hash="sha256:abc",
            source_type="document",
            byte_size=10,
            first_person_attestation="not_a_real_label",
        )
    with pytest.raises(ValueError):
        substrate.record_attestation(
            content_hash="MD5:abc",  # wrong prefix
            source_type="document",
            byte_size=10,
            first_person_attestation="authored_by_owner",
        )


# ─── Criterion 8: persistence (live-DB integration) ────────────────────────


pg_required = pytest.mark.skipif(
    os.getenv("SUBSTRATE_PG_TEST", "0") != "1" or not os.getenv("DATABASE_URL"),
    reason="set SUBSTRATE_PG_TEST=1 + DATABASE_URL to run live-DB tests",
)


@pg_required
def test_8_persistence_roundtrip(brain_keypair):
    """Criterion 8: write rows, recompute depth, verify counts survive
    'restart' (re-imports module + recomputes from DB)."""
    import importlib
    from api import substrate as substrate_mod

    # Clean slate
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS artifact_attestations")
    conn.close()

    substrate_mod.init_tables()

    # Insert 3 attestations spanning 2 source types + 1 derived.
    for i, (src, fp) in enumerate([
        ("document", "authored_by_owner"),
        ("note", "addressed_to_owner"),
        ("note", "derived"),
    ]):
        substrate_mod.record_attestation(
            content_hash=f"sha256:{i:064x}",
            source_type=src,
            byte_size=100 * (i + 1),
            first_person_attestation=fp,
        )

    # Simulate restart: clear caches + re-import.
    substrate_mod.cache_clear()
    importlib.reload(substrate_mod)

    depth = substrate_mod.compute_depth()
    assert depth.artifact_count == 3
    assert depth.total_bytes == 100 + 200 + 300
    assert depth.source_diversity == 2  # document, note
    assert depth.first_person_count == 2  # 2 non-derived
