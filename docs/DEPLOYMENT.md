# Deployment Guide

This guide covers deploying brainfoundry-nous on a VPS or dedicated server for personal production use.

## Prerequisites

- Docker and Docker Compose v2+
- At least 4 GB RAM (8 GB recommended for larger local models)
- 20+ GB disk space (Ollama models are large)
- A domain name with DNS pointing to your server (optional but recommended)

## Quick Deploy

```bash
git clone https://github.com/hbar-systems/brainfoundry-nous.git my-brain
cd my-brain
cp .env.example .env
nano .env          # fill in all required fields
docker compose up -d --build
```

## Environment Configuration

All configuration lives in `.env`. The key fields:

| Variable | Required | Description |
|---|---|---|
| `BRAIN_ID` | Yes | Unique identifier for this node (e.g. `my-brain-01`) |
| `BRAIN_NAME` | Yes | Display name |
| `BRAIN_OWNER` | Yes | Your name |
| `BRAIN_API_KEY` | Yes | API key for all authenticated endpoints |
| `BRAIN_IDENTITY_SECRET` | Yes | Secret for signing identity tokens |
| `NODEOS_SIGNING_SECRET` | Yes | Secret for BrainKernel governance kernel |
| `BRAIN_PRIVATE_KEY` | Yes | ED25519 private key for federation |
| `BRAIN_PUBLIC_KEY` | Yes | ED25519 public key (published via /identity) |
| `POSTGRES_PASSWORD` | Yes | Change from default before production |
| `BRAIN_ENV` | Yes | Set to `prod` to enforce secret validation on startup |

### Generating secrets

```bash
# API key and signing secrets
openssl rand -hex 32   # run 3 times, use for BRAIN_API_KEY, BRAIN_IDENTITY_SECRET, NODEOS_SIGNING_SECRET

# ED25519 federation keypair
python scripts/generate_keypair.py
```

## Port Layout

| Port | Service | Binding |
|---|---|---|
| `3010` | Console UI | `0.0.0.0` |
| `8010` | Brain API | `0.0.0.0` |
| `127.0.0.1:8001` | BrainKernel | localhost only |
| `127.0.0.1:54332` | PostgreSQL | localhost only |
| `127.0.0.1:11435` | Ollama | localhost only |

**Port 3010 (Console UI) proxies the API server-side using `BRAIN_API_KEY`. Anyone who can reach port 3010 can use the brain.** Protect it with a firewall rule, VPN, or Tailscale — do not expose it to the public internet without access control.

**Port 8010 (API) is protected by `BRAIN_API_KEY`.** Place it behind a reverse proxy (nginx/Caddy) with TLS before exposing it.

## Reverse Proxy (nginx example)

```nginx
server {
    listen 443 ssl;
    server_name brain.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/brain.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/brain.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8010/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Setting BRAIN_ENV=prod

When `BRAIN_ENV=prod`, the API refuses to start if:
- `BRAIN_API_KEY` is missing
- `BRAIN_IDENTITY_SECRET` is missing or set to the dev default
- `DEV_ENABLE_MEMORY_APPEND` is set

This is a safety net. Always use `prod` in production.

## Pulling a Local Model

```bash
docker compose exec ollama ollama pull llama3.2:3b
```

Set `OLLAMA_MODEL=llama3.2:3b` in `.env` and restart the API container.

## Updating

```bash
sudo chown -R $USER:$USER ~/brain 2>/dev/null   # see note below
git pull origin main
docker compose up -d --build
```

**Why the `chown` first.** The api container runs as root and bind-mounts the
repo (`BRAIN_HOST_DIR`); its git ops (the Update-tab "latest on origin" fetch,
`/admin/update`) and a past root checkout can leave `.git` and working-tree files
root-owned. A host `git pull` then fails *silently* (`cannot open .git/FETCH_HEAD:
Permission denied` / `unable to unlink old …`) and `docker compose up --build`
quietly rebuilds the **old** code. The chown-first is harmless when ownership is
already correct and guarantees the pull lands. The brain also **self-heals** at
boot — `repair_repo_ownership()` (`api/git_ownership.py`) re-owns the repo to the
host operator on every container start — but that runs *after* your pull, so lead
with the chown.

**Persona / settings survive rebuilds.** The personalized persona, API keys,
integration credentials, and tasks live in the `api_runtime` named volume
(`/app/runtime`), not in the image — `docker compose up --build` preserves them.

## Troubleshooting

**"I deployed but nothing changed."** Almost always the root-owned-repo issue
above — your `git pull` silently failed. Run the `chown` line and pull again;
confirm with `git rev-parse --short HEAD` matching `origin/main`.

**API container fails to start**: Check `docker compose logs api`. Most common cause is a missing required secret in `.env`.

**NodeOS unreachable**: The API fails closed — all inference and state mutations are blocked until NodeOS is healthy. Check `docker compose logs nodeos`.

**Embedding model not loaded**: The model loads on first use. Check `/ready` endpoint. The `/health` endpoint shows model status.

**Database errors**: Check that PostgreSQL is running (`docker compose ps postgres`) and that `POSTGRES_PASSWORD` matches the running container. If recreating from scratch, bring the volume down first: `docker compose down -v`.
