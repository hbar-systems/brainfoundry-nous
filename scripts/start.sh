#!/usr/bin/env bash
set -euo pipefail

# Resolve project root as "parent of scripts/", unless PROJECT_ROOT is set.
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)}"
cd "$PROJECT_ROOT"

MODEL="${OLLAMA_MODEL:-llama3.2:1b}"

# 1) Start the stack
echo "→ Starting Docker stack..."
docker compose up -d

# 2) Ensure Ollama model exists
if ! docker compose exec -T ollama ollama list | grep -q "$MODEL"; then
  echo "→ Pulling model: $MODEL"
  docker compose exec -T ollama ollama pull "$MODEL"
fi

# 3) Wait for API health
API_URL="${API_BASE:-http://127.0.0.1:8010}"
echo "→ Waiting for API health at $API_URL..."
for i in {1..60}; do
  if curl -fsS "$API_URL/health" >/dev/null 2>&1; then
    echo "✅ API is healthy."
    echo "   Console UI: http://localhost:3010"
    echo "   API:        $API_URL"
    echo "   API docs:   $API_URL/docs"
    exit 0
  fi
  sleep 1
done

echo "⚠️  API did not become healthy in 60s. Check: docker compose logs -f api"
exit 1
