"""
Part A federation handshake — SIGN side.

Inside a brain container, sign a cross-brain assertion addressed to --audience.
Prints the token to stdout (nothing else — safe to pipe).

Usage:
    docker compose exec brain-api python3 scripts/fed_sign.py --audience nous-brain-01
"""
import argparse
import os
import sys

sys.path.insert(0, "/app")

from api.identity.core import issue_federation_assertion


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audience", required=True, help="recipient brain_id")
    ap.add_argument("--subject", default="federation_handshake_test")
    ap.add_argument("--ttl", type=int, default=300)
    args = ap.parse_args()

    private_key = os.getenv("BRAIN_PRIVATE_KEY")
    brain_id = os.getenv("BRAIN_ID")
    if not private_key or not brain_id:
        print("ERROR: BRAIN_PRIVATE_KEY and BRAIN_ID must be set in env", file=sys.stderr)
        sys.exit(2)

    token = issue_federation_assertion(
        private_key_b64=private_key,
        issuer_brain_id=brain_id,
        audience_brain_id=args.audience,
        subject=args.subject,
        ttl_seconds=args.ttl,
    )
    print(token)


if __name__ == "__main__":
    main()
