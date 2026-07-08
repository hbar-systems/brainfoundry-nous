# BrainFoundry — private, self-hosted AI with real memory

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.9.1-informational.svg)](VERSION)
[![Stack](https://img.shields.io/badge/stack-FastAPI%20%2B%20Next.js%20%2B%20pgvector-success.svg)](#stack)

**Run your own AI brain on your own server.** It remembers your documents (RAG
over Postgres/pgvector), talks to whatever models you choose (local Ollama or
your own API keys), and keeps everything on *your* box — no vendor sees your
data, nothing phones home. It's for anyone who wants a private, personal AI with
real memory instead of a chat box that forgets.

Governance, an append-only audit log, and optional federation with other brains
are built in too — but you don't need any of that to run it. Start with the
Quickstart; the deeper model is in [Trust model](#trust-model-v09--read-this-before-you-run-it-in-production) below.

> **The names, once:** **BrainFoundry** is the product · a single install is **a
> brain** · **nous** is our public demo brain · **BrainKernel** is the governance
> kernel (called `nodeos` in the containers and env vars) · **BrainFoundryOS** is
> the federation protocol brains speak to each other. More in [docs/NAMING.md](docs/NAMING.md).

<!-- TODO(demo-gif) operator: record a ~10-15s silent screencap of nous at
     https://nous.brainfoundry.ai showing (1) a question + streamed answer,
     (2) the Knowledge tab with ingested docs, (3) the Kernel/audit tab. Export
     an optimized loop, ≤5 MB, 1280×800 (or 2:1 aspect), 12-15 fps, to
     docs/assets/demo.gif, then replace the line below with:
       ![BrainFoundry demo](docs/assets/demo.gif) -->
_See a brain live right now: **[nous.brainfoundry.ai](https://nous.brainfoundry.ai)** — a demo GIF lands here shortly._

## Quickstart

One command on a fresh Linux box with Docker. It generates dev secrets into
`.env`, builds the stack, pulls the local model, and waits until the brain
answers — no cloud key required:

```bash
git clone https://github.com/hbar-systems/brainfoundry-nous.git my-brain
cd my-brain
./scripts/start_docker.sh
```

Then open the console at `http://localhost:3010` and start chatting — it replies
from a local Ollama model with no API key set. Ingest your own documents with
`python scripts/ingest_folder.py /path/to/docs`.

> Prefer to configure by hand first? Copy `.env.example` to `.env` and set the
> four secrets (`openssl rand -hex 32` each → `BRAIN_API_KEY`,
> `BRAIN_IDENTITY_SECRET`, `NODEOS_SIGNING_SECRET`, `NODEOS_INTERNAL_KEY`), then
> run the same script — it leaves an existing `.env` untouched. Full walk-through
> (including the persona file that makes the brain *yours*) is in
> [Spin up your own brain](#spin-up-your-own-brain) below.

**Links:** [brainfoundry.ai](https://brainfoundry.ai) ·
[hbar.systems](https://hbar.systems) ·
live public demo: **[nous.brainfoundry.ai](https://nous.brainfoundry.ai)** — a real BrainFoundry brain you can chat with right now.

---

## What this is

A full-stack AI brain you run on your own server. It connects to the models you
choose, stores your knowledge, and answers with memory of it. You own it. Nobody
else has access. (Product name: **BrainFoundry**; the governance kernel is
**BrainKernel**, named `nodeos` in the container and env vars — see
[docs/NAMING.md](docs/NAMING.md).)

### Trust model (v0.9) — read this before you run it in production

This repo is the **reference implementation**, not a polished appliance.
BrainKernel is the governance kernel (named `nodeos` in the container and env vars).
BrainFoundryOS is the overall platform and federation protocol; each node runs a
BrainKernel (internally `nodeos`) that handles persona, memory routing, and decision-making.
The guarantees it gives you today are:

- **You are the only tenant.** Designed for single-owner, self-hosted use. Not
  multi-tenant. Not a hosted service.
- **BrainKernel gates the chat loop with caller-bound permits.** Every
  `/chat/completions` and `/chat/rag` request must present both a valid
  `permit_id` and its HMAC-signed `permit_token`. The token is issued once,
  from `POST /v1/loops/request`, and is bound to the agent that requested
  it — a leaked `permit_id` cannot be replayed without the token.
- **Brain-layer mutations go through NodeOS.** `remember`, `forget`, and
  `audit.clear` are routed through a propose → approve → execute flow
  against the NodeOS authority kernel before any database write or audit
  wipe lands. Fail-closed if NodeOS is unreachable.
- **BrainKernel is internal-only.** NodeOS binds to `127.0.0.1:8001`, has no
  browser proxy, and requires `X-Internal-Key` on all state-mutating routes.
- **External actions are preview-then-execute.** `git_push` and similar
  side-effects go through a strict branch allowlist and a preview step before
  anything lands.
- **Append-only audit log.** Every kernel command and every model call is
  recorded.

Known scope limits (v0.9): `context.set` / `context.clear` mutate an in-process
dict that resets on container restart and is not yet routed through NodeOS.
Bulk offline ingestion via `scripts/ingest_folder.py` writes directly to the
database for the single-owner bootstrap case. See `SECURITY.md` and Section
8 of `docs/SELF_HOSTING_GUIDE.md` for the full honest scope.


## Stack
- FastAPI — chat, RAG, embeddings, identity
- BrainKernel — governance kernel (loop permits, mutation gate, append-only audit)
- PostgreSQL + pgvector — vector memory
- Ollama — local model fallback (always available, no API key needed)
- Next.js — console UI (dashboard, chat, knowledge, kernel)
- Redis — rate limiting
- Docker Compose — everything runs in containers

**Connect your world (Integrations tab):** read-only, untrusted-by-default, mostly
no-OAuth — **email** (IMAP app password), **calendar** (iCal link), **Telegram**
(chat your brain from your phone), **Deep Research** (cited multi-source web
synthesis), **Tasks/reminders** (due → Telegram ping), **MCP** servers (any tool),
and **Drive** (OAuth). Setup steps in [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md).

---

## Models — Bring Your Own Key

Configure any combination. Only providers with a key set appear in the model selector.
Ollama is always available with no key required.

| Provider | Key | Example models |
|----------|-----|----------------|
| Anthropic | `ANTHROPIC_API_KEY` | claude-sonnet-4-6, claude-opus-4-6 |
| OpenAI | `OPENAI_API_KEY` | gpt-4o, gpt-4o-mini, o3-mini |
| Google | `GOOGLE_API_KEY` | gemini-2.0-flash, gemini-1.5-pro |
| xAI | `XAI_API_KEY` | grok-2, grok-beta |
| Groq | `GROQ_API_KEY` | llama-3.3-70b, mixtral-8x7b (free tier) |
| OpenRouter | `OPENROUTER_API_KEY` | deepseek, qwen, mistral, and more |
| Ollama (local) | none | mistral:7b, llama3.2, qwen2.5, phi3 |

---

## Spin up your own brain

### What you need

- A Linux server (Hetzner CAX21 recommended — ~€7/mo)
- Docker + Docker Compose
- A domain (optional but recommended)
- At least one API key, or Ollama for fully local

### 1. Clone

```bash
git clone https://github.com/hbar-systems/brainfoundry-nous.git my-brain
cd my-brain
```

### 2. Configure

```bash
cp .env.example .env
nano .env
```

Fill in at minimum:
- `BRAIN_ID` — unique name (e.g. `alice-brain-01`)
- `BRAIN_NAME` — display name (e.g. `Alice's Brain`)
- `BRAIN_SYMBOL` — a Unicode symbol shown in the nav (pick anything)
- `BRAIN_OWNER` — your name
- At least one API key, or leave all empty to use Ollama only
- All secret fields — generate each with `openssl rand -hex 32`

### 3. Configure your persona

The tracked template is `api/brain_persona.template.md`. Copy it to the
gitignored `api/brain_persona.local.md` — the runtime prefers that file, and it
survives `git pull` / `git reset --hard` upgrades untouched:

```bash
cp api/brain_persona.template.md api/brain_persona.local.md
nano api/brain_persona.local.md
```

Replace the `[CONFIGURE: ...]` placeholders with who you are, what you work on,
your projects, your thinking style. This is what makes the brain yours.
The recommended baseline section at the bottom is advisory — delete it if you want.
(You can also edit the persona later from the console UI.)

### 4. Start

```bash
docker compose up -d
```

### 5. Pull a local model (optional)

```bash
docker compose exec ollama ollama pull mistral:7b
# also available: llama3.2, qwen2.5:7b, phi3, deepseek-r1:7b
```

### 6. Ingest your documents

Organize documents into folders and ingest:

```bash
python scripts/ingest_folder.py /path/to/your/docs
```

This is what makes the brain know you. The more you ingest, the more personal it becomes.

**RAG tier folders (optional):** The brain prioritizes documents from certain folders during search.
Default folder names (configurable via env vars):

| Folder | Env var | Priority | Purpose |
|--------|---------|----------|---------|
| `identity/` | `RAG_TIER1` | Highest (always 2) | Who you are, core context |
| `thinking/` | `RAG_TIER2A` | High (always 1) | Notes, active reasoning |
| `projects/` | `RAG_TIER2B` | High (always 1) | Current work, in-progress |
| `writing/` | `RAG_TIER2C` | High (always 1) | Essays, published work |
| everything else | — | Similarity search | General corpus |

You can use any folder names — set `RAG_TIER1`, `RAG_TIER2A/B/C` in `.env`.
Or skip the structure entirely and let the similarity search find everything.

### 7. Access

- Console UI: `http://your-server:3010`
- API: `http://your-server:8010` (OpenAPI docs disabled — see `docs/DEPLOYMENT.md`)

> **Security note:** Port 3010 proxies the API server-side using your `BRAIN_API_KEY`. Do not expose it to the public internet without a firewall rule, VPN, or reverse proxy with authentication. Anyone who can reach port 3010 can use the brain.

Add a domain with Caddy for HTTPS — see `docs/DEPLOYMENT.md`.

---

## Production deployment checklist

Before exposing your brain to the internet:

```bash
# 1. Generate all secrets (run once, save output to .env)
openssl rand -hex 32   # → BRAIN_API_KEY
openssl rand -hex 32   # → BRAIN_IDENTITY_SECRET
openssl rand -hex 32   # → NODEOS_SIGNING_SECRET
openssl rand -hex 32   # → NODEOS_INTERNAL_KEY   (service-to-service auth between api ↔ nodeos)

# 2. Generate federation keypair (required for /identity endpoint)
python scripts/generate_keypair.py
# Copy BRAIN_PRIVATE_KEY and BRAIN_PUBLIC_KEY output into .env

# 3. Set non-default postgres credentials in .env
POSTGRES_USER=your_db_user
POSTGRES_PASSWORD=your_strong_password

# 4. Set BRAIN_ENV=prod in .env — enables startup secret enforcement

# 5. Build and start
docker compose up -d --build
```

**Security notes:**
- PostgreSQL binds to `127.0.0.1` only — never exposed to the public internet
- Never commit `.env` — it is gitignored
- The `GITHUB_TOKEN` approach (git credentials in container) is for development convenience only; for production use SSH deploy keys instead

---

## Public chat surface (optional)

If your brain is the public demo node (e.g. `nous.brainfoundry.ai`) and you
want strangers to be able to chat with it without exposing the operator
console, deploy the split-surface layout. The repo ships a minimal Next.js
chat app at `apps/public-chat/` (port 3020) and a brain endpoint
`POST /v1/public/chat` that takes no API key.

### Three-vhost layout

```
https://your-domain/             → :3020  (public chat, no auth, IP rate-limited)
https://console.your-domain/     → :3010  (operator console, basicauth)
https://api.your-domain/         → :8010  (brain API, X-API-Key)
```

The `console` and `api` subdomains keep their existing auth — only the bare
domain is publicly reachable. The Caddyfile blocks for the public-facing
vhosts must include `trusted_proxies private_ranges` so Caddy overwrites
client-supplied `X-Forwarded-For` with the real client IP. The brain reads
the *last hop* of XFF for per-IP rate limiting; without `trusted_proxies`,
strangers can rotate fake XFF values to defeat the limit.

### Public RAG namespace

`/v1/public/chat` hard-codes `layers=["public"]`. Only documents tagged
`metadata.layer = "public"` are visible — every other document is
default-deny. Seed the public corpus by uploading docs to the brain with
`metadata.layer="public"` set; the operator console upload UI does **not**
expose this layer (intentional — out of scope for v0). Recommended seed
docs ship in `docs/public/`.

### Rate limit

Defaults: **10 requests / 60 seconds / IP**. Configure via env:

```
PUBLIC_RATE_LIMIT_MAX=10
PUBLIC_RATE_LIMIT_WINDOW=60
```

The limiter is Redis-backed and fail-closed (Redis down → 429, not 200).

### Auth model

The public chat path **does not use `BRAIN_API_KEY`**. Auth is rate-limit-only.
The relay (`apps/public-chat/pages/api/chat.js`) does not forward any
`Authorization` header. The endpoint is intentionally unauthenticated and
intentionally read-only — no permits, no DB writes, no session persistence.
Operator console and the rest of the brain API still require `X-API-Key`
exactly as before.

### Persona

Public chat injects `api/brain_persona_nous.md` as its system prompt instead
of `api/brain_persona.md` (the operator's personal persona). The personal
persona must never leak onto a public surface — the two are deliberately
separate files.

### Operational note for CLI users

If you're running the brain at a domain that previously exposed the API on
the bare hostname, switching to the three-vhost layout is a **breaking
change**: any CLI tool whose config still points at the bare domain will
hit the public chat app and 404 on `/v1/*` paths. Move CLI defaults to
`api.your-domain` before flipping the Caddyfile.

---

## Upgrading your brain (you own the deploy)

Your brain is a `git clone` of this repo. There is no vendor upgrade channel,
no forced updates, no telemetry. You choose when to pull and what to pull.

**Track `main` (latest stable):**
```bash
ssh <you>@<your-brain-host>
cd /path/to/your/brain      # wherever you cloned it
git pull origin main
docker compose up -d --build api ui
```

**Pin to a specific commit** (reproducible, audit-friendly):
```bash
git fetch
git checkout <commit-sha>
docker compose up -d --build api ui
```

**Fork and run your own changes:** also fine. It's your brain. The only
contract that must stay compatible across forks is the federation protocol
(`/identity` + `POST /v1/federation/assertion`) so other brains can still
verify you.

This means three populations run this repo side-by-side and all three work:

1. **BrainFoundry-provisioned customers** — default, track `main`.
2. **Self-hosters** — `git clone` + `docker compose up` on any VPS.
3. **Forkers** — diverge however you want.

Backwards-incompatible changes are always called out in `CHANGELOG.md` with
an upgrade note. See `ROADMAP.md` for what's coming and what's deferred.

---

## Get your brain built for you

**White-glove personal service:**
Email [hello@hbar.systems](mailto:hello@hbar.systems) — subject line `brainfoundry`.
BrainFoundry reviews your request and crafts your brain personally.

---

## Federation trust — substrate floor (Layer 1)

A federating peer cannot accept assertions from this brain until the brain's
substrate-depth signal clears the configured thresholds. The substrate floor
is a federation-membership precondition — it does not gate ingestion, only
cross-brain trust. Design rationale:
[discussions/2026-05-01_federation-trust-mechanisms.md](https://github.com/hbar-systems/hbar.world/blob/main/discussions/2026-05-01_federation-trust-mechanisms.md).

**Endpoints:**

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET`  | `/v1/federation/substrate-depth`  | none   | Public signed depth signal (5-min cache). |
| `POST` | `/v1/federation/assertion`     | pinned-peer ED25519 | Adds a substrate-floor gate after sig + replay checks. |

**Default thresholds (env-tunable):**

| Env var | Default | Meaning |
|---------|---------|---------|
| `FEDERATION_SUBSTRATE_MIN_ARTIFACTS`     | 50  | Minimum total attestation rows. |
| `FEDERATION_SUBSTRATE_MIN_FIRST_PERSON`  | 25  | Minimum non-`derived` rows. |
| `FEDERATION_SUBSTRATE_MIN_DIVERSITY`     | 2   | Minimum distinct `source_type` values. |
| `FEDERATION_SUBSTRATE_MIN_AGE_DAYS`      | 7   | Minimum (now − oldest_artifact_ts).days. |
| `SUBSTRATE_DEPTH_CACHE_SECONDS`          | 300 | Server-side cache of the signed payload. |
| `SUBSTRATE_PEER_CACHE_SECONDS`           | 300 | Per-peer fetch+gate cache. |
| `FEDERATION_SUBSTRATE_GATE`              | on  | Set `off` to disable the gate (endpoint still served). |

These are the prompt's starting points, untested. Operators may need to seed
test brains rather than weaken the floor — see the discussions doc.

**Backfill:** brains with pre-existing RAG corpus need attestations generated
for the historical chunks. Use `scripts/substrate_backfill.py` (DRY-RUN
default, pass `--commit` to apply). Read the script docstring before running.

**Failure response shape** (HTTP 403):

```json
{
  "ok": false,
  "code": "substrate_floor_not_met",
  "details": {
    "artifact_count": { "got": 12, "required": 50 },
    "first_person_count": { "got": 4, "required": 25 }
  }
}
```

Other codes: `signature_invalid`, `substrate_depth_unreachable`. Tests:
`pytest tests/test_substrate.py -v`.

---

## Protocol

This node implements the BrainFoundryOS node contract.
See `docs/brainfoundry/NODE_CONTRACT.md` for the full spec.

The protocol is open. The brain is yours.

---

## License

AGPL-3.0 — see [LICENSE](LICENSE).

Run it, modify it, self-host it freely. If you run a modified version as a service, you must release your modifications under the same license.
