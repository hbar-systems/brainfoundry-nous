"""
api/ask.py — the ask door: one brain (or its agents) asks another a question.

Shaped on the A2A protocol (Agent Card at /.well-known/agent-card.json,
JSON-RPC 2.0 method "message/send") so agents on the web can find and call a
brain, while trust stays this brain's own: every ask carries an ED25519
federation assertion (api/identity/core.py) in the X-Brain-Assertion header,
bound to the question by a sha256 hash claim. See docs/ASK.md.

Read-only by construction: the answer is drawn only from chunks whose
metadata.scope is "public", never local-only, with no tools, no writes and no
memory changes. This module holds the pure parts (card, request parsing,
caller verification, prompt, reply shape); api/main.py wires the routes, the
rate limiter, retrieval and the model call.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

ASK_PATH = "/v1/ask"
ASSERTION_HEADER = "X-Brain-Assertion"
SCHEME = "brainfoundry-ed25519"
SUBJECT = "ask"
A2A_PROTOCOL_VERSION = "0.3.0"
MAX_QUESTION_CHARS = 4000
# A token is minted for one question; it must not live longer than this.
MAX_TOKEN_TTL = 600

# JSON-RPC 2.0 standard codes, plus server-defined codes for this door.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
UNAUTHENTICATED = -32010
FORBIDDEN = -32011
RATE_LIMITED = -32029


class AskError(Exception):
    """A refusal: HTTP status, JSON-RPC code and a short reason."""

    def __init__(self, status: int, code: int, reason: str):
        super().__init__(reason)
        self.status = status
        self.code = code
        self.reason = reason


def question_hash(question: str) -> str:
    """The `qh` claim: sha256 hex of the question text as UTF-8."""
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


# ── Agent Card ────────────────────────────────────────────────────────────────

def persona_description(persona: str) -> str:
    """First real line of the persona: markdown markers stripped; the template's
    banner and unfilled [PLACEHOLDER] lines skipped."""
    for line in (persona or "").splitlines():
        s = line.strip().lstrip("#").strip()
        if not s or s.upper().startswith("TEMPLATE") or "[" in s:
            continue
        return s[:300]
    return "A brainfoundry brain."


def agent_card(*, base_url: str, brain_id: str, name: str, persona: str,
               version: str) -> Dict[str, Any]:
    base = base_url.rstrip("/")
    return {
        "protocolVersion": A2A_PROTOCOL_VERSION,
        "name": name or brain_id or "brain",
        "description": persona_description(persona),
        "url": base + ASK_PATH,
        "preferredTransport": "JSONRPC",
        "version": version,
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "extensions": [{
                "uri": "urn:brainfoundry:ask-assertion:v1",
                "description": "Each request carries an ED25519 federation assertion "
                               "(iss, aud, sub='ask', iat, exp, jti, qh=sha256 of the question).",
                "required": True,
                "params": {"brain_id": brain_id, "identity_url": base + "/identity",
                           "header": ASSERTION_HEADER},
            }],
        },
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": [{
            "id": "ask",
            "name": "ask",
            "description": "Answer a question from this brain's public-scoped memory, "
                           "citing the documents used.",
            "tags": ["question-answering", "memory", "public"],
            "inputModes": ["text/plain"],
            "outputModes": ["text/plain", "application/json"],
        }],
        "securitySchemes": {
            SCHEME: {
                "type": "apiKey",
                "in": "header",
                "name": ASSERTION_HEADER,
                "description": "ED25519-signed federation assertion, one per question. "
                               f"Verify keys at {base}/identity (public_key).",
            },
        },
        "security": [{SCHEME: []}],
    }


# ── Request parsing ───────────────────────────────────────────────────────────

def parse_request(body: Any) -> Dict[str, Any]:
    """Validate the JSON-RPC envelope; return {id, question, public_key}."""
    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
        raise AskError(400, INVALID_REQUEST, "not a JSON-RPC 2.0 request")
    if body.get("method") != "message/send":
        raise AskError(400, METHOD_NOT_FOUND, "only message/send is supported")
    params = body.get("params")
    message = params.get("message") if isinstance(params, dict) else None
    parts = message.get("parts") if isinstance(message, dict) else None
    if not isinstance(parts, list):
        raise AskError(400, INVALID_PARAMS, "params.message.parts is required")
    texts = [p.get("text") for p in parts
             if isinstance(p, dict) and p.get("kind") == "text" and isinstance(p.get("text"), str)]
    if len(texts) != 1 or not texts[0].strip():
        raise AskError(400, INVALID_PARAMS, "exactly one non-empty text part is required")
    question = texts[0]
    if len(question) > MAX_QUESTION_CHARS:
        raise AskError(400, INVALID_PARAMS, f"question too long (max {MAX_QUESTION_CHARS} chars)")
    meta = params.get("metadata") if isinstance(params.get("metadata"), dict) else {}
    bf = meta.get("brainfoundry") if isinstance(meta.get("brainfoundry"), dict) else {}
    pk = bf.get("public_key")
    return {
        "id": body.get("id"),
        "question": question,
        "public_key": pk if isinstance(pk, str) and pk else None,
        "context_id": message.get("contextId"),
    }


# ── Caller verification ───────────────────────────────────────────────────────

@dataclass
class Caller:
    brain_id: str
    trust: str          # "peer" (pinned key) | "public" (public asking, self-certified key)
    rate_key: str
    endpoint: Optional[str] = None
    public_key: Optional[str] = None


def _unverified_iss(token: str) -> Optional[str]:
    try:
        claims_b64 = token.split(".")[1]
        claims_b64 += "=" * (-len(claims_b64) % 4)
        iss = json.loads(base64.urlsafe_b64decode(claims_b64).decode()).get("iss")
        return iss if isinstance(iss, str) and iss else None
    except Exception:
        return None


def find_pinned_peer(brain_id: str) -> Optional[Dict[str, Any]]:
    """A peer with a pinned key: introduced peers (data/peers.json) first, then
    the operator's known_peers.toml. Never a key the caller supplied."""
    if not brain_id:
        return None
    try:
        from api.hbar_commands import find_peer_by_brain_id
        p = find_peer_by_brain_id(brain_id)
        if p:
            return p
    except Exception:
        pass
    from api.identity.peers import load_peers
    return next((p for p in load_peers() if p["brain_id"] == brain_id), None)


