# Changelog

The single source of truth for the running version is the `VERSION` file
at the repo root. Bump policy is in [`docs/VERSIONING.md`](docs/VERSIONING.md).
Older entries below carry only their date — semver tagging starts at 0.8.2.

## Unreleased

- memory: **memory-type separation + provenance (cognitive-OS gap #2, phase
  1+2).** Every retrievable chunk now carries a **memory type** and
  **provenance**, and retrieval weights by it. New `api/memory_type.py` defines
  the trust taxonomy — `semantic` (operator-curated upload), `reflective`
  (derived/inferred summary, e.g. chat consolidation), `untrusted` (an upload
  the injection scan flagged medium/high), `ephemeral` (session scratch, never
  persisted) — a **different axis** from the user-named `layer` (they use
  distinct metadata keys and never collide). At ingest, each chunk is stamped
  structurally by its path: uploads → `semantic` (or `untrusted` if the
  persisted injection-scan band is medium/high — which makes the gap-#3 defense
  *structural*, not just a one-time warning), consolidation summaries →
  `reflective`; provenance records `source`, `derivation` (observed/inferred),
  `ingested_at`, `ingested_by`, `source_trust`, and `content_hash` (the join key
  back to the signed `artifact_attestations` ledger that was missing before). At
  retrieval, the flat and layer-scoped paths overscan then rerank by
  `similarity × trust_prior` so `untrusted` chunks are demoted (not erased — the
  roadmap wants conflicting evidence surfaced) and `ephemeral` dropped; a
  poisoned chunk can no longer dominate retrieval on raw similarity alone (gap
  #5). The RAG prompt now labels each document with its type/derivation
  (`[Document N — semantic, observed]`) so the model — and the operator reading
  a trace — can tell a curated fact from an inferred summary from an untrusted
  scrape (gap #4). Schema: two partial indexes (`mem_type`, `content_hash`) in
  `vector-db/init.sql` + boot-time ensure; backward-compatible — an untagged
  legacy chunk is treated as `semantic` at read, so no migration is *required*.
  Optional backfill `scripts/backfill_memory_type.py` (idempotent, SSH-into-
  container like `reembed_null_embeddings.py`) makes existing tags explicit.
  13 tests. Deferred to a follow-up: FactChecker generalization over RAG/cross-
  brain claims (phase 3) and the UI type chips (phase 4).
- tools: **Tool activity shows the query + clickable sources.** The dispatch
  audit record now keeps each call's sources (title + url, capped at 10), and
  the `/trace` Tool activity rows show the search query (`"…"`) and expand to a
  numbered list of clickable source links — so the operator can check *what the
  brain actually read*, not just a "5 sources" count. (Sources were already
  clickable in the chat answer's web panel; this brings the historical audit
  view to parity.)
- ui: **fix "deployed but the UI looks the same."** Two changes so a new build
  is always visible: (1) the service worker now fetches page navigations with
  `cache:'no-store'` (was network-first but the browser HTTP cache could still
  hand it a stale page → stale chunk references); a normal refresh after a
  deploy now always loads the fresh page. CACHE_NAME bumped to v3. (2) A
  new-version banner in `_app.js` — once a tab is open, clicking nav links does
  client-side routing with the already-loaded bundle, so a deploy is invisible
  until a full reload; the app now polls the live page's Next buildId (on mount,
  on focus, every 2 min) and, when it differs from the loaded one, shows a
  one-click "A new version of your brain is ready · Reload".
- ui: **Tool activity on the Trace page** — the `/tools/audit` trail now has a
  surface. A "Tool activity" section on `/trace` lists every external tool call
  the brain made (web search, future tools) newest-first: success/fail dot, tool
  name, tier, result/reason summary, relative time. Closes the "what did my
  brain reach out and do" loop; the audit log was endpoint-only before.
- security: **prompt-injection defenses on ingest** (cognitive-OS gap #3). A
  poisoned PDF / scraped page / forwarded email can carry text aimed at the
  MODEL ("ignore your instructions", "reveal your system prompt", a forged
  `System:` turn, invisible zero-width instructions) that, once embedded, can be
  retrieved into a later answer and treated as a command. Two layers: (1)
  `api/injection_scan.py` scans extracted text at propose time for injection
  patterns + invisible-character payloads and returns a risk band — surfaced to
  the operator in the Knowledge-tab approval card (⚠ banner + flagged passages)
  so a poisoned doc is visible BEFORE it lands in memory; it informs, never
  auto-blocks (respects propose→approve governance). (2) Structural backstop in
  the RAG prompt: retrieved documents are now explicitly framed as reference to
  draw facts from, and the model is told not to obey instructions embedded in
  them. 11 tests.
- fix: **root-owned `.git` — the Update tab / `git pull` permission bug.** The
  api container runs git as root against the bind-mounted repo (`/admin/version-
  info` fetches origin on every console load; `/admin/update` pulls), which
  root-clobbered `.git/FETCH_HEAD` etc. so the host SSH user got
  `cannot open '.git/FETCH_HEAD': Permission denied` and deploys degraded to
  rsync (which then diverges the checkout — the mess that bit hbar 2026-05-30).
  New `api/git_ownership.py` re-owns `.git` to the host user after the root
  fetch, plus a boot-time migration (runs on every container restart, so it also
  covers post-update) that repairs brains already in the broken state. Mirrors
  the brain-apps container-root-chown pattern; best-effort, never blocks a
  request or startup. Makes "deploy via the Update tab, never rsync" actually
  hold on every brain + future provision.
- ui: **"How it works" explainer** in Settings → Web search — a collapsed,
  sentence-per-line teaching block covering what web search is, how it stays
  safe (untrusted results, cites URLs, never obeys hidden instructions), what
  the corroboration score means (a measurement of agreement, not a verdict),
  and cost/control. Closes the "is there a place where this is clear to users"
  gap; the per-tool "How it works" block is the pattern for future tools.
- tools: **corroboration score (FactChecker v0).** Every web-search answer now
  carries a measured trust signal — `corroboration N%` shown next to the web
  sources — computed in `api/factcheck.py` as
  `100·(0.35·independence + 0.35·agreement + 0.30·trust)`: **independence** =
  count of distinct registrable domains (five copies of one wire story ≠
  corroboration), **agreement** = mean pairwise cosine of the source snippets
  via the brain's bge-large embeddings (do the sources actually say the same
  thing?), **trust** = mean per-domain prior from a small operator-extensible
  seed list (gov/edu/wire weigh more). Sources that disagree with the rest are
  flagged as ⚠ dissenters rather than averaged away. Presented honestly as a
  MEASUREMENT of source agreement, not a truth verdict; degrades gracefully
  (drops the agreement term) when embeddings are unavailable, and returns null
  for <2 sources. New `POST /factcheck/score` endpoint for reuse. The same
  scorer will later cover RAG-doc and cross-brain claims once they carry
  provenance.
- ui: **web-search result citations + dollar-amount rendering fix.** (1) The
  URLs the brain pulls from the web now render as a collapsible "🌐 N web
  sources (untrusted)" panel under the message (numbered to match the inline
  [1]/[2] citations), so those references resolve instead of dangling; a failed
  search shows a quiet note rather than silently looking like "chose not to
  search". (2) `singleDollarTextMath: false` in MessageRenderer — prose dollar
  amounts ("$50 billion … $225 billion", common in web/news/finance results)
  were being parsed as inline LaTeX and rendered as a vertical stack of
  characters; lone `$` is now plain text, `$$…$$` display math still works.
