#!/usr/bin/env bash
set -euo pipefail

# ── BrainFoundry one-command bootstrap ────────────────────────────────────────
# The paste-and-run path for a fresh clone. On a clean VM this:
#   1. creates .env from .env.example if it is missing, and fills the four
#      required secrets with `openssl rand -hex 32` so the api container does
#      NOT crash-loop on an empty BRAIN_IDENTITY_SECRET (main.py startup guard);
#   2. builds + starts the stack;
#   3. pulls the local Ollama models the brain answers with, so "start chatting"
#      returns a response with no cloud key;
#   4. waits for the API to report healthy.
#
# Idempotent: an existing .env is never overwritten, and models already present
# are not re-pulled. Safe to re-run.
#
# This produces a DEV brain (BRAIN_ENV=dev). Before exposing it to the public
# internet, follow the "Production deployment checklist" in README.md — set
# BRAIN_ENV=prod, a strong POSTGRES_PASSWORD, and a federation keypair.

# Resolve project root as "parent of scripts/", unless PROJECT_ROOT is set.
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)}"
cd "$PROJECT_ROOT"

# Local models to ensure exist. Operator chat uses llama3.2:3b (DEFAULT_MODEL);
# the public-chat surface uses llama3.2:1b (PUBLIC_CHAT_MODEL). Override with
# e.g. MODELS="llama3.2:3b" to pull fewer.
MODELS="${MODELS:-llama3.2:3b llama3.2:1b}"

# ── 0) Ensure .env exists with the required secrets filled ───────────────────
gen_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    # Fallback if openssl is somehow absent (should not happen on a normal VM).
    head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

# Set KEY=<generated-secret> in .env, but ONLY when the key is currently blank
# (KEY= with nothing after it). Never clobbers a value the operator already set.
fill_secret_if_blank() {
  local key="$1" file="$2"
  if grep -qE "^${key}=$" "$file"; then
    local val
    val="$(gen_secret)"
    # Portable in-place edit (works with both BSD and GNU sed via a temp file).
    local tmp
    tmp="$(mktemp)"
    awk -v k="$key" -v v="$val" 'BEGIN{FS=OFS="="} $0==k"=" {print k"="v; next} {print}' "$file" > "$tmp"
    mv "$tmp" "$file"
    echo "   • generated $key"
  fi
}

if [ ! -f .env ]; then
  echo "→ No .env found — creating one from .env.example and generating dev secrets…"
  cp .env.example .env
  fill_secret_if_blank BRAIN_API_KEY .env
  fill_secret_if_blank BRAIN_IDENTITY_SECRET .env
  fill_secret_if_blank NODEOS_SIGNING_SECRET .env
  fill_secret_if_blank NODEOS_INTERNAL_KEY .env
  echo "   .env created (BRAIN_ENV=dev). Edit it to set your BRAIN_ID / persona / API keys."
else
  echo "→ .env already exists — leaving it untouched."
fi

# ── 1) Build + start (or resume) the stack ───────────────────────────────────
echo "→ Building and starting the stack…"
docker compose up -d --build

# ── 2) Ensure the local models exist (no-op if already present) ──────────────
for MODEL in $MODELS; do
  if docker compose exec -T ollama ollama list 2>/dev/null | grep -q "$MODEL"; then
    echo "→ Model already present: $MODEL"
  else
    echo "→ Pulling model: $MODEL (first run only — this can take a few minutes)…"
    docker compose exec -T ollama ollama pull "$MODEL"
  fi
done

# ── 3) Wait for API health ───────────────────────────────────────────────────
echo "→ Waiting for API health…"
for i in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then
    echo "✅ API is healthy."
    echo
    echo "   Console UI:  http://localhost:3010"
    echo "   Brain API:   http://localhost:8010"
    echo "   Open the console and start chatting. Ingest docs with:"
    echo "     python scripts/ingest_folder.py /path/to/docs"
    exit 0
  fi
  sleep 1
done

echo "⚠️  API did not become healthy within 90s. Check: docker compose logs -f api"
exit 1