def verify_caller(*, token: Optional[str], question: str, this_brain_id: str,
                  public_key: Optional[str], public_asking: bool,
                  now: Optional[int] = None) -> Caller:
    """Check the assertion and decide who is asking.

    A known peer is verified against its PINNED key only (a caller-supplied key
    never overrides a pin). An unknown issuer is refused unless the owner has
    turned public asking on; then the request must carry its own public key,
    which proves key possession (not who the caller is) and keys the rate limit.
    Replay of a jti within its lifetime is refused.
    """
    from api.identity.core import verify_federation_assertion
    from api.identity.replay_cache import record, seen_before

    if not token:
        raise AskError(401, UNAUTHENTICATED, f"missing {ASSERTION_HEADER}")
    iss = _unverified_iss(token)
    if not iss:
        raise AskError(401, UNAUTHENTICATED, "invalid_token_format")

    peer = find_pinned_peer(iss)
    if peer:
        key, trust = peer["public_key"], "peer"
    elif public_asking and public_key:
        key, trust = public_key, "public"
    elif public_asking:
        raise AskError(401, UNAUTHENTICATED,
                       "unknown peer: send params.metadata.brainfoundry.public_key")
    else:
        raise AskError(403, FORBIDDEN, "unknown_peer")

    try:
        claims = verify_federation_assertion(
            public_key_b64=key, token=token,
            expected_audience=this_brain_id, expected_issuer=iss)
    except Exception as e:
        reason = str(e) if isinstance(e, ValueError) else "invalid_key"
        raise AskError(401, UNAUTHENTICATED, f"assertion_verify_failed: {reason}")

    now = int(time.time()) if now is None else now
    exp, iat = claims.get("exp"), claims.get("iat")
    if not isinstance(exp, int) or not isinstance(iat, int):
        raise AskError(401, UNAUTHENTICATED, "missing iat/exp")
    if exp - now > MAX_TOKEN_TTL:
        raise AskError(401, UNAUTHENTICATED, f"token lives longer than {MAX_TOKEN_TTL}s")
    if claims.get("sub") != SUBJECT:
        raise AskError(401, UNAUTHENTICATED, "sub must be 'ask'")
    if claims.get("qh") != question_hash(question):
        raise AskError(401, UNAUTHENTICATED, "question hash mismatch")
    jti = claims.get("jti")
    if not jti:
        raise AskError(401, UNAUTHENTICATED, "missing_jti")
    if seen_before(jti):
        raise AskError(401, UNAUTHENTICATED, "replay_detected")
    record(jti, exp=exp)

    if trust == "peer":
        return Caller(brain_id=iss, trust="peer", rate_key=f"ask:peer:{iss}",
                      endpoint=peer.get("endpoint"), public_key=key)
    return Caller(brain_id=iss, trust="public", rate_key=f"ask:key:{key}", public_key=key)


# ── Answer ────────────────────────────────────────────────────────────────────

def public_only(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Belt to retrieval's braces: keep only chunks whose scope is exactly public."""
    return [d for d in docs or [] if (d.get("metadata") or {}).get("scope") == "public"]


def citations(docs: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for d in docs:
        name = d.get("document_name")
        if name and name not in out:
            out.append(name)
    return out


NO_ANSWER = "This brain has no public memory on that question."


def build_prompt(question: str, docs: List[Dict[str, Any]]) -> str:
    from api.security import untrusted as _untrusted
    body = "Public documents:\n"
    for d in docs:
        body += f"\n[{d.get('document_name', 'document')}]\n{d.get('content', '')}\n"
    return (
        _untrusted.with_policy_preamble(
            "You answer a question from another brain using ONLY the public documents "
            "below. Cite each document you draw on by its name in square brackets. "
            "If the documents do not answer the question, say so; do not use outside "
            "knowledge and never invent facts about the owner of this brain.")
        + "\n\n" + _untrusted.untrusted_context_block("public memory (retrieved documents)", body)
        + "\n\nQuestion: " + question + "\nAnswer:"
    )


def reply(rpc_id: Any, answer: str, cites: List[str], *, brain_id: str,
          context_id: Optional[str] = None) -> Dict[str, Any]:
    """A2A Message result: a text part with the answer, a data part with citations."""
    msg: Dict[str, Any] = {
        "kind": "message",
        "role": "agent",
        "messageId": str(uuid.uuid4()),
        "parts": [
            {"kind": "text", "text": answer},
            {"kind": "data", "data": {"citations": cites}},
        ],
        "metadata": {"brainfoundry": {"brain_id": brain_id, "citations": cites,
                                      "scope": "public"}},
    }
    if context_id:
        msg["contextId"] = context_id
    return {"jsonrpc": "2.0", "id": rpc_id, "result": msg}


def error(rpc_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}
