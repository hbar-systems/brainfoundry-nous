#!/usr/bin/env python3
"""
Hand the owner a link that makes a radio station play in the order of this brain's taste.

Calls this brain's owner-gated POST /v1/radio/subscribe-token and prints the URL.
The brain builds a short taste note from its own memory, signs it, and the station
(orfeo.music by default) verifies the signature; nothing else leaves the brain.

Usage (on the brain, or in the console terminal):
    python scripts/orfeo_subscribe.py
    python scripts/orfeo_subscribe.py --station https://orfeo.music --api http://localhost:8000

Environment: BRAIN_API_KEY (the owner's X-API-Key; read from the environment only).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--station", default="https://orfeo.music")
    ap.add_argument("--api", default=os.getenv("BRAIN_API_URL", "http://localhost:8000"))
    ap.add_argument("--show-taste", action="store_true", help="also print the taste note sent")
    args = ap.parse_args(argv)

    key = os.getenv("BRAIN_API_KEY") or os.getenv("API_KEY")
    if not key:
        print("ERROR: set BRAIN_API_KEY in the environment", file=sys.stderr)
        return 2
    req = urllib.request.Request(
        args.api.rstrip("/") + "/v1/radio/subscribe-token",
        data=json.dumps({"station": args.station}).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode()).get("detail")
        except Exception:
            detail = None
        print(f"ERROR: HTTP {e.code}: {detail or e.reason}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if args.show_taste:
        print("taste:", body.get("taste"), file=sys.stderr)
    print(body["url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
