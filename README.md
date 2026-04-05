# brainfoundry-node

The canonical brain node runtime for [BrainFoundryOS](https://brainfoundry.ai).

Clone this to run your own sovereign personal brain.

---

## What this is

A full-stack AI brain node. Runs on your server, connects to the models you choose,
stores your knowledge. You own it. Nobody else has access.

**Stack:**
- FastAPI — chat, RAG, embeddings, identity
- CognitiveOS — governance kernel (loop permits, PROPOSE/CONFIRM)
- PostgreSQL + pgvector — vector memory
- Ollama — local model fallback (always available, no API key needed)
- Next.js — console UI (dashboard, chat, knowledge, kernel)
- Redis — rate limiting
- Docker Compose — everything runs in containers

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

```bash
nano api/brain_persona.md
```

Replace the `[CONFIGURE: ...]` placeholders with who you are, what you work on,
your projects, your thinking style. This is what makes the brain yours.
The recommended baseline section at the bottom is advisory — delete it if you want.

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

## Get your brain built for you

**White-glove personal service:**
Email [hello@hbar.systems](mailto:hello@hbar.systems) — subject line `brainfoundry`.
BrainFoundry reviews your request and crafts your brain personally.

---

## Protocol

This node implements the BrainFoundryOS node contract.
See `docs/brainfoundry/NODE_CONTRACT.md` for the full spec.

The protocol is open. The brain is yours.

---

## License

AGPL-3.0 — see [LICENSE](LICENSE).

Run it, modify it, self-host it freely. If you run a modified version as a service, you must release your modifications under the same license.
