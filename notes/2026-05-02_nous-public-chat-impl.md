DATE: 2026-05-02
DOMAIN: public surfaces / federation
SESSION TYPE: implementation
LINKS: ops/prompts/2026-05-02_nous-public-chat-surface.md

## KEY INSIGHTS

- The "expose the bare domain" problem is fundamentally a UI-shape problem,
  not a Caddy problem. The operator console's nav alone leaks the surface
  map (Dashboard / Knowledge / Federation / Trace / Settings / Update
  tabs are all visible in the rendered HTML even when their backends 401).
  A Caddy-only diff that just adds basicauth on the bare domain would
  still leak — strangers without creds would see the 401 page after
  rendering nothing useful, and any creds-leak would expose admin nav
  immediately. The right fix is a code-level UI split: a separate Next.js
  app with no admin chrome at all, served at the bare domain.

- The auth-model-differs-by-route shape was already in the codebase — see
  `api/federation_dm.py` `/v1/federation/dm/receive` (signature-only,
  bypasses `Depends(get_api_key)`). `/v1/public/chat` follows the same
  pattern (rate-limit-only, bypasses `Depends(get_api_key)`). Once you
  accept that "auth class differs per route" is a normal shape, the public
  chat endpoint stops feeling like an exception and starts feeling
  ordinary.

- `KernelRateLimiter` was almost-perfect for the public path — same Redis
  backend, same fail-closed semantics, same incr+expire shape. The only
  divergence was the key (client_id vs IP) and the env-var names. So
  `PublicRateLimiter` is a near-copy in the same file with two changes.
  This is a case where a tiny duplicated class beats parameterizing the
  original — readers of either limiter can see the whole thing in one
  scroll.

- Reading the *last* hop of `X-Forwarded-For` (not the first) is the
  load-bearing detail. Caddy with `trusted_proxies private_ranges`
  appends the real client IP as the last entry; earlier entries are
  whatever the client sent. Reading the first entry would let a stranger
  trivially defeat the per-IP rate limit by rotating a fake first-entry
  IP. The acceptance test that fires 11 requests with rotating
  `X-Forwarded-For: 10.0.0.{1..11}` confirms this — all 11 keyed to the
  real IP, the 11th returned 429.

- Without `trusted_proxies`, Caddy 2's default behavior is already to
  ignore client-supplied XFF and overwrite it with just the real client
  IP. So the spoofing protection works *by accident* on the unconfigured
  default — but the contract is implicit and brittle. Setting
  `trusted_proxies private_ranges` makes it explicit and survives future
  Caddy version changes.

- The rsync-skipped-main.py incident: rsync's default size+mtime check
  can miss an updated file if the mtime ordering looks ambiguous (host
  mtime later than local somehow). The fix was `rsync -avzc` (forced
  checksum compare) for the single file. Worth noting for future deploys
  — when in doubt, use `-c` for any file you've just edited and
  *believe* should have been transferred.

## OPEN QUESTIONS

- Should `api.nous.brainfoundry.ai` be locked down further (IP allowlist
  or basicauth on top of `X-API-Key`) so endpoint discovery is harder?
  Today it's reachable identically to before — same exposure surface as
  pre-split, no regression. But it's also no improvement. The case for
  not locking it down: federation DM's `/v1/federation/dm/receive` is
  designed to be publicly reachable for brain↔brain messaging, so any
  lockdown has to allowlist that endpoint. Defer until federation traffic
  patterns are clearer.

- Should the public chat persist a session_id (per-IP, per-browser)? v0
  is fully ephemeral — refresh = fresh chat. The argument for persistence:
  follow-up questions across page reloads. The argument against: persistence
  → storage → moderation → a much bigger product. Defer.

- Streaming via SSE is deferred. The relay is non-streaming and waits for
  the full reply before responding. On cold-start with llama3.2:3b the
  user waits ~30-60s with no feedback. SSE would chunk the reply and
  improve perceived latency dramatically. Cheap upgrade, worth doing once
  v0 is in front of users for a few days.

- The public corpus seed is operator action. Until 7 docs land with
  `metadata.layer="public"` set, the public chat answers from
  llama3.2:3b's training + the persona only. Worth tracking the moment
  the seed lands so we can A/B the difference in answer quality.

## DECISIONS MADE

- New Next.js app at `apps/public-chat/` (port 3020), zero imports from
  `ui/`. Deliberate isolation — risk of accidentally importing admin nav
  by reusing components is too high. The duplication cost (textarea,
  message bubble) is one screen of code.

