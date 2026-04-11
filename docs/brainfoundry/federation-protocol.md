# Federation Protocol
*BrainFoundryOS — cross-brain identity and authorization*
*Version: 0.1 — ED25519 signing layer*

---

## What federation is

Federation is two sovereign brain nodes voluntarily interacting — sharing context, issuing requests, or taking actions on each other's behalf — without either brain surrendering control to a central authority.

"Two brains can talk" is not federation. Federation is the set of rules that makes any interaction between any two nodes trustworthy and verifiable. It answers three questions:

1. **Identity** — is this token actually from the brain it claims to be from?
2. **Authorization** — did the owner of that brain actually authorize this specific action?
3. **Scope** — what is this token allowed to do, and for how long?

---

## Why HMAC-SHA256 is not enough

The intra-brain permit system (loop permits, operator assertions) uses HMAC-SHA256 with a shared secret (`HBAR_IDENTITY_SECRET`). This works when the same brain issues and verifies its own tokens — both sides know the secret.

For federation, Brain B needs to verify a token issued by Brain A. With symmetric signing, that would require Brain B to know Brain A's secret. Sharing secrets between sovereign nodes breaks the sovereignty model entirely — you are trusting the other node's operational security as much as your own.

**ED25519 solves this.** Brain A holds a private key that never leaves its server. Brain A signs tokens with the private key. Brain B fetches Brain A's public key from `GET /identity` and verifies the signature. No secrets are shared. Brain B never needs to trust Brain A's infrastructure — only the mathematics of the signature.

---

## Setup — one time per brain

### 1. Generate keypair

From the brain repo root:

```bash
python scripts/generate_keypair.py
```

Output:
```
# Add these to your .env file
BRAIN_PRIVATE_KEY=<base64url-encoded private key>
BRAIN_PUBLIC_KEY=<base64url-encoded public key>
```

### 2. Add to `.env`

```env
BRAIN_PRIVATE_KEY=<value>   # never share, never commit
BRAIN_PUBLIC_KEY=<value>    # public — safe to expose
```

### 3. Rebuild the API container

```bash
docker compose up -d --build api
```

### 4. Verify the public key is published

```bash
curl https://brain.yourdomain.com/identity | grep public_key
```

The `/identity` endpoint returns `brain_identity.yaml` as JSON. The `public_key` field is now present and publicly readable. Any other brain can fetch it.

---

## Token format

All federation tokens use the same three-part structure as intra-brain permits:

```
base64url(header).base64url(claims).base64url(signature)
```

**Header:**
```json
{
  "alg": "EdDSA",
  "typ": "HBAR_FED_ASSERTION",
  "v": 1
}
```

**Claims:**
```json
{
  "iss": "<issuing brain_id>",
  "aud": "<receiving brain_id>",
  "sub": "<subject — what this assertion is about>",
  "iat": <unix timestamp>,
  "exp": <unix timestamp>,
  "v": 1
}
```

Additional claims can be included for context (action type, permit scope, etc.).

**Signature:** ED25519 signature over `base64url(header).base64url(claims)` using the issuing brain's private key.

---

## Issuing a federation assertion (Brain A)

```python
from api.identity.core import issue_federation_assertion
import os

token = issue_federation_assertion(
    private_key_b64=os.getenv("BRAIN_PRIVATE_KEY"),
    issuer_brain_id="brain-alpha",
    audience_brain_id="brain-beta",
    subject="context_share",          # what you're asserting
    ttl_seconds=300,                  # 5 minutes
    claims={"action": "read_memory"}, # optional extra claims
)
```

Send this token to Brain B in the request (e.g. as `X-Fed-Assertion` header or in the request body).

---

## Verifying a federation assertion (Brain B)

```python
import httpx
from api.identity.core import verify_federation_assertion

# 1. Fetch the issuing brain's public key
identity = httpx.get("https://brain.alpha.example.com/identity").json()
public_key_b64 = identity["public_key"]

# 2. Verify
try:
    claims = verify_federation_assertion(
        public_key_b64=public_key_b64,
        token=token,
        expected_audience="brain-beta",  # this brain's brain_id
    )
    # claims is the decoded payload — iss, aud, sub, exp, etc.
except ValueError as e:
    # invalid_token_format | invalid_signature | aud_mismatch | expired
    reject_request(reason=str(e))
```

**What verify checks:**
- Signature is valid (cryptographic proof the token came from the holder of Brain A's private key)
- Token is addressed to this brain (`aud` matches `expected_audience`)
- Token has not expired (`exp > now`)

---

## Error codes

| Error | Meaning |
|-------|---------|
| `invalid_token_format` | Token is not three dot-separated parts |
| `invalid_signature` | Signature does not verify against the public key |
| `aud_mismatch` | Token was not addressed to this brain |
| `expired` | Token has passed its `exp` timestamp |

---

## Security properties

**What this guarantees:**
- A token that verifies was signed by the holder of the corresponding private key
- A private key that never leaves its server cannot be forged by a third party
- A token addressed to Brain B cannot be replayed against Brain C (`aud` check)
- A token expires after `ttl_seconds` — captured tokens cannot be replayed indefinitely

**What this does not guarantee (yet):**
- That Brain A's owner *intended* this specific token at this moment — that is the PROPOSE→CONFIRM layer, which is the next build step for cross-brain actions
- Revocation — there is no token revocation mechanism in v0.1; expiry is the only cancellation
- That the `/identity` endpoint itself hasn't been tampered with — in production this should be fetched over TLS with certificate pinning or cached after first verified contact

---

## Relation to other protocol layers

```
┌─────────────────────────────────────────────┐
│  PROPOSE → CONFIRM (kernel governance)       │  ← owner authorization
│  Loop permits (NodeOS)                       │  ← action scope
│  Federation assertions — ED25519  ← HERE     │  ← node identity + authenticity
│  Caddy TLS + basic auth                      │  ← transport security
└─────────────────────────────────────────────┘
```

Federation assertions answer "is this really Brain A talking?" — before the receiving brain decides whether to act on what Brain A is asking.

---

## First handshake — brain-alpha ↔ brain-beta

**Prerequisites:**
- [ ] Keypairs generated and deployed on both brains
- [ ] Both brains rebuilt with `cryptography>=42.0.0`
- [ ] Both `/identity` endpoints return `public_key` field

**Test sequence:**
1. Brain A issues a `HBAR_FED_ASSERTION` with `sub: "handshake_ping"`
2. Brain B fetches Brain A's `/identity`, verifies the token
3. Brain B issues a response assertion back to Brain A
4. Brain A verifies Brain B's response
5. Both sides log success

This is the territory claim. Test privately, announce publicly the same day it works.

---

## Implementation

| File | Role |
|------|------|
| `api/identity/core.py` | `generate_brain_keypair()`, `issue_federation_assertion()`, `verify_federation_assertion()` |
| `api/brain_identity.yaml` | `public_key: "${BRAIN_PUBLIC_KEY}"` — published via `GET /identity` |
| `api/requirements.txt` | `cryptography>=42.0.0` |
| `scripts/generate_keypair.py` | One-time keypair generation |
| `.env.example` | `BRAIN_PRIVATE_KEY`, `BRAIN_PUBLIC_KEY` documented |

Intra-brain permits (loop permits, operator assertions) continue to use HMAC-SHA256 via `issue_permit()` / `verify_permit()` — the symmetric system is unchanged and appropriate for single-brain use.