- build: **CPU-only torch + `.dockerignore`** — fixes recurring "no space left
  on device" failures during `docker compose up -d --build` on brain boxes. The
  fleet has no GPU (Hetzner CAX ARM, CPU embeddings + CPU Ollama), but the
  default `torch` wheel pulled transitively by `sentence-transformers` dragged
  in multi-GB `nvidia/cudnn` CUDA libraries — dead weight that filled small
  disks during rebuilds. `api/Dockerfile` now installs CPU-only torch from
  PyTorch's cpu index before requirements so sentence-transformers sees torch
  already satisfied and never installs the CUDA build (saves ~GBs/image). Added
  a root `.dockerignore` (api build context = repo root; the image only needs
  `api/` + `VERSION`, so `.git`/`ui`/`nodeos`/`apps`/`vector-db`/`__pycache__`
  etc. no longer ship to the builder) and `ui/.dockerignore` (drops
  `node_modules`/`.next`, regenerated by `npm ci`/`build`). Template fix —
  every future provision inherits it. Host hygiene to reclaim already-bloated
  boxes: `docker builder prune -af && docker image prune -f` (never
  `--volumes` — that holds the brain's memory).
- tools: the brain gets its first real external capability — **web search**
  (Brave Search API). New `api/tools/` package: a permission-tiered registry +
  dispatcher (`green`/`yellow`/`red`) that every future tool (fetch, calendar,
  mail, `brain_call`) slots into. Web search is `yellow` (external API read):
  off by default, enabled by the operator in Settings → Web search with a Brave
  key under their own billing. Every dispatch is audited (`/app/runtime/
  tool_audit.jsonl`, surfaced read-only at `GET /tools/audit`) and counted
  against an operator-set monthly cap. Results enter chat as clearly-delimited
  **untrusted** reference data (`api/tools/safety.py`) with provenance (URL +
  retrieval time) — never as instructions the model can follow, and the
  delimiter tokens are neutralized so a crafted snippet can't break out. v0
  wiring is deterministic and operator-driven: a per-message `🌐 web` toggle in
  the chat composer sets `web_search: true` on `/chat/rag`; `red`-tier tools and
  native model-driven tool-calling are intentionally deferred to land with the
  permission-tier enforcement they depend on. Endpoints: `GET/POST
  /settings/web-search`, `POST /settings/web-search/key`, `GET /tools`,
  `GET /tools/audit`. Closes the first box of ROADMAP §v1.1+ "tool registry".
- brain-apps: install no longer leaves root-owned dirs on the host. The api
  container clones as root, so `brain-apps/<id>/` used to land root-owned on
  the bind-mounted host filesystem — the operator could not `rm` a stale dir
  without sudo and `app_dir_exists` blocked reinstall. After every successful
  `git clone` (install preview, install, update preview, update) the new
  tree is now chown'd to the bind-mount owner (or to `BRAIN_USER_UID:GID` if
  set). A one-shot startup migration in `mount_installed_apps` re-owns any
  already-existing app dirs that were left root-owned by the old path.