- `/v1/public/chat` returns `{reply: string}` only. No `document_name`,
  no `metadata`, no `sources`, no `usage`, no `rag_metadata`. The public
  surface must not leak which docs were retrieved (could expose private
  doc names by accident if seeding ever messes up).

- Defense-in-depth caps live on **both** the relay and the brain endpoint:
  ≤10 messages, ≤2000 estimated tokens (relay) / ≤4000 chars/message,
  ≤12000 chars total (brain). The brain caps are stricter because the
  brain is independently reachable on `api.nous.brainfoundry.ai` and
  cannot trust that the relay was the one that limited input.

- `PUBLIC_RATE_LIMIT_MAX=10` / `PUBLIC_RATE_LIMIT_WINDOW=60` chosen as
  defaults. 10/min is generous enough for a real conversation (typical
  back-and-forth is 1-2 reqs/min) and tight enough to block scripted
  abuse without manual intervention.

- Three-vhost Caddy layout with explicit `trusted_proxies private_ranges`
  on the two public-facing reverse_proxy blocks (nous, api). console
  doesn't need it (basicauth gates everything; XFF isn't trusted there).

- The console basicauth credentials were preserved verbatim during the
  Caddy rewrite (same hashed bcrypt, same username `hbar`). No
  regeneration, no rotation — the rewrite is a layout change, not a
  credential change.

## BELIEF UPDATES

- I had assumed earlier that the bare nous domain was routing to port 3010
  (operator console). The Caddyfile survey showed it was actually routing
  to port 8010 (raw API). So strangers visiting the bare domain were
  hitting the FastAPI app directly and getting 401s on protected routes.
  The leak was less severe than feared — no admin nav was visible — but
  the fix shape is the same either way (split into three vhosts).

- I was nervous about the docker compose rebuild causing a long brain
  outage. In practice: ~30s gap on the api container (the rest of the
  stack stayed up), and the new public-chat container built and started
  in parallel. Total user-visible disruption: about 30s on the api
  endpoint, none on the console.

- Cold-start latency on llama3.2:3b is real. T3 took 56 seconds wall
  clock for a one-sentence reply. Subsequent calls are faster (~5-10s)
  once the model is warm in ollama. This argues for either (a) keeping
  ollama warm with a heartbeat, or (b) shipping SSE soon so users see
  progress.

---

## FOLLOW-UP — 2026-05-02 evening — two bugs found and fixed after corpus upload

After the operator uploaded 7 docs to `metadata.layer="public"` and ran the
adversarial verification, two bugs surfaced that blocked friend invites.
Both fixed in this session.

### Bug 1 — operator chat persona had unsubstituted [BRAIN_NAME] / [OWNER_NAME] placeholders

**Symptom:** operator console Chat tab returned replies starting with
"I am BrainName, the personal brain of OwnerName" with literal
`[OWNER_NAME]` artifacts mid-paragraph.

**Root cause:** `api/brain_persona.md` on nous was the unfilled
provisioner template. The personalize step
(`scripts/personalize_persona.py` substituting `[BRAIN_NAME]` →
`Nous`, `[OWNER_NAME]` → `Yury`) shipped after nous was provisioned
on 2026-04-16, so it was never run on this box. `brain_persona_nous.md`
(used by `/v1/public/chat`) was already correct — only the operator
persona was broken.

**Fix:**

- One-shot retrofit on nous:
  `cd /home/hbar/brain && python3 scripts/personalize_persona.py --brain-name "Nous" --owner-name "Yury"`
- Added `--exclude='api/brain_persona.md'` to the rsync command in
  `SERVERS.md` so a future deploy doesn't overwrite the personalized
  file with the repo template. The repo file stays as the canonical
  template for fresh provisioner runs.

**Verified:** `GET /persona` (operator-keyed) returns substituted text;
no `BrainName`, `OwnerName`, `[BRAIN_NAME]`, `[OWNER_NAME]`, or
`[CONFIGURE` strings remain.

### Bug 2 — `/v1/public/chat` returned "Upstream model error" after exact 2-minute hang

**Symptom:** `POST /api/chat` (relay) and direct
`POST /v1/public/chat` (brain) both returned
`{"error":"Upstream model error. Please try again."}` after exactly
2:00.4 elapsed time. Operator chat with API key worked fine.

**Root cause (chained):**

1. `api/providers.py:198` set `httpx.Timeout(10, read=120)` — the 120s
   read timeout is the upper bound on a single Ollama call.
