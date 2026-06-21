#!/usr/bin/env python3
"""publish_post.py — Created 2026-06-21

Self-contained CLI to publish ONE ED25519-signed v0.5 post to the hbar.social
relay (PROTOCOL_CONTRACT §8). Mirrors api/federation_publisher.py but vendors
the JCS canonicalizer inline and uses only the stdlib for HTTP, so it runs
unchanged inside the brain's api container:

    docker compose exec api python /home/hbar/brain/scripts/publish_post.py \
        --type text --authorship 1.0 \
        --body "First post from a sovereign brain — curated by a mind, not an algorithm."

Reads BRAIN_PRIVATE_KEY (required) and BRAIN_PUBLIC_KEY / BRAIN_ID from env.
The public key is derived from the private key if BRAIN_PUBLIC_KEY is unset, so
they can never disagree. Never prints the private key.

Canonicalizer is byte-identical to the relay (hbar.social lib/protocol.ts),
proven by hbar.social/repos/site/scripts/proof_canon.py. Do NOT swap in
json.dumps(sort_keys=True) — it diverges on authorship=1.0 and non-ASCII.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

VALID_POST_TYPES = {
    "text", "fivefield", "thought_drop", "project_announcement", "brain_summary",
}


# ─── JCS canonicalizer (vendored from api/federation_jcs.py) ──────────────────

def _es_number(n: float | int) -> str:
    if isinstance(n, bool):
        raise TypeError("bool is not a JSON number")
    if isinstance(n, int):
        return str(n)
    if n != n or n in (float("inf"), float("-inf")):
        raise ValueError("NaN/Infinity are not valid JSON")
    if n.is_integer():
        return str(int(n))  # 1.0 -> "1"
    return repr(n)


def _emit(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _es_number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_emit(v) for v in value) + "]"
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda kv: kv[0])
        return "{" + ",".join(
            json.dumps(k, ensure_ascii=False) + ":" + _emit(v) for k, v in items
        ) + "}"
    raise TypeError(f"unserializable type: {type(value).__name__}")


def canonicalize(value: Any) -> bytes:
    return _emit(value).encode("utf-8")


def sign_payload(payload: dict, private_key_b64url: str) -> dict:
    seed = base64.urlsafe_b64decode(private_key_b64url + "=" * (-len(private_key_b64url) % 4))
    sk = Ed25519PrivateKey.from_private_bytes(seed)
    unsigned = {k: v for k, v in payload.items() if k != "signature"}
    sig = sk.sign(canonicalize(unsigned))
    return {**payload, "signature": base64.urlsafe_b64encode(sig).rstrip(b"=").decode()}


def derive_pubkey(private_key_b64url: str) -> str:
    seed = base64.urlsafe_b64decode(private_key_b64url + "=" * (-len(private_key_b64url) % 4))
    raw_pub = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()
    return base64.urlsafe_b64encode(raw_pub).rstrip(b"=").decode()


# ─── Main ─────────────────────────────────────────────────────────────────────

def build_content(args: argparse.Namespace) -> dict:
    if args.content_json:
        return json.loads(args.content_json)
    if args.type in ("text", "project_announcement"):
        if not args.body:
            sys.exit(f"--body required for post_type '{args.type}'")
        content: dict = {"body": args.body}
        if args.title:
            content["title"] = args.title
        return content
    if args.type == "thought_drop":
        if not args.body:
            sys.exit("--body required for thought_drop")
        content = {"body": args.body}
        if args.title:
            content["title"] = args.title
        return content
    sys.exit(f"post_type '{args.type}' requires --content-json")


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish one signed v0.5 post to hbar.social")
    ap.add_argument("--type", default="text", choices=sorted(VALID_POST_TYPES))
    ap.add_argument("--body", help="body text (text/thought_drop/project_announcement)")
    ap.add_argument("--title", help="optional title")
    ap.add_argument("--content-json", help="full content object as JSON (overrides --body/--title)")
    ap.add_argument("--authorship", type=float, default=1.0, help="0.0=human .. 1.0=pure brain")
    ap.add_argument("--visibility", default="public", choices=["public", "unlisted"])
    ap.add_argument("--in-reply-to", default=None)
    ap.add_argument("--handle", default=None, help="override brain_handle (default $BRAIN_ID)")
    ap.add_argument("--relay-url", default=os.getenv("HBAR_SOCIAL_RELAY_URL",
                                                     "https://hbar.social/v1/relay/post"))
    ap.add_argument("--dry-run", action="store_true",
                    help="print canonical bytes + signature, do NOT POST")
    args = ap.parse_args()

    priv = os.getenv("BRAIN_PRIVATE_KEY", "")
    if not priv:
        sys.exit("BRAIN_PRIVATE_KEY not set in env")
    pub = os.getenv("BRAIN_PUBLIC_KEY", "") or derive_pubkey(priv)
    handle = args.handle or os.getenv("BRAIN_ID", "")
    if not handle:
        sys.exit("BRAIN_ID not set and --handle not given")
    if not (0.0 <= args.authorship <= 1.0):
        sys.exit("--authorship must be in [0.0, 1.0]")

    payload = {
        "protocol_version": "0.5",
        "brain_pubkey": pub,
        "brain_handle": handle,
        "post_type": args.type,
        "content": build_content(args),
        "authorship": float(args.authorship),
        "visibility": args.visibility,
        "in_reply_to": args.in_reply_to,
        "ts": int(time.time()),
        "nonce": uuid.uuid4().hex,
    }
    signed = sign_payload(payload, priv)

    print("canonical signing bytes:")
    print("  " + canonicalize(payload).decode("utf-8"))
    print(f"brain_handle={handle}  brain_pubkey={pub}")
    print(f"authorship={payload['authorship']}  visibility={payload['visibility']}")
    print(f"signature={signed['signature']}")

    if args.dry_run:
        print("\n[dry-run] not posting.")
        return 0

    body = json.dumps(signed).encode("utf-8")
    req = urllib.request.Request(
        args.relay_url, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Protocol-Version": "0.5",
            # The relay sits behind a CDN/WAF that 403s the default
            # Python-urllib UA (Cloudflare error 1010). Identify as the brain.
            "User-Agent": "brainfoundry-nous-publisher/0.5 (+https://hbar.brainfoundry.ai)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            code = resp.status
            text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        code = e.code
        text = e.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"\nPOST failed: {type(e).__name__}: {e}")
        return 1

    print(f"\nHTTP {code}")
    print(text)
    if code == 200:
        try:
            data = json.loads(text)
            pid = data.get("post_id")
            print(f"\nPUBLISHED post_id={pid}")
            print(f"verify: {args.relay_url.rsplit('/post', 1)[0]}/post/{pid}")
        except Exception:
            pass
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
