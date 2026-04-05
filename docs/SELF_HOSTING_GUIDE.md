# BrainFoundryOS — Self-Hosting Guide

A complete reference for running your own sovereign brain node.

---

## Table of contents

1. [What you're running](#1-what-youre-running)
2. [Prerequisites](#2-prerequisites)
3. [Installation](#3-installation)
4. [Configuration reference](#4-configuration-reference)
5. [Persona — making it yours](#5-persona--making-it-yours)
6. [Knowledge ingestion (RAG)](#6-knowledge-ingestion-rag)
7. [Models](#7-models)
8. [CognitiveOS — the governance kernel](#8-cognitiveos--the-governance-kernel)
9. [Federation](#9-federation)
10. [Production hardening](#10-production-hardening)
11. [Connecting external systems](#11-connecting-external-systems)
12. [Maintenance](#12-maintenance)
13. [Security model](#13-security-model)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. What you're running

A brain node is a personal, sovereign AI system. It runs on your own server.
Nobody else has access. You control the data, the models, and the behavior.

**Services started by `docker compose up`:**

| Service | Port | Purpose |
|---------|------|---------|
| `api` | 8010 | Main brain API — chat, RAG, identity, kernel |
| `nodeos` | 8001 (internal) | CognitiveOS governance kernel |
| `ui` | 3010 | Console — dashboard, chat, knowledge, kernel |
| `postgres` | 127.0.0.1:54332 | Vector memory (pgvector) |
| `ollama` | 11434 (internal) | Local model inference |
| `redis` | 6379 (internal) | Kernel rate limiting |

Only ports 8010, 3010, and optionally Ollama (if you want to call it directly) need to be accessible. PostgreSQL, Redis, and NodeOS are internal-only.

---

## 2. Prerequisites

**Server:**
- Linux (Ubuntu 22.04 / Debian 12 recommended)
- 2+ CPU cores, 4GB+ RAM minimum (8GB recommended if running local models)
- 20GB+ disk
- Hetzner CAX21 (ARM, ~€7/mo) or CX22 (x86, ~€4/mo) work well

**Software:**
- Docker 24+ and Docker Compose v2
- Git
- Python 3.11+ (for scripts — not required inside containers)

**Domain (optional but recommended):**
- Required for HTTPS and a stable address for federation

---

## 3. Installation

### Step 1 — Clone

```bash
git clone https://github.com/hbar-systems/brainfoundry-nous.git my-brain
cd my-brain
```

### Step 2 — Configure

```bash
cp .env.example .env
```

Edit `.env` — see [Section 4](#4-configuration-reference) for all variables.

### Step 3 — Write your persona

```bash
nano api/brain_persona.md
```

Replace the `[CONFIGURE: ...]` placeholders. See [Section 5](#5-persona--making-it-yours).

### Step 4 — Generate secrets

```bash
# Run these one at a time and paste each output into .env
openssl rand -hex 32   # → BRAIN_API_KEY
openssl rand -hex 32   # → BRAIN_IDENTITY_SECRET
openssl rand -hex 32   # → NODEOS_SIGNING_SECRET

# Federation keypair (required for /identity endpoint)
python scripts/generate_keypair.py
# Paste BRAIN_PRIVATE_KEY and BRAIN_PUBLIC_KEY into .env
```

### Step 5 — Start

```bash
docker compose up -d --build
```

### Step 6 — Pull a local model

```bash
docker compose exec ollama ollama pull llama3.2
# Other options: mistral:7b, qwen2.5:7b, phi3, deepseek-r1:7b, gemma3
```

### Step 7 — Ingest your documents

```bash
python scripts/ingest_folder.py /path/to/your/notes
```

### Step 8 — Access

- Console UI: `http://your-server:3010`
- API: `http://your-server:8010` (OpenAPI/Swagger docs are disabled; see docs/DEPLOYMENT.md for all routes)

Add a domain + HTTPS via Caddy — see `docs/DEPLOYMENT.md`.

---

## 4. Configuration reference

Copy `.env.example` to `.env`. All variables are optional unless marked **required**.

### Identity

| Variable | Required | Description |
|----------|----------|-------------|
| `BRAIN_ID` | Yes | Unique node identifier (e.g. `alice-brain-01`) |
| `BRAIN_NAME` | Yes | Display name shown in UI |
| `BRAIN_SYMBOL` | No | Unicode symbol in nav (e.g. `⊕`) |
| `BRAIN_OWNER` | Yes | Your name (shown in identity endpoint) |

### Secrets (required for production)

| Variable | Description |
|----------|-------------|
| `BRAIN_API_KEY` | API authentication key for all private endpoints |
| `BRAIN_IDENTITY_SECRET` | Signs identity assertions and permits |
| `NODEOS_SIGNING_SECRET` | Signs CognitiveOS governance tokens |
| `NODEOS_INTERNAL_KEY` | Service-to-service key; `api` → `nodeos` |
| `BRAIN_PRIVATE_KEY` | ED25519 private key for federation |
| `BRAIN_PUBLIC_KEY` | ED25519 public key (published via `/identity`) |

All secrets: generate with `openssl rand -hex 32`. Keypair: use `python scripts/generate_keypair.py`.

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | `postgres` | Hostname (container name in Docker) |
| `POSTGRES_PORT` | `5432` | Internal port |
| `POSTGRES_DB` | `llm_db` | Database name |
| `POSTGRES_USER` | `postgres` | **Change in production** |
| `POSTGRES_PASSWORD` | `postgres` | **Change in production** |

### Models

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `llama3.2:3b` | Default local model |
| `DEFAULT_MODEL` | `llama3.2:3b` | Default model for chat |
| `ANTHROPIC_API_KEY` | — | Enables Claude models |
| `OPENAI_API_KEY` | — | Enables GPT models |
| `GOOGLE_API_KEY` | — | Enables Gemini models |
| `XAI_API_KEY` | — | Enables Grok models |
| `GROQ_API_KEY` | — | Enables Groq (free tier available) |
| `OPENROUTER_API_KEY` | — | Enables OpenRouter (many models) |

Only set keys for providers you want to use. Ollama works without any key.

### Document processing

| Variable | Default | Description |
|----------|---------|-------------|
| `CHUNK_SIZE` | `750` | Token chunk size for ingestion |
| `CHUNK_OVERLAP` | `150` | Overlap between chunks |
| `DOCS_DIR_HOST` | — | Host path to your documents |

### RAG tier folders

The brain gives priority to documents in named folders during search. The folder names are configurable.

| Variable | Default | Priority | Intended purpose |
|----------|---------|----------|-----------------|
| `RAG_TIER1` | `identity` | Highest — always 2 results | Who you are, core context |
| `RAG_TIER2A` | `thinking` | High — always 1 result | Notes, active reasoning |
| `RAG_TIER2B` | `projects` | High — always 1 result | Current work |
| `RAG_TIER2C` | `writing` | High — always 1 result | Essays, published work |

Everything else in your corpus is searched by similarity. You can ignore the tier structure entirely — it only matters if you organize your documents into folders.

### Network

| Variable | Default | Description |
|----------|---------|-------------|
| `API_BASE` | `http://localhost:8010` | API base URL |
| `CORS_ORIGINS` | — | Additional allowed origins (comma-separated) |
| `BRAIN_ENV` | `dev` | Set to `prod` to enable startup secret enforcement |

---

## 5. Persona — making it yours

The persona file (`api/brain_persona.md`) is the most important customization.
It defines how the brain understands and represents you.

Edit it before first start:

```bash
nano api/brain_persona.md
```

Replace every `[CONFIGURE: ...]` block with your own content. The structure:

```
## Who I am
[Your name, profession, what you do]

## What I work on
[Current projects, domains, responsibilities]

## How I think
[Your reasoning style, frameworks you use, how you approach problems]

## My context
[Timezone, tools, collaborators, environment]
```

This file is never committed to git if you fork the repo and keep your own branch. It lives entirely on your server.

You can update it at any time — restart the API container to reload:

```bash
docker compose restart api
```

---

## 6. Knowledge ingestion (RAG)

Your brain learns from your documents. Ingest any folder of text files, PDFs, or markdown.

### Basic ingestion

```bash
python scripts/ingest_folder.py /path/to/folder
```

The script recursively processes all `.txt`, `.md`, `.pdf` files.

### Organizing for tier-weighted search

If you want the brain to prioritize certain documents (persona, notes, current work) over the general corpus, use the tier folder structure:

```
my-docs/
  identity/      ← highest priority (who you are, your CV, your principles)
  thinking/      ← high priority (active notes, reasoning docs)
  projects/      ← high priority (current work docs)
  writing/       ← high priority (essays, blog posts)
  research/      ← general corpus (papers, references)
  archive/       ← general corpus (old notes)
```

Then ingest the top-level folder:

```bash
python scripts/ingest_folder.py my-docs
```

The tier folder names match what you set in `RAG_TIER1`, `RAG_TIER2A/B/C` (defaults: `identity`, `thinking`, `projects`, `writing`). Rename folders to match your own structure and update the env vars.

### Re-ingesting after changes

You can re-run ingestion at any time. Documents with the same path/name are updated in-place.

### What to ingest

The more the brain knows about you, the more personal it becomes. Good sources:

- Your notes (Obsidian, Notion exports, plain text)
- Documents you've written (essays, reports, specs)
- Reading notes and highlights
- Your CV / bio
- Project documentation

Avoid ingesting sensitive credentials, financial records, or anything you wouldn't want persisted in a database. The database is local to your server, but treat it as you would any persistent store.

---

## 7. Models

### Bring Your Own Key (BYOK)

The brain routes requests by model name prefix. Set only the API keys for providers you use.

```
claude-*         → Anthropic (ANTHROPIC_API_KEY)
gpt-*, o1-*      → OpenAI (OPENAI_API_KEY)
gemini-*         → Google (GOOGLE_API_KEY)
grok-*           → xAI (XAI_API_KEY)
groq/*             → Groq (GROQ_API_KEY)   e.g. groq/llama-3.3-70b-versatile
openrouter/*     → OpenRouter (OPENROUTER_API_KEY)
(anything else)  → Ollama (local, no key required)
```

The model selector in the UI only shows providers with a key configured.

### Local models (Ollama)

Ollama is always running and requires no API key. Good local models:

```bash
docker compose exec ollama ollama pull llama3.2        # fast, small
docker compose exec ollama ollama pull llama3.2:3b     # slightly larger
docker compose exec ollama ollama pull qwen2.5:7b      # multilingual, capable
docker compose exec ollama ollama pull mistral:7b      # reliable general purpose
docker compose exec ollama ollama pull deepseek-r1:7b  # strong reasoning
docker compose exec ollama ollama pull gemma3          # Google, Apache 2.0
```

List available models:

```bash
docker compose exec ollama ollama list
```

---

## 8. CognitiveOS — the governance kernel

CognitiveOS is the governance service running in the `nodeos` container. It
provides loop permits, memory/action proposals, and an append-only audit log
for the brain's chat completion path.

> **Scope (v0.5).** CognitiveOS is an authoritative store for permits,
> proposals, and audit events — not yet a universal executor. It gates the
> chat inference flow (every `/chat/completions` call verifies a permit) and
> records memory proposals. It does **not** yet intercept every direct
> write to the brain's document store; custom brain commands such as
> `remember` and `forget` currently execute against the database directly
> and are logged in the API audit file rather than mediated through a
> NodeOS proposal. Full mediation of those paths is on the v0.6 roadmap.
> Treat CognitiveOS today as a strong authority for the chat loop and an
> honest audit log everywhere else, not as a hermetic gate on all writes.

### Core concepts

**Loop permit** — A timed authorization bound to an agent, node, and loop
type. The brain API verifies the permit is `ACTIVE` and not expired on every
chat completion; requests without a valid permit are refused.

```
REQUEST → ACTIVE → (expires) | (revoked) → INACTIVE
```

**Memory proposal** — A pending record submitted to NodeOS describing a
proposed long-term memory write. Proposals are stored with `PENDING` status
until explicitly decided (`APPROVED` / `REJECTED`). The v0.5 chat flow records
selected outputs as proposals; approval and replay into the vector store is a
manual operator step.

**Action proposal** — The analogous record for external side effects such as
`git_push`. NodeOS enforces a strict branch allowlist and a
preview-before-execute contract for the actions it does run.

### Internal-only access

NodeOS binds only to `127.0.0.1:8001` on the host and is never exposed to
browsers. All state-mutating NodeOS endpoints require an `X-Internal-Key`
header matching `NODEOS_INTERNAL_KEY`. The brain API forwards this header
automatically; other callers on the Docker network cannot forge requests
without the secret.

### Using the kernel from the API

The brain's chat interface automatically requests a loop permit for each
session via an internal route. For inspection and manual governance you can
use:

```
POST /v1/brain/command         — PROPOSE / CONFIRM read-only commands via the brain API
GET  /v1/audit                 — read the audit log
```

The raw NodeOS endpoints (`/v1/loops/request`, `/v1/memory/propose`, …) are
reachable only from inside the Docker network with a valid `X-Internal-Key`.

### Kernel rate limits

Kernel commands are rate-limited per client. Defaults: 30 requests per 60
seconds. Adjust with `KERNEL_RATE_LIMIT_MAX` and `KERNEL_RATE_LIMIT_WINDOW`
in `.env`.

---

## 9. Federation

Federation allows your brain to verify assertions from other brain nodes, and for other nodes to verify yours. It uses ED25519 asymmetric signing.

### Setup

```bash
python scripts/generate_keypair.py
```

Copy the output into `.env`:

```
BRAIN_PRIVATE_KEY=<private key — never share>
BRAIN_PUBLIC_KEY=<public key — safe to publish>
```

Your public key is exposed at `GET /identity` so other brains can verify your tokens.

### What federation enables (v1)

- Cross-brain identity verification
- Assertions signed by your brain are verifiable by any node with your public key
- Foundation for future cross-brain memory sharing and collaborative workflows

Federation is optional for personal use. It is required if you want to be addressable by other BrainFoundryOS nodes.

---

## 10. Production hardening

Before exposing your brain to the internet:

### Required

1. **Set all secrets** (see Section 4)
2. **Set `BRAIN_ENV=prod`** — startup will refuse if secrets are missing or default
3. **Change Postgres credentials** — `POSTGRES_USER` and `POSTGRES_PASSWORD`
4. **Set up a reverse proxy with TLS** — see `docs/DEPLOYMENT.md`

### Recommended

5. **Use SSH deploy keys instead of GITHUB_TOKEN** for git operations in the nodeos container. See `nodeos/Dockerfile` for instructions.
6. **Restrict `CORS_ORIGINS`** to only your actual frontend domain.
7. **Run `docker compose up` from a systemd service** so the brain restarts automatically after server reboot.

### On Docker secrets and API keys

API keys (Anthropic, OpenAI, etc.) are passed as Docker environment variables. Anyone with access to the Docker socket can read them via `docker inspect`. For most personal self-hosted deployments this is acceptable — the Docker socket is only accessible to root and docker-group users on the server.

For higher-security deployments (shared servers, corporate environments), consider using Docker Secrets or a vault (e.g. HashiCorp Vault, Infisical) and mounting secrets at runtime instead.

---

## 11. Connecting external systems

Any system can connect to the brain via the authenticated API.

### Authentication

All non-public endpoints require `X-API-Key` or `Authorization: Bearer <key>`.

```bash
# Test the connection
curl -H "X-API-Key: your-key" http://your-server:8010/health
```

### Chat via API

```bash
curl -X POST http://your-server:8010/chat/completions \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What am I working on?"}], "model": "llama3.2:3b", "permit_id": "<permit_id>"}'
```

### Public endpoints (no auth required)

These are intentionally unauthenticated — they are needed for federation and service discovery:

- `GET /health` — liveness check
- `GET /ready` — readiness check  
- `GET /identity` — node identity and public key (federation)
- `GET /capabilities` — what this node supports

---

## 12. Maintenance

### Restart a service

```bash
docker compose restart api
docker compose restart nodeos
docker compose restart ui
```

### View logs

```bash
docker compose logs -f api
docker compose logs -f nodeos
docker compose logs --tail=100 api
```

### Update

```bash
git pull
docker compose up -d --build
```

### Database backup

```bash
docker compose exec postgres pg_dump -U postgres llm_db > backup_$(date +%Y%m%d).sql
```

### Reset the database

```bash
docker compose down -v   # destroys all data
docker compose up -d --build
```

---

## 13. Security model

This brain node is designed for **personal self-hosted use** by a single owner.

**What is protected:**
- All private endpoints require API key authentication
- PostgreSQL never binds to a public interface (127.0.0.1 only)
- CognitiveOS requires a valid loop permit on every chat completion
- NodeOS state-mutating endpoints require `X-Internal-Key` (service-to-service auth)
- Startup refuses if secrets are missing or default (in prod mode)
- CognitiveOS kernel request bodies are size-limited

**What is not protected (and why):**
- `/identity`, `/ready`, `/capabilities` are unauthenticated — required for federation protocol; they expose only public information
- TLS is not built into the containers — use a reverse proxy (Caddy, nginx) in front. See `docs/DEPLOYMENT.md`
- API keys are passed as Docker environment variables — visible to anyone with Docker socket access on the host

**Threat model:**
This system assumes you control your server. It is not designed for multi-tenant deployments, shared hosting, or environments where the Docker socket is accessible to untrusted parties.

---

## 14. Troubleshooting

### Brain won't start

```bash
docker compose logs api
docker compose logs nodeos
```

Common causes:
- Missing or default secrets with `BRAIN_ENV=prod` — the startup check will print exactly which secret is missing
- Postgres not ready yet — wait 10 seconds and retry; the API retries on startup

### Chat returns 500

The API key is wrong, or the selected model is not available. Check:

```bash
docker compose logs api --tail=50
```

### Ollama model not found

```bash
docker compose exec ollama ollama list
docker compose exec ollama ollama pull <model-name>
```

### Documents not appearing in search

Ingestion may have failed silently. Check:

```bash
python scripts/ingest_folder.py /your/folder
```

Also verify the database has embeddings:

```bash
docker compose exec postgres psql -U postgres -d llm_db -c "SELECT COUNT(*) FROM document_embeddings;"
```

### Kernel permit errors

Loop permits expire. If you see `403 Permit expired`, request a new permit via `POST /v1/loops/request`.

### Port conflicts

Default ports are 8010 (API), 3010 (UI), 54332 (Postgres, localhost only).
Change any of these in `docker-compose.yml` if they conflict with existing services.
