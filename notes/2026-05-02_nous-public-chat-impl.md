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
