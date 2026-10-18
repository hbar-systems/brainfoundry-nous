#!/usr/bin/env python3
"""
Ask another brain a question through its ask door (docs/ASK.md).

Fetches the brain's A2A Agent Card, signs a one-question federation assertion
with THIS brain's key (the same issue_federation_assertion outgoing federation
calls use), POSTs JSON-RPC message/send to the card's url, prints the answer
and the cited documents.

Usage:
    BRAIN_ID=<my id> BRAIN_PRIVATE_KEY=<my key> \\
        python3 scripts/ask_brain.py https://other-brain.example "What is X?"

    Inside a brain container the env is already set:
        docker compose exec brain-api python3 scripts/ask_brain.py <base-url> "<question>"

Flags: --json prints the raw JSON-RPC response; --public-key also sends this
brain's public key (BRAIN_PUBLIC_KEY), needed only when the other brain has
not pinned us and has public asking on. Exit 0 on an answer, 1 on a refusal,
2 on a usage or network error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.identity.core import issue_federation_assertion  # noqa: E402

ASSERTION_HEADER = "X-Brain-Assertion"
TTL_SECONDS = 120


def _get_json(url: str, timeout: float = 15) -> Dict[str, Any]:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}),
                                timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def audience_from_card(card: Dict[str, Any]) -> Optional[str]:
    for ext in (card.get("capabilities") or {}).get("extensions") or []:
        bid = (ext.get("params") or {}).get("brain_id")
        if bid:
            return bid
    return None


def build_request(*, question: str, audience: str, private_key: str, my_id: str,
                  public_key: Optional[str] = None) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Headers and JSON-RPC body for one ask. The token is bound to this question."""
    import hashlib
    token = issue_federation_assertion(
        private_key_b64=private_key,
        issuer_brain_id=my_id,
        audience_brain_id=audience,
        subject="ask",
        ttl_seconds=TTL_SECONDS,
        claims={"qh": hashlib.sha256(question.encode("utf-8")).hexdigest()},
    )
    params: Dict[str, Any] = {"message": {
        "role": "user", "messageId": str(uuid.uuid4()),
        "parts": [{"kind": "text", "text": question}],
    }}
    if public_key:
        params["metadata"] = {"brainfoundry": {"public_key": public_key}}
    body = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "message/send", "params": params}
    headers = {"Content-Type": "application/json", ASSERTION_HEADER: token}
    return headers, body


def answer_of(resp: Dict[str, Any]) -> Tuple[str, list]:
    msg = resp.get("result") or {}
    text = "\n".join(p.get("text", "") for p in msg.get("parts", []) if p.get("kind") == "text")
    cites: list = []
    for p in msg.get("parts", []):
        if p.get("kind") == "data":
            cites = (p.get("data") or {}).get("citations") or cites
    return text, cites


def main() -> int:
    ap = argparse.ArgumentParser(description="Ask another brain a question.")
    ap.add_argument("base_url")
    ap.add_argument("question")
    ap.add_argument("--json", action="store_true", help="print the raw JSON-RPC response")
    ap.add_argument("--public-key", action="store_true",
                    help="send BRAIN_PUBLIC_KEY (for brains that have not pinned us)")
    args = ap.parse_args()

    my_id, private_key = os.getenv("BRAIN_ID"), os.getenv("BRAIN_PRIVATE_KEY")
    if not my_id or not private_key:
        print("ERROR: BRAIN_ID and BRAIN_PRIVATE_KEY must be set in env", file=sys.stderr)
        return 2
    public_key = os.getenv("BRAIN_PUBLIC_KEY") if args.public_key else None
    if args.public_key and not public_key:
        print("ERROR: --public-key needs BRAIN_PUBLIC_KEY in env", file=sys.stderr)
        return 2

    base = args.base_url.rstrip("/")
    try:
        card = _get_json(base + "/.well-known/agent-card.json")
        audience = audience_from_card(card) or _get_json(base + "/identity").get("brain_id")
    except Exception as e:
        print(f"ERROR: could not read the agent card at {base}: {e}", file=sys.stderr)
        return 2
    if not audience:
        print("ERROR: the card names no brain_id", file=sys.stderr)
        return 2

    headers, body = build_request(question=args.question, audience=audience,
                                  private_key=private_key, my_id=my_id, public_key=public_key)
    req = urllib.request.Request(card.get("url") or base + "/v1/ask",
                                 data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            resp = json.loads(e.read().decode("utf-8"))
        except Exception:
            print(f"ERROR: HTTP {e.code}", file=sys.stderr)
            return 2
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(resp, indent=2, ensure_ascii=False))
    if "error" in resp:
        if not args.json:
            print(f"refused: {resp['error'].get('message')}", file=sys.stderr)
        return 1
    if not args.json:
        text, cites = answer_of(resp)
        print(text)
        if cites:
            print("\nCited:")
            for c in cites:
                print(f"  - {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
