# Changelog

The single source of truth for the running version is the `VERSION` file
at the repo root. Bump policy is in [`docs/VERSIONING.md`](docs/VERSIONING.md).
Older entries below carry only their date — semver tagging starts at 0.8.2.

## 0.9.1 — 2026-07-08 — launch pre-flight

Ships on top of the 0.9.0 security release: the quickstart now runs as pasted on
a clean VM, and the unauthenticated public demo surface is hardened against
prompt injection.

- security: **public-chat prompt-injection hardening (launch pre-flight).** The
  unauthenticated `/v1/public/chat` (and the machine `/v1/federation/query`)
  prompt builder fed raw retrieved documents and caller-supplied history
  straight into the local model beside the persona — `THREAT_MODEL.md` §2 claims
  retrieved docs are demoted, but the public path did not do it. Both are now
  routed through the Odysseus untrusted-context wrapper
  (`api/security/untrusted.py`): the do-not-follow policy leads the prompt,
  retrieved docs are fenced as untrusted data, and caller history is neutralized
  + fenced so forged `system`/`assistant` turns cannot pose as prompt structure.
  New guards in `tests/test_public_chat_injection.py`.
- dx: **one-command quickstart that runs as pasted on a clean VM.**
  `scripts/start_docker.sh` now creates `.env` and fills the four required
  secrets with `openssl rand -hex 32` (so the api no longer crash-loops on an
  empty `BRAIN_IDENTITY_SECRET`), pulls the local models the brain answers with
  (`llama3.2:3b` + `:1b`), builds, and health-waits. README Quickstart is a
  single paste (`git clone` → `cd` → `./scripts/start_docker.sh`) and "start
  chatting" returns a local-model reply with no cloud key. README also leads
  with "private, self-hosted AI with real memory", adds a one-line name
  glossary, un-flags the live `nous.brainfoundry.ai` demo, and genericizes the
  personal `/home/hbar/brain` default.

## 0.9.0 — 2026-07-05

- security: **pre-launch hardening (release-prep).** Fail-closed on a weak
  Postgres password in non-dev; `PUBLIC_CHAT_DAILY_MAX` now defaults to 2000
  (was unlimited); `X-Forwarded-For` is only trusted when `TRUST_PROXY_HEADERS=true`
  (default false); `/var/run/docker.sock` removed from the default compose file
  (in-console `/admin/update` is now an opt-in via `docker-compose.override.yml`).
  See [`RELEASE_NOTES.md`](RELEASE_NOTES.md) for upgrade impact. New guards in
  `tests/test_release_hardening.py`. Naming standardized in prose (BrainFoundry
  product / BrainKernel kernel; `nous` reserved as an instance name) with a
  deferred code-rename table in [`docs/NAMING.md`](docs/NAMING.md).
