#!/usr/bin/env bash
set -euo pipefail

# Resolve project root as "parent of scripts/", unless PROJECT_ROOT is set.
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)}"
cd "$PROJECT_ROOT"

# 1) Start (or resume) the stack
docker compose up -d

# 2) Ensure the Ollama model exists (no-op if already present)
MODEL="${OLLAMA_MODEL:-llama3.2:3b}"
if ! docker compose exec -T ollama ollama list | grep -q "$MODEL"; then
  echo "→ Pulling model: $MODEL"
  docker compose exec -T ollama ollama pull "$MODEL"
fi

# 3) Wait for API health
echo "→ Waiting for API health…"
for i in {1..30}; do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null; then
    echo "✅ API is healthy."
    echo "UI: http://localhost:3010"
    exit 0
  fi
  sleep 1
done

echo "⚠️  API did not become healthy in time (30s). Check 'docker compose logs -f api'."
exit 1
