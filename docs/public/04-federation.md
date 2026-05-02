# Federation

Federation is two sovereign brain nodes voluntarily interacting — sharing context, issuing signed requests, or taking actions on each other's behalf — without either brain surrendering control to a central authority.

## The claim federation actually makes

"Two brains can talk" is not federation. Federation is the set of rules that makes any interaction between any two nodes verifiable. It answers three questions:

1. **Identity.** Is this token actually from the brain it claims to be from?
2. **Authorization.** Did the owner of that brain actually authorize this specific action?
3. **Scope.** What is this token allowed to do, and for how long?

Federation answers (1) and (3) directly via signatures and expiries. Question (2) is answered by the kernel governance layer described in the previous document — the brain issuing an assertion only does so when its own PROPOSE → CONFIRM has been satisfied.

## Why asymmetric signing

An intra-brain permit system can use symmetric signing: the same brain issues and verifies tokens, so a shared secret is fine.

Federation cannot. For brain B to verify a token issued by brain A, B would need A's secret. Sharing a secret between sovereign nodes breaks the sovereignty model — each brain's security becomes the other brain's problem.

ED25519 solves this cleanly. Each brain holds a private key that never leaves its server. Each brain publishes its public key at a well-known HTTP endpoint. Verification is public-key cryptography — no secret sharing, no back channels.

## Identity endpoint

Every brain exposes:

```
GET /identity
```

The response is unauthenticated and contains the node's public identity:

- `brain_id` — unique identifier
- `brain_name` — display name
- `public_key` — base64url-encoded ED25519 public key
- `capabilities` — supported protocol versions
- `owner` — the named operator

No authentication is required because none of this is secret. The public key is meant to be read by anyone who wants to verify a signature from this brain.

## Assertion format

All federation tokens use a three-part structure:

```
base64url(header) . base64url(claims) . base64url(signature)
```

The header declares the algorithm (`EdDSA`) and the token type. The claims include the issuing brain ID (`iss`), the audience brain ID (`aud`), the subject of the assertion (`sub`), issued-at (`iat`), expires-at (`exp`), and any additional assertion-specific context.

The signature is an ED25519 signature over the header and claims using the issuing brain's private key.

## Issuing an assertion

Brain A wants to assert something to brain B. Operator tooling signs the claims with brain A's private key:

```
python scripts/fed_sign.py --audience <brain-b-id> --subject <what>
```

The script reads `BRAIN_PRIVATE_KEY` and `BRAIN_ID` from the environment, produces a signed token, and prints it to stdout.

A production federation call sends this token to brain B over HTTPS in a request body or header.

## Verifying an assertion

Brain B receives a token. It calls its own kernel:

```
POST /v1/federation/assertion
body: { "token": "<the token>", "issuer_endpoint": "https://brain-a.example.com" }
```

The kernel on brain B:

1. Fetches `GET /identity` on the issuer endpoint.
2. Reads `public_key` from the response.
3. Verifies the signature against that public key.
4. Checks the audience matches brain B's own `BRAIN_ID`.
5. Checks the token has not expired.
6. Returns the decoded claims, or a structured error.

Operator tooling mirrors this:

```
python scripts/fed_verify.py --token <token> --issuer-endpoint https://brain-a.example.com
```

## Error codes

Verification can fail in four named ways:

| Error | Meaning |
|---|---|
| `invalid_token_format` | Token is not three dot-separated parts |
| `invalid_signature` | Signature does not verify against the public key |
| `aud_mismatch` | Token was not addressed to this brain |
| `expired` | Token has passed its `exp` timestamp |

Each failure is a hard reject. There is no partial acceptance, no fuzzy matching.

## Security properties

**What federation guarantees:**

- A token that verifies was signed by the holder of the corresponding private key.
- A private key that never leaves its server cannot be forged by a third party.
- A token addressed to brain B cannot be replayed against brain C — the audience check fails.
- A token cannot be replayed indefinitely — it expires on the issuer's declared TTL.

**What federation does not guarantee:**

- That the issuer's owner *intended* this specific token at this moment. That is the job of the kernel governance layer inside the issuing brain. The federation layer guarantees authenticity of the token; the kernel layer guarantees authenticity of the intent behind it.
- Revocation before expiry. Expiry is the only cancellation mechanism at the protocol level. Operators who want tighter revocation run short TTLs.

## The email analogy

Federation is to brains what SMTP is to humans. Anyone can send. Anyone can receive. There is no central authority deciding who is allowed to address whom. The protocol is open and publicly documented.

The difference: email is deliberately lax about authenticity, and spam is the cost. Federation assertions are strictly signed — an assertion that does not verify is dropped, not queued.

What rides on top of federation — memory sharing, collaborative workflows, cross-brain agents — is domain-specific workflow built on the assertion primitive. The primitive itself is small, like an SMTP envelope: identity, audience, subject, expiry, signature. Everything else is payload.

## Where federation sits

Federation is one of four layers in a brain's security stack, stacked from owner intent down to transport:

```
PROPOSE → CONFIRM (kernel governance)     ← owner authorization
Loop permits (BrainKernel)                ← action scope
Federation assertions (ED25519)           ← node identity and authenticity
TLS + reverse proxy                       ← transport security
```

A federated action must clear all four layers. A misissued assertion fails at (3). An unauthorized one fails at (1).

## Trying it

A brain that has been through the install flow already has an identity endpoint and a keypair. To verify federation end-to-end against another brain:

```
# On brain A — issue a test assertion
python scripts/fed_sign.py \
  --audience <brain-b-id> \
  --subject handshake_ping > token.txt

# On brain B — verify it
curl -X POST https://brain-b.example.com/v1/federation/assertion \
  -H "Content-Type: application/json" \
  -d "{\"token\": \"$(cat token.txt)\", \"issuer_endpoint\": \"https://brain-a.example.com\"}"
```

A successful response returns the decoded claims. A failure returns a structured error with one of the four codes above.

## Status

The bidirectional HTTPS federation handshake is working. Two independent brain instances on separate servers can exchange ED25519-signed assertions, each fetching the peer's public key live from `/identity` and verifying signature, audience, issuer, and expiry server-side.

Richer context-mesh workflows — cross-brain memory sharing, federated queries, collaborative agents — build on this primitive but are the next build layer, not part of the current reference implementation. The primitive is stable; the workflows are what sits on top of it.