- feat: **persistent "your mind" panel + dashboard value card (onboarding v0.1).**
  The live fact panel is no longer onboarding-only — it's an always-on,
  dismissable, re-openable window into what your brain knows about you. A brain
  icon in the chat header toggles it at any time, on any brain; the panel's X
  hides it; both states persist per-brain in runtime settings (`mind_panel_shown`,
  default OFF). Re-open it months later and watch a new fact land live as you
  talk. DRAFT copy.
  - **Per-turn extraction on the normal chat path.** When the panel is shown,
    each authenticated `/chat/rag` turn runs the SAME verified extraction + write
    path the onboarding panel uses (operator-direct → `semantic` trust 1.0,
    `source=onboarding-self-stated`), surfaced as the existing `onboarding_facts`
    SSE frame. **Cost-gated:** extraction runs ONLY when the panel is shown, and
    on a new cheap resolver (`providers.cheap_extraction_model()` → Haiku-class,
    never the operator's expensive default; local/free when no cloud key) — so a
    hidden panel adds zero cost and an established fleet brain is unchanged until
    its owner opts in. One-tap "that's not me" removal works from the persistent
    panel too (source-guarded delete). New endpoints: `GET`/`POST /mind/panel`.
  - **Dashboard card** states the value plainly ("Talk to your brain — it learns
    you as you go") with a CTA into Chat — the "what is this for" the dashboard
    was missing. No new env var (so nothing to wire into compose). Onboarding v0
    (the trial-reasoner first-run path + its gating) is unchanged.

- fix: **wire trial/onboarding env into the compose api service (was
  dead-on-arrival).** The api service uses an explicit `environment:` allow-list
  (not `env_file`), so none of the nine onboarding/trial vars reached the
  container — `TRIAL_REASONER_API_KEY` set in `.env` never arrived. Wired all
  nine as `${NAME:-}`, hardened the trial-reasoner config getters to treat
  empty-string as "use default" (so the compose pattern can't crash `int("")`),
  and added a regression test that asserts every `TRIAL_*`/`ONBOARDING_*` env the
  code reads is wired into the compose api block. Caught by the e2e live-verify.

- feat: **first-run "become-you" onboarding — a fresh, keyless brain that turns
  a cold stranger into "I want one".** A brand-new (near-empty corpus) brain can
  now run a first-run experience instead of the empty-Knowledge-tab + BYOK-wall
  dead end: the brain speaks first with a curious hook, reflects sharply, and
  visibly forms a model of the owner in a live "your mind" side panel — all
  stored only in their own brain, no upload and no key required. **DRAFT copy**
  (opener / CTA / first-run persona) ships behind the mechanism — refine before
  public use.
  - **Trial reasoner (`api/onboarding/trial_reasoner.py`).** A fresh brain has no
    cloud key and the local model is too weak for sharp reflections, so the
    operator funds a SHARED key (`TRIAL_REASONER_API_KEY`, default model
    `claude-haiku-4-5`) used only for the first session. It is a DEDICATED client,
    kept entirely out of `api/providers.py`, so no normal chat turn on any brain
    can ever spend it. Every call is metered fail-closed via reserve-then-
    reconcile against a HARD per-session token cap, a per-IP/day token cap, a
    per-IP/day distinct-session cap, and an optional brain-wide kill-ceiling
    (Redis primary, JSON-sidecar fallback; counters configured-but-unreachable →
    refuse, never proceed unmetered). Source IP is hashed in the audit log.
  - **Live fact extraction + "your mind" panel.** After each turn a structured
    extraction call pulls high-confidence facts about the owner; self-stated
    facts are written operator-direct → `semantic` (trust 1.0) through the same
    hardened write path the Store button uses (`source=onboarding-self-stated`,
    `identity` layer). The chat UI renders them live with a growing counter and a
    one-tap "that's not me" removal (source-guarded delete).
  - **Tight first-run gate (the safety contract).** Everything is inert unless
    `is_fresh_brain()` (near-empty corpus AND onboarding-not-completed; corpus
    read fails safe-OFF) AND a trial key is configured. With `TRIAL_REASONER_API_KEY`
    unset — the state of every already-provisioned brain — `/onboarding/status`
    returns `active:false`, `/chat/rag` is byte-for-byte the old path, and the UI
    renders nothing new. New endpoints: `/onboarding/{status,opener,complete,facts}`
    + `DELETE /onboarding/fact/{id}`. Shared JSON-extraction util lifted to
    `api/json_utils.py` (also used by `/memory/store/propose`).

- fix: **vendor disavowal now catches lettered model suffixes (`gpt 4o` /
  `gpt-4o`).** The GPT pattern required the version digits to end on a word
  boundary, so `4o` never matched and `_detect_named_vendors` missed GPT-4o
  identity questions. Surfaced by the new CI unit job (`test_gpt_versioned_pattern`).

- ops: **CI + automated backups — the safety net under the fleet.** 12+ brains
  deploy by `git pull` from `main`, and a brain holds its owner's accumulated
  cognition; there was no test gate before `main` reached them and no backup
  under their memory. This closes both.
  - **CI (`.github/workflows/ci.yml`).** Runs on push + PR to `main`:
    `lint` (byte-compile, fails in seconds on a typo) → `unit` (the full pytest
    suite with no external services; the live-DB tests in `test_substrate.py`
    self-skip) + `integration` (those same live-DB tests run for real against a
    `pgvector/pgvector:pg16` service container, so "needs a DB" never means
    "silently skipped"). Operator flips on branch protection to make the checks
    block merge — until then they report but do not enforce.
  - **`scripts/backup_brain.sh`.** One sovereign, local, restorable artifact per
    run: `pg_dump` of the whole vector DB (gzipped) + a tar of the per-brain
    runtime state that is not in git (`settings.json`, `brain_persona.local.md`,
    `peers.json`, the federation/tool/governance audit logs, `brain-apps/`).
    Secrets are excluded by design (same rule as `export_brain.py`). Rotating
    retention (7 daily + 4 weekly + 10 pre-update, every prune logged), a
    host-cron schedule, and a `--pre-update` mode. Never phones home.
  - **Pre-update snapshot.** `scripts/update_brain.sh` now takes a
    `--pre-update` backup *before* it pulls and rebuilds against the live
    Postgres volume — a bad deploy costs minutes, not a brain. Best-effort by
    default; `REQUIRE_BACKUP=1` makes a missing snapshot abort the update.
  - **`scripts/restore_brain.sh` + `docs/BACKUP_RESTORE.md`.** Fresh box →
    `docker compose up` → restore the dump + untar runtime → brain is back. The
    runbook proves the restore, not just that the dump runs.

- security: **write-lane hardening — scan + classify every path into memory
  (cognitive-OS gap #3, write side).** The read side already demoted untrusted
  chunks; the write side was unguarded — several endpoints wrote straight into
  `document_embeddings` with no injection scan and no memory-type stamp, so a
  poisoned document written once re-injected into every future session that
  retrieved it, and the read-side rerank gave zero defense. Now **every** write
  path scans (`injection_scan.scan_text`) and classifies
  (`memory_type.classify_write`) before persisting:
  - **Operator-direct** writes (chat Store button `/memory/store`, approved
    upload) → `semantic`, not demoted; the scan band is recorded in provenance
    for audit. Closes the `/memory/store` gap where `mem_type` was never stamped.
  - **Non-interactive / external** writes (`/memory/append`, automated
    `brain_ingest`, stored tool/peer answers) → `untrusted` (0.4× at retrieval)
    by default; a **high**-severity hit additionally **quarantines** the chunk
    (persisted with provenance, excluded from retrieval via `memory_type.rerank`
    until the operator releases it — logged, never silently dropped). Never
    `semantic`. A brain app can't launder its content up to `semantic` or clear
    a quarantine via passthrough metadata.
  - `brain_ingest` rides the already-hardened document-upload propose/approve
    flow (scan at propose, classify at approve), with operator approval in loop.
  - The dev-gated kernel `MEMORY_APPEND` handler stamps the same scan +
    classification (jsonl-only today, so it carries the gate forward if ever
    pointed at the vector store).
  - **Operator review UI + audit.** Knowledge tab gains a Quarantine review
    queue (`GET /documents/quarantine`) listing held docs with risk band,
    source, `ingested_by`, held-at, and a content preview so the operator sees
    *why* it was held. Two triage actions:
    - **Release** (`POST /documents/{name}/release`) clears the quarantine flag
      so the doc re-enters retrieval, landing `untrusted` (0.4×). It does **not**
      promote to `semantic`, by design and for consistency: `classify_upload`
      already caps operator-*approved* medium/high uploads at `untrusted` —
      nowhere does approval of injection-flagged content earn full trust, only
      operator *authorship* does. To fully trust it, re-author via the Store
      button.
    - **Delete** (`POST /documents/{name}/quarantine/delete`) hard-deletes the
      quarantined chunks — the "actually malicious" path (scoped to
      still-quarantined chunks; not a general hard-delete bypass).
    Every release/delete is written to an append-only `api/quarantine_audit.py`
    log (mirrors `federation_audit.py`), queryable via
    `GET /documents/quarantine/log`.
  - `THREAT_MODEL.md` §6 gap #3 narrowed from "principal residual surface" to
    "heuristic-coverage residual".

- federation: **federation MVP — per-peer caps, cross-brain audit log, sanctioned
  introduce path.** The proven cross-brain READ path is now operationally safe to
  leave on.
  - **Per-peer caps.** Inbound `/v1/federation/query` gains a `FederationRateLimiter`
    keyed by verified-peer `brain_id` (signed assertion) or IP for anonymous
    callers — per-window + per-caller daily cap (`FEDERATION_RATE_LIMIT_*`,
    `FEDERATION_DAILY_MAX`). Outbound `brain_call` gets a per-peer monthly budget
    (`brain_call:<id>` key, `FEDERATION_OUTBOUND_MONTHLY_CAP`) that refuses before
    the round-trip and audit-logs the refusal. `brain_call` now signs each request
    so the peer can cap *us*, not just our IP.
  - **Cross-brain audit log.** `api/tools/federation_audit.py` writes one
    append-only JSONL line per federation event, both directions
    (`ts, direction, peer_brain_id, query_summary, documents_used, answer_len,
    verified, trust, outcome`). `GET /v1/federation/log` (operator-authed) + a
    Settings → Security & Federation activity-log panel.
  - **Sanctioned introduce path.** Operator-authed REST endpoints
    (`/v1/federation/peers` list/introduce/ping + `DELETE …/{id}`) replace
    hand-editing `data/peers.json`; introduce pins the peer's `/identity` public
    key. Settings panel gains an "Introduce peer" form with per-peer ping/remove.
- integrations: **connect your real world — email, calendar, Telegram, MCP (the
  no-OAuth way).** A new **Integrations** tab plus agentic tools so the brain can
  act on your life. Modeled on Odysseus's productivity suite but using
  app-password/link auth, not OAuth, so setup is minutes not a cloud-console maze.
  - **Email (IMAP)** — host + email + app password (Gmail/Outlook/Fastmail/iCloud/
    self-hosted). Tool `inbox_read` (recent/unread, search). `api/integrations/email_imap.py`.
  - **Calendar (iCal link)** — paste the "secret iCal (.ics)" URL any provider
    exposes. Tool `calendar_read`. `api/integrations/calendar_ics.py`.
  - **Telegram** — `@BotFather` token → secret-protected webhook; chat your brain
    from your phone, answered from its memory + reasoner. First chat is pinned as
    owner; strangers refused. `api/integrations/telegram.py`.
  - **MCP servers** — connect a remote MCP server (Streamable-HTTP); its tools
    become `mcp__<server>__<tool>` in the agentic loop. `api/integrations/mcp_client.py`.
  - **Google Drive (OAuth, optional)** — the one connector that still needs OAuth;
    `drive_search`. Email/calendar do NOT use OAuth.
- research: **Deep Research** — a new **Research** tab + `POST /research` (SSE).
  Plans search queries, reads multiple sources via `web_search` + the new
  `fetch_url` tool, and writes a cited report, streamed live. `api/research.py`.
- tasks: **Tasks / reminders** — a **Tasks** tab + `/tasks` CRUD + tools
  `task_add`/`task_list`. "remind me to … tomorrow" creates a task; a due time
  pings your connected Telegram. `api/tasks_store.py`.
- tools: **`fetch_url`** — read a single web page (SSRF-guarded, untrusted-wrapped),
  the companion to `web_search`. Surfaced to the agentic loop.
- security: **prompt-injection hardening** (Odysseus-modeled, MIT — see NOTICE).
  `api/security/untrusted.py` wraps every external surface (RAG hits, web/page
  output, email/calendar/MCP results) as untrusted data with a do-not-follow
  header; a fail-closed tool gate (`is_blocked_tool`) default-denies shell/file/
  email/settings/`mcp__*` for the model-driven loop; `THREAT_MODEL.md` shipped.
- models: **BYOK frontier as the default reasoner.** When a cloud key is set,
  operator chat defaults to a frontier model matched to the keyed provider
  (Anthropic → Opus); memory + RAG stay sovereign on the brain. Local Ollama is
  the offline fallback.
- retrieval: **default architecture is now `flat`** (similarity-only). The old
  `tiered` default force-injected the same identity/context docs into every
  answer regardless of relevance ("why the same citations every time").
  Model-aware RAG context budget added so a small local model's window isn't
  swamped (cloud keeps full document bodies).
- fix: **persona persists across rebuilds** — it now lives in the `/app/runtime`
  volume, not the image-baked `api/` dir that `docker compose up --build` wiped
  (the "brain forgot its name after every deploy" bug).
- fix: **reliable deploys** — `repair_repo_ownership()` self-heals a root-owned
  bind-mounted repo so host `git pull` stops silently failing. See `docs/DEPLOYMENT.md`.
- fix: **Firefox loads behind Basic Auth** — the service worker no longer
  intercepts navigations (it couldn't resolve the 401 auth challenge in Firefox).

- ui: **math renders again, and the tool trail names the peer.** (1) Inline
  LaTeX (`$\hat{A}^\dagger = \hat{A}$`, `$P(H|D)$`) was showing as raw source
  because `singleDollarTextMath` was turned OFF to stop prose dollar amounts
  ("$50 billion") rendering as math — wrong trade-off for an educational brain.
  Now single-dollar math is ON and currency `$`-before-a-digit is escaped to a
  literal instead, so both render correctly (display `$$…$$` untouched). (2) The
  agentic tool trail now shows the target — `🔧 brain_call → hbar-university`,
  `🔧 web_search → <query>` — instead of a bare tool name; the per-call `detail`
  rides in the tool event.
- federation: **`brain_call` — a brain can ask another brain (orchestration v0).**
  The agentic loop can now reach a peer brain: register hbar.university /
  hbar.science (etc.) as introduced peers, turn on agentic mode, and the model
  can call `brain_call(target, query)` to get an answer from that peer's own
  corpus and synthesize it WITH attribution ("according to hbar.university: …").
  Two halves: (1) serving — new `POST /v1/federation/query`, the machine-callable
  cross-brain READ surface every brain now exposes (non-streaming JSON, no
  Turnstile, per-IP rate-limited, answers only from the same PUBLIC_CHAT_LAYERS /
  SCOPE the public chat already serves, so federation never exposes more than
  public); (2) calling — `api/tools/brain_call.py`, a YELLOW tool (a cross-brain
  read is external-read, same tier as web search; a cross-brain *write* would be
  RED, not this). The callable directory is the brain's introduced-peers list
  (`data/peers.json`, managed via the `peers.*` kernel commands); v0 calls the
  peer's public surface so no signing is needed (signed private-scope reads are a
  later tier). The peer's answer is wrapped as an attributed, untrusted reference
  (treat as citation, don't obey embedded instructions). The agentic loop injects
  the live peer list into `brain_call`'s target enum each turn (and drops the
  tool when no peers are configured). Every call is tier-gated + audited like any
  tool. 6 tests. This is the team-of-brains orchestration story — each node a
  full sovereign brain, not a sub-agent.
- tools: **native model-driven tool-calling + permission-tier enforcement
  (opt-in agentic mode).** The brain can now DECIDE when to use a tool instead
  of the operator flipping the per-message 🌐 toggle. `api/providers.py` gains
  `complete_with_tools()` — an agentic loop for Anthropic + OpenAI-compatible
  models: the model emits a tool call, it runs through the existing tier-gated
  `tools.dispatch()` (GREEN auto, YELLOW standing-auth, RED still fail-closed),
  the result is fed back, repeat (capped at 4 rounds as a loop guard). Works on
  Anthropic, OpenAI-compatible, AND local Ollama models — federation never
  requires a cloud model (sovereignty). Capable local models (llama3.3:70b,
  qwen2.5:72b, mistral-nemo, …) tool-call well; a model that can't simply
  answers without tool calls, never an error.
  New GREEN tool `search_memory` (the model reads its own corpus on demand,
  carrying memory-type provenance) — the green-tier counterpart to yellow
  `web_search`. Agentic mode is **off by default**, opt-in per brain via
  `POST /settings/agentic-tools`, so the deterministic safe path never
  regresses; `rag_chat_completion` runs the agentic loop only when it's on AND
  the model supports native tools, and falls back to a plain completion if the
  tool path errors so an answer is never lost. The chat answer shows a compact
  tool trail (🔧 tool / ⚠ failed-or-blocked); full detail stays on `/trace`.
  RED stays blocked — its per-call approval flow is a later build (read-only
  first, write second). 9 tests (schema converters + both provider loops with
  faked clients + registry tiers).
- ui: **green / yellow / red permission tiers explained.** New Settings →
  "Agentic tools" panel with the agentic-mode toggle and a plain-language
  legend — green reads your own memory (always on), yellow reaches the open web
  / external APIs (you enable it; audited + capped), red writes / sends /
  executes (per-call approval, not enabled yet) — plus a tier-dotted list of the
  tools your brain can call. Backed by a single source of truth
  (`GET /tools/tiers`) so the definitions never drift between code and UI.
- fix: **Knowledge "Browse — by memory layer" capped at 500 docs.** On a brain
  past ~500 documents the browse panel listed only the 500 most-recent docs AND
  undercounted every layer (the per-layer counts are derived client-side from
  that capped list, so the cap propagated into the counts) — e.g. hbar's 647
  docs showed as "500 total" with identity 14 vs 23, episodic 291 vs 365. The
  brain itself was fine; retrieval/chat/search always used the full corpus, only
  this manual listing was capped. `ui/pages/upload.js` now requests `?limit=
  10000` (a soft ceiling, not an assumption) and shows "showing N of TOTAL" if a
  brain ever exceeds it (the response already returns the true `total`). Backend
  `list_documents` default bumped 500 → 10000 as defense; `?offset` paging is
  already wired for any brain that eventually exceeds 10000. Template bug — every
  brain past 500 docs benefits.
- tools: **FactChecker generalized to the brain's own documents (cognitive-OS
  gap #2 phase 3 — the payoff).** The corroboration score that web search got
  now also runs over RAG answers, using the per-chunk provenance phase 1+2 added.
  `api/factcheck.py` refactored to a shared `_corroboration_core` (the
  independence·agreement·trust math was already source-agnostic); new
  `score_rag_corroboration(docs)` maps RAG provenance onto the three factors —
  **independence** = distinct source documents (by `content_hash`, else
  `document_name`, so five chunks of one doc don't self-corroborate),
  **trust** = mean per-chunk `source_trust` (an answer grounded only in
  `untrusted` chunks scores low — the gap-#5 signal made visible),
  **agreement** = mean pairwise cosine of the chunk contents. Every RAG answer
  now carries `rag_metadata.corroboration` (both streaming + non-streaming),
  surfaced in the chat UI as a colour-banded `corroboration N%` badge on the
  sources panel with an expandable breakdown (independent documents / agreement
  / trust / dissenting docs) — mirroring the web badge. New `POST
  /factcheck/score-rag` endpoint. The web score's output shape is unchanged
  (`n_domains` preserved for the existing UI). Presented, like the web score, as
  a MEASUREMENT of support, not a truth verdict; returns null for <2 chunks and
  degrades to independence+trust when embeddings are unavailable. 10 tests.
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
