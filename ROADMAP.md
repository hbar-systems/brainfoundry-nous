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
3. **`nous` CLI** (week 2–3) — `nous chat`, `nous upload --layer X`, `nous stats`. Published origin points at the clean URLs. nous-brain (renamed from nous-brain-01) is the canonical public test target.

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

- [ ] **Index layer tag in vector store** — v0.8 stores layer in
      `document_embeddings.metadata->>'layer'` (JSONB extraction, unindexed).
      Fine at current corpus size (low-thousands of chunks per brain); becomes
      a hot path once brains hold tens of thousands of chunks or layer filters
      are used in every query. Fix: add a generated column
      `layer TEXT GENERATED ALWAYS AS (metadata->>'layer') STORED` + btree
      index, or promote layer to a first-class column. Schedule when any brain
      crosses ~20k chunks or p95 latency on layer-filtered `/chat/rag` exceeds
      ~300ms.

## v0.9 — appearance + identity

- [ ] **Skins / appearance section** in Settings — palette presets (warm
      academic / cool minimal / hbar-default), font pairing toggle, accent
      colour, optional brain symbol override (already partially via
      `NEXT_PUBLIC_BRAIN_SYMBOL`). Surfaces taste, not just function.
- [ ] **Identity card** — single shareable URL/PDF: brain name, public key,
      federation endpoint, owner contact. The thing you hand someone when
      saying "here's my brain".

## v1.0 — first real federation workflows

- [ ] Federation permits / memory-share flow — first real workflow on top of
      the assertion primitive.
- [ ] hbar-brain rebuilt from this template (dogfood pass, validates that
      the template is genuinely usable by its own creator).

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
