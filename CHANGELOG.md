# Changelog

## 2026-05-02 — substrate floor (Layer 1) live

**Federation membership now gated on substrate-depth.** The
`/v1/federation/assertion` handler runs an additive precondition after
sig/replay/jti: it fetches the issuer's `/v1/federation/substrate-depth`
and checks `artifact_count >= 50`, `first_person_count >= 25`,
`source_diversity >= 2`, `(now - oldest_artifact_ts).days >= 7`. The
depth payload is signed by the issuer and verified against the same
pinned pubkey from `known_peers.toml` that gates the handshake itself —
no self-attesting trust. Failure returns HTTP 403 with a
machine-readable `{ok, code, details}` body.

Verified live 2026-05-02: `hbar → yury` assertion returned `403
substrate_floor_not_met` with full per-check breakdown (artifact_count
0/50, first_person 0/25, diversity 0/2, age null/7d) — gate path
exercised end-to-end.

New:

- `api/substrate.py` — Postgres-backed `artifact_attestations` ledger,
  ED25519 signing of the depth payload, threshold check, peer
  fetch+cache (5-minute TTL).
- Public unauthenticated `GET /v1/federation/substrate-depth` —
  returns metrics over the local attestation ledger (counts, hashes,
  byte sizes, source-type diversity, oldest/newest timestamps),
  signed by the brain's federation keypair. Cached 5 minutes.
- Auto-attestation hooks in `/chat/sessions/{id}/consolidate` and
  `/documents/upload` — every newly-ingested artifact writes a row
  with `backfilled=false` containing a sha256 hash over the full
  source text (not per-chunk), source_type, byte size,
  `first_person_attestation` (default `authored_by_owner`), and an
  ED25519 signature over the canonical row payload.
- `scripts/substrate_backfill.py` — DRY-RUN by default, `--commit`
  applies. Reconstructs documents from `document_embeddings`, groups
  chunks by `document_name`, generates one attestation per document
  with `backfilled=true`. Operators that ingested scraped material
  pass `--label-derived <pattern>`.

Federation registry (`api/identity/known_peers.toml`) populated on
all four brains (yury, hbar, e2e, nous) — each pinning the other
three with verified pubkeys. Verified live: `hbar → yury` and
`hbar → nous` both return `403 substrate_floor_not_met` with full
per-check details.

Env (all defaults baked in):

- `FEDERATION_SUBSTRATE_GATE` — set `off` to disable the gate; the
  endpoint serves regardless. Default `on`.
- `FEDERATION_SUBSTRATE_MIN_ARTIFACTS` (50)
- `FEDERATION_SUBSTRATE_MIN_FIRST_PERSON` (25)
- `FEDERATION_SUBSTRATE_MIN_DIVERSITY` (2)
- `FEDERATION_SUBSTRATE_MIN_AGE_DAYS` (7)
- `SUBSTRATE_DEPTH_CACHE_SECONDS` (300)
- `SUBSTRATE_PEER_CACHE_SECONDS` (300)

13 unit/integration tests in `tests/test_substrate.py` (12 pass, 1
opt-in live-DB via `SUBSTRATE_PG_TEST=1`).

No breaking changes. Federation DM (`/v1/federation/dm/*`) is
unaffected — it uses a separate signature-only path that does not go
through `/v1/federation/assertion`.

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
