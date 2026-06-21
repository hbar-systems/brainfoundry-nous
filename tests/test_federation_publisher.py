"""Tests for the federation publisher canonicalizer + signer (v0.5).

Guards the two PROTOCOL_CONTRACT landmines that make naive json.dumps fail:
  1. integer-valued floats: authorship 1.0 must canonicalize to "1", not "1.0"
  2. non-ASCII must stay raw UTF-8, not \\u-escaped
Plus a sign->verify round-trip, and that the CLI's vendored canonicalizer is
identical to api/federation_jcs (no drift between the two copies).

Created 2026-06-21.
"""
import base64
import importlib.util
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

from api import federation_jcs as jcs


def test_authorship_integer_float_collapses_to_int():
    # authorship 1.0 (pure brain) is the default case — must be "1".
    assert jcs.canonicalize({"authorship": 1.0}) == b'{"authorship":1}'
    assert jcs.canonicalize({"authorship": 0.0}) == b'{"authorship":0}'
    assert jcs.canonicalize({"authorship": 0.7}) == b'{"authorship":0.7}'


def test_non_ascii_stays_raw_utf8():
    out = jcs.canonicalize({"body": "Größe — souverän"})
    assert out == '{"body":"Größe — souverän"}'.encode("utf-8")
    assert b"\\u" not in out


def test_keys_sorted_no_whitespace():
    out = jcs.canonicalize({"b": 1, "a": 2, "ts": 3})
    assert out == b'{"a":2,"b":1,"ts":3}'


def test_signature_strip_and_roundtrip():
    sk = Ed25519PrivateKey.generate()
    seed = sk.private_bytes_raw()
    priv = base64.urlsafe_b64encode(seed).rstrip(b"=").decode()
    pub_raw = sk.public_key().public_bytes_raw()

    payload = {
        "protocol_version": "0.5", "brain_handle": "hbar",
        "post_type": "text", "content": {"body": "hi"},
        "authorship": 1.0, "visibility": "public", "in_reply_to": None,
        "ts": 1750000000, "nonce": "a1b2c3d4e5f60718",
    }
    signed = jcs.sign_payload(payload, priv)
    assert "signature" in signed
    # Verify against canonical bytes of payload-minus-signature.
    sig = base64.urlsafe_b64decode(signed["signature"] + "==")
    Ed25519PublicKey.from_public_bytes(pub_raw).verify(sig, jcs.signing_bytes(signed))


def test_cli_canonicalizer_matches_module():
    """The CLI vendors its own copy of the canonicalizer — assert no drift."""
    cli_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "publish_post.py")
    spec = importlib.util.spec_from_file_location("publish_post", cli_path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    cases = [
        {"authorship": 1.0, "b": "ä", "a": [1, 2, 3], "n": None, "t": True},
        {"content": {"body": "Größe — x"}, "ts": 1750000000, "authorship": 0.7},
    ]
    for c in cases:
        assert cli.canonicalize(c) == jcs.canonicalize(c)
