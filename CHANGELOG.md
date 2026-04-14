# Changelog

## 2026-04-14 — federation live

**First bidirectional cross-brain HTTPS federation handshake proven in
production.** Two independent brain instances (yury-brain-01 and
nous-brain-01) on separate Hetzner servers exchanged ED25519-signed
assertions in both directions over public HTTPS, with each brain
fetching the peer's public key live from its `/identity` endpoint and
verifying signature, audience, issuer, and expiry server-side.

New:

- `POST /v1/federation/assertion` in `api/main.py` — receives
  `{token, issuer_endpoint}`, fetches issuer `/identity` for the
  public key, verifies the assertion, returns decoded claims.
- `scripts/fed_sign.py` — CLI wrapper around
  `issue_federation_assertion`. Reads `BRAIN_PRIVATE_KEY` + `BRAIN_ID`
  from env, takes `--audience`, prints signed token to stdout.
- `scripts/fed_verify.py` — CLI wrapper around
  `verify_federation_assertion`. Fetches issuer `/identity` over HTTPS,
  verifies the token against the retrieved public key and this brain's
  `BRAIN_ID` as expected audience.

No breaking changes. The library primitives
(`issue_federation_assertion`, `verify_federation_assertion`) have
shipped since v0.6.0; this release exposes them over HTTP and provides
the operator tooling to test cross-brain.

## 2026-04 — rename

**CognitiveOS renamed to BrainKernel.** The governance kernel inside
a brainfoundry-nous node is now called BrainKernel in all
documentation. The underlying container name and env var prefix
remain `nodeos` for infrastructure continuity. This change is a
documentation update to (a) avoid conflict with a pre-existing
trademark registration for the term "CognitiveOS" held by a third
party in an unrelated software consultancy category, and (b) use a
more technically accurate name — the component is a kernel (core
governance layer inside a node), not a full operating system. No
code or API behavior changes.
