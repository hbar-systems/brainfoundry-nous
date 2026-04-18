"""
Part A federation handshake — VERIFY side.

Inside a brain container, look the issuer endpoint up in the local known_peers
registry to retrieve the pinned brain_id + public_key, then verify the token
was signed by that key and addressed to this brain. Registry lookup replaces
the earlier /identity fetch — see T1 in the federation threat model.

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

from api.identity.core import verify_federation_assertion
from api.identity.peers import find_peer_by_endpoint


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--issuer-endpoint", required=True, help="e.g. https://yury.brainfoundry.ai")
    args = ap.parse_args()

    brain_id = os.getenv("BRAIN_ID")
    if not brain_id:
        print("ERROR: BRAIN_ID must be set in env", file=sys.stderr)
        sys.exit(2)

    peer = find_peer_by_endpoint(args.issuer_endpoint)
    if peer is None:
        print(f"VERIFY_FAIL: unknown_peer — {args.issuer_endpoint} not in known_peers.toml", file=sys.stderr)
        sys.exit(1)

    try:
        claims = verify_federation_assertion(
            public_key_b64=peer["public_key"],
            token=args.token,
            expected_audience=brain_id,
            expected_issuer=peer["brain_id"],
        )
    except ValueError as e:
        print(f"VERIFY_FAIL: {e}", file=sys.stderr)
        sys.exit(1)

    print("VERIFY_OK")
    print(json.dumps(claims, indent=2))


if __name__ == "__main__":
    main()