- brain-apps: `brain-apps/installed.json` is no longer tracked in git. It is
  per-brain runtime state and `_load_installed()` creates it on first request;
  tracking it as an empty stub meant every template-repo deploy could
  overwrite a brain's populated registry ("apps gone"). The stub is removed
  and `brain-apps/installed.json` is gitignored. The deploy rsync example in
  SERVERS.md gains `--exclude='brain-apps/installed.json'` and
  `--exclude='brain-apps/*/'` as defense in depth.
- brain-apps: an installed app can now be updated in place — no
  uninstall/reinstall. `POST /apps/{id}/update/preview` clones the repo at
  HEAD and reports whether it is up to date and whether the manifest
  changes the app's permission/memory-layer scope; `POST /apps/{id}/update`
  re-pins the SHA, swaps the served bundle (recoverable backup), refreshes
  installed.json, and hot-remounts. The app token and install date
  survive. A scope-changing update is refused unless `accept_scope_change`
  is set, so an update can never silently widen access. The Apps page card
  gets an Update button: silent one-click when scope is unchanged, a
  re-approval card showing the added/removed scope when it changed.
- ui/apps: brain-app install moved out of Settings onto the Apps page
  (`/apps`). The GitHub-URL field, manifest preview, permission/layer
  scope approval, just-installed token reveal, and per-app enable/disable
  + uninstall now all live on `/apps`. Settings -> Apps is reduced to a
  quiet, faded pointer back to the page (no controls there by design).
- ui/chat: composer newline handling is now device-aware. On touch
  devices (on-screen keyboard, no Shift) plain Enter inserts a newline and
  the Send button is the only way to send; on a real keyboard Enter still
  sends and Shift+Enter is the newline. The composer hint adapts to match
  (`↵ new line · tap Send` vs `⇧↵ newline`).
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
- ui: composer toolbar now shows a `⇧↵ newline` hint — plain Enter sends,
  Shift+Enter starts a new line. Previously invisible, so multi-line input
  (e.g. a bullet list built with the ≡ button) wasn't discoverable.

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
