# brainfoundry-nous — roadmap

Created: 2026-04-14
Owner: BrainFoundry
Scope: public template repo. Items here are what we want the brain UX/runtime
to grow into, not promises with dates.

---

## v0.7.x — sovereignty unblocks (in-progress)

- [x] Customer SSH keypair delivered at provision time (provisioner repo, 2026-04-14).
- [x] Bidirectional federation handshake over public HTTPS (Part A + Part B, 2026-04-14).
- [x] Single `/settings` page in the console — Keys, Models, Memory layers,
      Security & Federation, CLI, Advanced Kernel (2026-04-14).
- [x] First-login tour modal (2026-04-14).
- [x] BYOK providers expanded: Anthropic, OpenAI, Gemini, xAI, Groq, OpenRouter,
      Together.ai, Mistral (2026-04-14).
- [x] Sidecar settings persistence (`/app/runtime/settings.json` on `api_runtime`
      named volume) — keys + active model + memory layers survive rebuilds.
- [ ] Clean public URLs (drop `-brain-01` from customer-facing hostnames).
- [ ] Provisioner: proper CI/CD (replace rsync) — blocked on org Deploy Keys policy.

## Sequencing (load-bearing — do not reorder without reason)

1. **v0.8 memory layers** (this week) — layer-scoped upload, layer-filtered retrieval, per-layer stats. Everything downstream depends on this primitive being real.
2. **URL rename** (week 2) — drop `-brain-01` from customer-facing hostnames *before* the CLI ships a public origin config. Federation is keyed on endpoints, so this is done carefully, in-place, with DNS + Caddy updates coordinated.
3. **`hbar` CLI** (week 2–3) — `hbar chat`, `hbar upload --layer X`, `hbar stats`. One binary, endpoint-configurable per brain (nous, your own, a friend's). nous-brain is the canonical public test target; `hbar --init` scaffolds `.hbar/brain.toml` for any user pointing at their own instance.

Rationale: a CLI before layers would be a thinner wrapper on `/chat`. A CLI published against `*-brain-01.brainfoundry.ai` would bake a URL we intend to drop into every customer's shell history.

## Testing-ring timeline (internal → private → community)

- **Week 1 (now → +7d):** Internal dogfood only. Me on yury-brain + one fresh template-rebuilt brain. No external users.
- **Week 2–3 (+7 → +21d):** 2–3 close friends, Model 3 white-glove. Surface the install/first-chat papercuts the author can't see. Each tester onboarded live, not self-serve.
- **Week 4 (+21 → +28d):** Widen to 5–10 friends/colleagues via Model 2B provisioner. Tests the self-serve path end-to-end (email, SSH delivery, first-login tour).
- **Week 5+ (+28d onward):** Open to brainfoundry community / public signal. Only after two rounds of private feedback have closed obvious gaps.

Anti-pattern to avoid: tapping the community before the private ring on the theory that "more eyes = faster feedback." Public eyes see a broken thing and leave; private eyes see a broken thing and tell you.

Caveat: timeline assumes current rate holds and no major legal/contract interruption. The employment contract question logged in FOCUS.md, if it activates, eats a week.

## v0.8 — memory layers become real + observability

**Memory layers currently = labels only.** You define them in Settings but
uploads are not yet scoped to them. Fixing this is the top v0.8 item.

- [ ] **Layer-scoped upload** — in Knowledge (or from inside a layer row in
      Settings), drop files into a specific layer. Each chunk gets the
      layer name as a tag in the vector store.
- [ ] **Layer-filtered retrieval** — RAG queries can narrow to one or more
      layers, so "what did I say about X in my `thinking` layer" works.
- [ ] **Per-layer stats** — doc count, last-ingested timestamp, shown in
      the Settings layer row.

Also in v0.8 (observability + trust surface):

Deferred from the v0.7.x Brain UX v2 pass because each one needs its own
backend (event store, pollable endpoints, etc). These are the natural next
beats once the settings surface exists.

- [ ] **Federation activity log** — table of inbound + outbound assertions:
      timestamp, peer brain_id, audience, verified yes/no, claims summary.
      Surfaces in Settings → Security & Federation. Backed by a small
      append-only log on disk (`/app/runtime/federation.log` or sqlite).
- [ ] **Recent auth events** — SSH login attempts (parsed from journald) +
      console login attempts. Same panel. "Last 30 days, last 10 events."
      Helps the user notice they're being probed.
- [ ] **Test federation button** — in Settings → Security & Federation, paste
      a peer endpoint, click "ping". Brain self-issues an assertion to that
      peer and shows the verified response (or the error). Removes the
      manual `curl` ceremony from the federation handshake.
- [ ] **Per-key "test" button** — next to each saved provider key, a button
      that does a 1-token completion against that provider. Confirms the key
      works without burning a chat session.

## v0.8.x — layer-store performance (follow-on)

- [x] **Index layer tag in vector store** (2026-04-16) — partial btree index
      `document_embeddings_layer_idx ON document_embeddings ((metadata->>'layer'))
      WHERE metadata->>'layer' IS NOT NULL`. Added to `vector-db/init.sql` for
      new brains and applied on boot via a fail-soft startup hook in
      `api/main.py` for existing brains. Partial keeps the index small since
      most chunks are unscoped. Revisit if layer cardinality grows past a few
      dozen and a generated column or first-class `layer` column becomes
      cheaper than the JSONB expression.

## v0.9 — appearance + identity

- [ ] **Skins / appearance section** in Settings — palette presets (warm
      academic / cool minimal / hbar-default), font pairing toggle, accent
      colour, optional brain symbol override (already partially via
      `NEXT_PUBLIC_BRAIN_SYMBOL`). Surfaces taste, not just function.
- [ ] **Identity card** — single shareable URL/PDF: brain name, public key,
      federation endpoint, owner contact. The thing you hand someone when
      saying "here's my brain".
- [ ] **In-UI update banner + one-click upgrade** — today brain owners update
      via SSH (`git pull && docker compose up -d --build`). Fine for Week-2
      Model-3 white-glove onboarding; becomes a real gap at Week-4 Model-2B
      self-serve scale. Landing this means detecting new `main` via a
      runtime check, surfacing a banner in Settings, and running the
      rebuild from inside the container (likely via a small host-side
      agent or Caddy exec, since the API container can't `docker compose`
      itself). Blocks nothing earlier; schedule before first public widening.

## v1.0 — first real federation workflows

- [ ] Federation permits / memory-share flow — first real workflow on top of
      the assertion primitive.
- [ ] hbar-brain rebuilt from this template (dogfood pass, validates that
      the template is genuinely usable by its own creator).

## v1.1+ — tool registry (external capabilities)

Added: 2026-04-15. Status: parked, post-federation.

The brain currently has no formal way to call out to the world. Tools are the surface that gives it hands, eyes, and reach — but the protocol contract has to come before any specific tool, otherwise every tool reinvents permitting and provenance.

**Why parked:** federation (v1.0) is the harder primitive and unlocks more. Tools are easy to bolt on once the registry shape is decided; doing them earlier means designing the registry against an immature governance surface.

**Scope when picked up:**

- [ ] **Tool registry primitive** — `tools/local.toml` schema (name, endpoint, permit-class: read/write/network, budget, provenance-tag format) + `POST /v1/tools/:name/invoke` contract. One registry pattern, every tool slots in.
- [ ] **Permit classes** — read-only tools (web search, fetch, calendar read) auto-permit with audit log. Write tools (mail send, blog post, federation call) gated by PROPOSE/CONFIRM. Hard monthly budget cap per tool.
- [ ] **Provenance tagging** — every tool result entering memory tagged with source, tool name, timestamp, session id. Required for commercial use — must be able to answer "where did this claim come from."
- [ ] **First reference tool: web search** — Brave Search API (commercial-clean, soloist-friendly: paid tier ~$3/1k queries, no contract). Auto-permitted, audit-logged, budget-capped.
- [ ] **Tool tier rollout** (sequence, not all at once):
  - Tier 1 (hands): web search + fetch, file read/write in `.hbar/`, sandboxed shell, git read
  - Tier 2 (senses): calendar read, mail read, RSS, screenshot+OCR, audio in
  - Tier 3 (reach): mail send, post to own systems via API, federation call, code-exec sandbox
  - Tier 4 (domain): music (Spotify/Bandcamp/Ableton), finance, health bridges

**Sequencing principle:** read-only first, write second, autonomous third. Most personal-AI failure modes come from giving write access before the governance layer is real. The tool registry exists *because* PROPOSE/CONFIRM exists — it's the gate every Tier 3+ tool passes through.

**Provider posture (commercial use):** API keys held under owner's personal billing, not company alias — keeps tools portable across entity structures. Self-hosted scrapers (SearXNG etc.) skipped: ops burden too high for a soloist.

---

## How brain owners update their own brain

The whole point of this template is that **the customer owns the deploy**.
Every brain provisioned by BrainFoundry is just a clone of this repo running
under `docker compose`. Anyone with SSH access (which every customer has —
see provisioner's customer-SSH delivery) can:

```
cd /home/hbar/brain
git pull origin main
docker compose up -d --build api ui
```

That's the upgrade story. No vendor lock-in, no forced upgrades, no telemetry
phoning home. If a customer wants to **pin** to a specific commit instead of
following `main`, they can:

```
git fetch
git checkout <commit-sha>
docker compose up -d --build api ui
```

If they want to **fork** and run their own changes, that's also fine — it's
their brain. The federation protocol is the only thing that needs to stay
compatible across forks.

This means the public repo serves three populations at once:
1. BrainFoundry-provisioned customers (default `main`).
2. Self-hosters who run `docker compose up` from scratch on their own VPS.
3. Forkers who diverge entirely.

Roadmap items above must keep all three working. Backwards-incompatible
changes get called out in `CHANGELOG.md` with an upgrade note.
