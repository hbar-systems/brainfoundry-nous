# Changelog

The single source of truth for the running version is the `VERSION` file
at the repo root. Bump policy is in [`docs/VERSIONING.md`](docs/VERSIONING.md).
Older entries below carry only their date — semver tagging starts at 0.8.2.

## Unreleased

- rag: /chat/rag prompt now instructs the model to cite source documents
  inline (Event 14 follow-up).
- brain-apps: new `llm.complete` bridge intent. An installed app that
  declares the `llm.invoke` permission can ask the brain to generate a
  completion over its own corpus using the operator's selected (BYOK)
  model. The host shell (`ui/pages/apps/[id].js`) mints + holds the loop
  permit and proxies to `/chat/rag`; the iframe never sees the permit.
  RAG retrieval is scoped to the app's `read`-mode `requires_layers`.
  `ui/pages/api/permit.js` now accepts optional `agent_id` / `reason` so
  app-originated permits are attributable in the audit trail. Schema:
  `app.schema.json` adds `llm.invoke` to the `permissions` enum + an
  `allOf` rule requiring `requires_layers`. Non-streaming in v0.
- providers: local Ollama models now win over name-prefix routing.
  `_resolve` checks the live Ollama tag list (`GET /api/tags`, cached 60s,
  fail-soft) before the prefix heuristics, so an open-weight model whose
  name carries a foreign prefix (e.g. `gpt-oss:120b`) routes to local
  Ollama instead of erroring "API key not configured".
- ui: markdown tables in the chat no longer collapse. The message bubble's
  `word-break: break-word` was squeezing columns to ~1 char and wrapping
  header text letter-per-line; `MessageRenderer` now sets `table-layout`,
  a header `nowrap`, and a cell min-width, with horizontal scroll on
  overflow.
- ui: the Save-to-memory layer dropdown is now the themed `CustomSelect`
  instead of a native `<select>` — matches the rest of the chat header.

## 0.8.4 — 2026-05-11 — recency anchor for 1b public-chat

**Fix only.** 0.8.3 wasn't enough. Post-deploy probes showed the 1b
model fixating on the persona's opening disavowal block ("I am not
ChatGPT...") and refusing benign questions like "What is the capital of
France?" with "I cannot create content similar to ChatGPT". Per the
fix-it prompt's optional Change 4: small models follow the most-recent
instruction better than the first.

Changes:

- `api/main.py` — `_build_public_prompt` now appends a short positive
  recency reminder immediately before the user turn. Reiterates
  "answer in 1-2 grounded sentences", "never refuse benign questions",
  and "off-topic → redirect, not refusal". This is the same intent as
  the persona's tail paragraphs but planted at the recency slot where
  1b actually weights it.

No persona-file change. No schema. No env. PATCH-class fix on top of
0.8.3.

## 0.8.3 — 2026-05-11 — public-chat persona stability on 1b

**Fix only.** Public chat surface (`/v1/public/chat`) on llama3.2:1b was
drifting on plain self-intros — verification probes today returned
generic safety refusals ("I cannot provide information on illegal
activities") and word-salad on "what model are you running". The persona
file was already comprehensive; 1b just can't follow long instructions
without in-context examples.

Changes:

- `api/main.py` — `_build_public_prompt` now injects a 1-shot
  introduce-yourself example between the RAG documents block and the
  conversation history. Style anchor only; the model is told not to
  literally repeat it.
- `api/brain_persona_nous.md` — added explicit off-topic redirect
  instruction ("I'm Nous — I discuss brainfoundry…") so generic safety
  refusals no longer fire on benign weird questions. Also added an
  anti-hallucination guardrail forbidding invented implementation
  details beyond what the persona already authorises.

No schema, no new endpoints, no env. PATCH-class fix. Operator-side
chat (`/chat/rag`) and BYOK paths are untouched. 3b model upgrade is
not viable on CAX21 ARM (prompt-eval timeout on RAG context).

## 0.8.2 — 2026-05-02 — substrate floor (Layer 1) live

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
