#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)}"
cd "$PROJECT_ROOT"

docker compose down
docker compose up -d

# Re-check model (handles fresh ollama container)
MODEL="${OLLAMA_MODEL:-llama3.2:1b}"
if ! docker compose exec -T ollama ollama list | grep -q "$MODEL"; then
  docker compose exec -T ollama ollama pull "$MODEL"
fi

echo "→ Waiting for API health…"
for i in {1..30}; do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null; then
    echo "🔁 Docker stack restarted and API healthy."
    exit 0
  fi
  sleep 1
done

echo "⚠️  API did not become healthy (30s). See 'docker compose logs -f api'."
exit 1
