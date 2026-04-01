#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <brain_id> <host_port> [compose_file]"
  echo "example: $0 hbar.brain.beta 8130 docker-compose.instantiator.yml"
  exit 1
fi

BRAIN_ID="$1"
HOST_PORT="$2"

# Check if host port already in use
if ss -ltn | awk '{print $4}' | grep -q ":${HOST_PORT}$"; then
  echo "ERROR: host port ${HOST_PORT} is already in use"
  exit 1
fi

COMPOSE_FILE="${3:-docker-compose.instantiator.yml}"

LAST="${BRAIN_ID##*.}"
SVC="api_${LAST//[^a-zA-Z0-9_]/_}"

INST_DIR="instances/${BRAIN_ID}"

if [[ ! -d "$INST_DIR" ]]; then
  echo "ERROR: $INST_DIR not found. Run ./scripts/mold_new_brain.sh $BRAIN_ID first."
  exit 1
fi

# ensure runtime env exists
if [[ ! -f "$INST_DIR/.env" ]]; then
  cp "$INST_DIR/.env.example" "$INST_DIR/.env"
fi

# ensure identity secret exists once
if ! grep -q '^HBAR_IDENTITY_SECRET=' "$INST_DIR/.env"; then
  echo 'HBAR_IDENTITY_SECRET=dev-secret-please-change' >> "$INST_DIR/.env"
fi


# Ensure required external network exists
if ! docker network ls --format '{{.Name}}' | grep -q '^hbar-brain_llm-network$'; then
  echo "ERROR: required Docker network 'hbar-brain_llm-network' not found. Start base stack first."
  exit 1
fi

python3 - <<PY
import yaml
from pathlib import Path

p = Path("$COMPOSE_FILE")
doc = yaml.safe_load(p.read_text())
doc.setdefault("services", {})
doc.setdefault("networks", {})

svc_name = "$SVC"
if svc_name in doc["services"]:
    raise SystemExit(f"ERROR: service {svc_name} already exists in {p}")

doc["services"][svc_name] = {
    "build": {"context": ".", "dockerfile": "api/Dockerfile"},
    "restart": "unless-stopped",
    "env_file": [f"./$INST_DIR/.env"],
    "networks": ["llm-network"],
    "ports": [f"{int("$HOST_PORT")}:8000"],
    "environment": {
        "DATABASE_URL": "postgresql+psycopg://postgres:postgres@postgres:5432/postgres",
        "REDIS_URL": "redis://redis:6379/0",
        "OLLAMA_BASE_URL": "http://ollama:11434",
        "NODEOS_BASE_URL": "http://nodeos:8001",
        "BRAIN_IDENTITY_PATH": "/app/api/brain_identity.yaml",
    },
    "volumes": [
        f"./$INST_DIR/api/brain_identity.yaml:/app/api/brain_identity.yaml:ro,Z",
        f"./$INST_DIR/ops:/app/ops:Z",
        f"./$INST_DIR/data:/app/data:Z",
    ],
}

p.write_text(yaml.safe_dump(doc, sort_keys=False))
print(f"OK: registered $BRAIN_ID as service {svc_name} on port $HOST_PORT in {p}")
PY
