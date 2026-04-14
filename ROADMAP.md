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

## v0.8 — observability + trust surface

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
