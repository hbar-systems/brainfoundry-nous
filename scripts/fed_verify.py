"""
Part A federation handshake — VERIFY side.

Inside a brain container, fetch the issuer's /identity to get its public key,
then verify the token was signed by it and addressed to this brain.

Usage:
    docker compose exec brain-api python3 scripts/fed_verify.py \
        --token <token> \
        --issuer-endpoint https://yury.brainfoundry.ai
"""
import argparse
import os
import sys
import json

sys.path.insert(0, "/app")

import httpx
from api.identity.core import verify_federation_assertion


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--issuer-endpoint", required=True, help="e.g. https://yury.brainfoundry.ai")
    args = ap.parse_args()

    brain_id = os.getenv("BRAIN_ID")
    if not brain_id:
        print("ERROR: BRAIN_ID must be set in env", file=sys.stderr)
        sys.exit(2)

    url = args.issuer_endpoint.rstrip("/") + "/identity"
    resp = httpx.get(url, timeout=10.0)
    resp.raise_for_status()
    identity = resp.json()

    issuer_brain_id = identity.get("brain_id")
    public_key = identity.get("public_key")
    if not issuer_brain_id or not public_key:
        print(f"ERROR: /identity missing brain_id or public_key: {identity}", file=sys.stderr)
        sys.exit(3)

    try:
        claims = verify_federation_assertion(
            public_key_b64=public_key,
            token=args.token,
            expected_audience=brain_id,
            expected_issuer=issuer_brain_id,
        )
    except ValueError as e:
        print(f"VERIFY_FAIL: {e}", file=sys.stderr)
        sys.exit(1)

    print("VERIFY_OK")
    print(json.dumps(claims, indent=2))


if __name__ == "__main__":
    main()
