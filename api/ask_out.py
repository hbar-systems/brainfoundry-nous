"""
Asking out (2026-10-20): this brain asks another brain one question through that brain's ask door
(docs/ASK.md). The owner, or the console bridge on the owner's behalf, calls POST /v1/ask-peer; the
brain signs with its own key, so no agent or reasoner ever holds BRAIN_PRIVATE_KEY.

The peer's address comes from whoever calls, so it is checked like any fetch: https only, every
address the host resolves to must be public (api/tools/fetch_url.py's check), the url the peer's
card names gets the same check, and redirects are not followed (a redirect could lead past the
check). Timeouts and size caps bound what a peer can make this brain wait for or hold.

Standard library only, apart from the brain's own signing.
"""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable, Dict, Optional, Tuple

from api.identity.core import issue_federation_assertion

ASSERTION_HEADER = "X-Brain-Assertion"
TTL_SECONDS = 120
CARD_PATH = "/.well-known/agent-card.json"
CARD_TIMEOUT = 10
ASK_TIMEOUT = 150
CARD_MAX_BYTES = 64 * 1024
REPLY_MAX_BYTES = 1024 * 1024
MAX_QUESTION_CHARS = 4000


class PeerError(Exception):
    """A refusal or failure on the way out. `status` is what the owner route answers with."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _public_host(host: str) -> bool:
    from api.tools.fetch_url import _is_public_address
    return _is_public_address(host)


def check_url(url: str, is_public: Optional[Callable[[str], bool]] = None) -> str:
    """The url, if this brain may call it: https, a host, every address public. Else PeerError(400)."""
    u = urllib.parse.urlparse((url or "").strip())
    if u.scheme != "https":
        raise PeerError(400, "the peer must be an https address")
    if not u.hostname:
        raise PeerError(400, "the peer address has no host")
    if not (is_public or _public_host)(u.hostname):
        raise PeerError(400, f"{u.hostname} does not resolve to public addresses only")
    return urllib.parse.urlunparse(u)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        raise PeerError(502, f"the peer answered with a redirect ({code}); redirects are not followed")


_OPENER = urllib.request.build_opener(_NoRedirect)


def _read(resp, cap: int) -> bytes:
    data = resp.read(cap + 1)
    if len(data) > cap:
        raise PeerError(502, f"the peer's answer is larger than {cap // 1024} KB")
    return data


def http_json(url: str, *, data: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None,
              timeout: float, cap: int, opener=None) -> Tuple[int, Dict[str, Any]]:
    """(status, parsed JSON) for one request, no redirects, at most `cap` bytes."""
    req = urllib.request.Request(url, data=data, headers={"Accept": "application/json", **(headers or {})},
                                 method="POST" if data is not None else "GET")
    try:
        with (opener or _OPENER).open(req, timeout=timeout) as r:
            status, raw = r.status, _read(r, cap)
    except PeerError:
        raise
    except urllib.error.HTTPError as e:
        status, raw = e.code, _read(e, cap)
    except TimeoutError:
        raise PeerError(504, "the peer did not answer in time")
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise PeerError(504, "the peer did not answer in time")
        raise PeerError(502, f"could not reach the peer: {e.reason}")
    except OSError as e:
        raise PeerError(502, f"could not reach the peer: {e}")
    try:
        return status, json.loads(raw.decode("utf-8"))
    except Exception:
        raise PeerError(502, f"the peer's answer is not JSON (HTTP {status})")


def audience_from_card(card: Dict[str, Any]) -> Optional[str]:
    for ext in (card.get("capabilities") or {}).get("extensions") or []:
        bid = (ext.get("params") or {}).get("brain_id")
        if bid:
            return bid
    return None


def build_request(*, question: str, audience: str, private_key: str, my_id: str,
                  public_key: Optional[str] = None) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Headers and JSON-RPC body for one ask. The token is bound to this question."""
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


def ask_peer(peer: str, question: str, *, my_id: str, private_key: str, public_key: Optional[str] = None,
             is_public: Optional[Callable[[str], bool]] = None, opener=None) -> Dict[str, Any]:
    """Ask `peer` (its base url) one question. Returns {peer, brain_id, answer, citations}; PeerError otherwise."""
    question = (question or "").strip()
    if not question:
        raise PeerError(400, "the question is empty")
    if len(question) > MAX_QUESTION_CHARS:
        raise PeerError(400, f"the question is longer than {MAX_QUESTION_CHARS} characters")
    if not my_id or not private_key:
        raise PeerError(503, "this brain has no federation identity (BRAIN_ID, BRAIN_PRIVATE_KEY)")
    base = check_url(peer, is_public).rstrip("/")
    status, card = http_json(base + CARD_PATH, timeout=CARD_TIMEOUT, cap=CARD_MAX_BYTES, opener=opener)
    if status != 200 or not isinstance(card, dict):
        raise PeerError(502, f"the peer has no agent card (HTTP {status})")
    audience = audience_from_card(card)
    if not audience:
        raise PeerError(502, "the peer's agent card names no brain_id")
    url = check_url(card.get("url") or base + "/v1/ask", is_public)
    headers, body = build_request(question=question, audience=audience, private_key=private_key,
                                  my_id=my_id, public_key=public_key)
    status, resp = http_json(url, data=json.dumps(body).encode("utf-8"), headers=headers,
                             timeout=ASK_TIMEOUT, cap=REPLY_MAX_BYTES, opener=opener)
    if not isinstance(resp, dict):
        raise PeerError(502, "the peer's answer is not a JSON-RPC object")
    if "error" in resp:
        err = resp.get("error") or {}
        raise PeerError(502, f"the peer refused: {str(err.get('message') or err)[:300]}")
    if "result" not in resp:
        raise PeerError(502, f"the peer's answer has no result (HTTP {status})")
    answer, cites = answer_of(resp)
    return {"peer": base, "brain_id": audience, "answer": answer,
            "citations": [str(c)[:300] for c in cites][:50]}