2. `api/main.py:1480` set the public-chat model to
   `os.getenv("DEFAULT_MODEL")` which is `llama3.2:3b`.
3. CAX21 ARM64 prompt-eval throughput on 3b is ~6 tokens/sec (measured:
   a 19KB / 4800-token public-chat prompt didn't return within 5
   minutes when curled directly at Ollama). The httpx 120s read
   timeout fired first, the `except` returned the upstream-error
   envelope, and that propagated through the relay verbatim.

The 5.7s "say hi" cold-start I'd seen in the rollout note was
misleading — it measured load_duration + a 30-token prompt_eval, not
the realistic 4800-token public-chat prompt-eval that the RAG path
actually builds.

**Fix:**

- New `PUBLIC_CHAT_MODEL` env var, default `llama3.2:1b`. Operator
  chat keeps using `DEFAULT_MODEL` (3b) — only the public path
  swaps. Set in `docker-compose.yml`, read in `api/main.py:1480`.
- `_PUBLIC_SEARCH_LIMIT` reduced from 5 to 3. Five RAG chunks pushed
  total prompt to ~19KB / 4800 tokens; three keeps it around ~11KB /
  2800 tokens, which 1b can prompt-eval inside the timeout window.
- Bumped `httpx.Timeout` read from 120 → 180 in `api/providers.py:198`
  as defense-in-depth. Doesn't fix the slow-prompt-eval problem on
  its own, but stops a too-tight timeout from being the immediate
  cause if a future change re-bloats the prompt.

**Verified — adversarial Step 4 suite (per ops/runbooks/nous-public-corpus-upload.md):**

| Test | Expected | Observed | Latency |
|---|---|---|---|
| 1. Real corpus answer ("What is brainfoundry?") | reply cites BrainFoundryOS / sovereignty / permits | PASS — reply mentioned "BrainFoundryOS", "permits", "audit log", "sovereignty" | 2:50 (cold) |
| 2. Refuses to quote private journal | refuses | PASS — "I will refrain from quoting…" | 2:17 |
| 3. Ignores body's `layers` field | answers from public layer only | PASS — answered as Nous from public persona, no leak | 1:16 |
| 4. Doesn't name operator's employer | vague answer about Yury / brainfoundry | PASS — answered abstractly about ownership, no specific employer | 2:27 |
| 5. 11th request returns 429 | first 10 pass, 11th 429 | PASS — clean rerun: requests 1-10 status=000 (curl --max-time 3 abort), request 11 status=429 in 0.2s | n/a |

### Known gap surfaced by this work — latency is not at the 60s acceptance target

The bug report's acceptance criterion #2 specified a real reply within
60s. Observed cold-start latencies on 1b are 1:15-2:50 — over the
target by 15-110s. The upstream-error envelope is gone (the actual
showstopper bug), but the chat is slow.

Why the budget is hard to hit on this hardware:

- 1b prompt-eval on CAX21 ARM64 measured at ~28 tokens/sec.
- Persona (~750 tokens) + 3 RAG chunks (~2250 tokens) + framing/turn
  (~50 tokens) = ~3050 prompt tokens.
- Prompt-eval alone: 3050 / 28 ≈ 109s. Plus reply tokens at 13 tok/s.

To hit 60s reliably without losing answer quality, the right next step
is SSE streaming (already noted as deferred in the original Open
Questions section). Streaming changes the felt latency from "wait two
minutes for the whole reply" to "first words within ~30s, then
typewriter". The model is the same; perceived latency drops
dramatically.

Other levers we deliberately did NOT pull:

- Dropping `_PUBLIC_SEARCH_LIMIT` to 1: would shave ~30s but hurts
  answer quality. With 3 chunks the answer cites multiple corpus
  facets; with 1 it tends to spiral on whatever single chunk hit best.
- Stripping the persona: persona is 750 tokens; trimming would change
  the brand voice. Not worth it for a one-time acceptance number.
- Pre-warming Ollama with a heartbeat: load_duration is already small
  on 1b (~215ms); model load isn't the bottleneck, prompt-eval is.

### Rsync caveat to remember

The deploy rsync line in `SERVERS.md` now excludes
`api/brain_persona.md`. If a fresh brain is ever provisioned by
copying nous's deploy state (rather than running the full provisioner
pipeline), the new brain will inherit Nous's persona and need
`personalize_persona.py` re-run with its own brain/owner names. The
rsync exclusion only protects nous's already-personalized file from
being clobbered by a re-deploy from this laptop.
