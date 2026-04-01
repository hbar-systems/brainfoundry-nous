#!/usr/bin/env bash
set -euo pipefail

# --- EDIT THIS IF YOUR PATH CHANGES ---
PROJECT_ROOT="/Users/hbar/dev/hbar-brain-slm"
API_URL="http://127.0.0.1:8000"
MODEL="llama3.2:1b"

echo "🔌 Checking external drive..."
if [[ ! -d "$PROJECT_ROOT" ]]; then
  echo "❌ Project directory not found at $PROJECT_ROOT"; exit 1
fi

echo "📁 Switching to project..."
cd "$PROJECT_ROOT" || { echo "❌ Missing project folder: $PROJECT_ROOT"; exit 1; }

# 1) venv
if [[ -d ".venv" ]]; then
  echo "🐍 Activating venv..."
  source .venv/bin/activate
else
  echo "🐍 Creating fresh venv..."
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install --upgrade pip setuptools wheel
  # minimal deps you use from scripts
  python -m pip install -r requirements.txt || true
  python -m pip install pyyaml
fi

# 2) docker stack
echo "🐳 Starting Docker stack..."
docker compose up -d

# 3) ensure Ollama model exists
echo "🧰 Ensuring Ollama model: ${MODEL}"
if ! docker compose exec -T ollama ollama list | grep -q "${MODEL}"; then
  docker compose exec -T ollama ollama pull "${MODEL}"
fi

# 4) wait for API
echo "⏳ Waiting for API health..."
for i in {1..60}; do
  if curl -fsS "$API_URL/health" >/dev/null; then
    break
  fi
  sleep 1
done

echo "✅ Health:"
curl -sS "$API_URL/health" || true

# 5) quick visibility
echo "📄 Sample search (VQE):"
curl -sS -X POST "$API_URL/documents/search" \
  -H 'Content-Type: application/json' \
  -d '{"query":"VQE","limit":3}' || true

echo "🧠 physics_qm → docs:"
sqlite3 extensions/brain/semantic.db \
  "SELECT d.document_name FROM document_entities d JOIN entities e ON e.id=d.entity_id WHERE e.name='physics_qm';" || true

echo
echo "➡️ Ready."
echo "   Ask with tags:  python3 scripts/ask.py \"[topic:quantum] Summarize VQE in 3 bullets.\""
echo "   Tasks extract:  python3 scripts/ask.py \"[todo,project:hbar-brain] Extract tasks.\""
