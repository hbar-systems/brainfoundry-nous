#!/usr/bin/env bash
set -euo pipefail

# Molder v0.1
# Creates a new governed brain instance directory with:
# - identity yaml
# - .env template
# - docker compose overlay (ports + names + volumes)
#
# Usage:
#   ./scripts/mold_new_brain.sh <brain_id> [out_dir]
#
# Example:
#   ./scripts/mold_new_brain.sh hbar.brain.demo instances/hbar.brain.demo

BRAND="hbar.systems"
BRAIN_ID="${1:-}"
OUT_DIR="${2:-}"

if [[ -z "${BRAIN_ID}" ]]; then
  echo "Usage: $0 <brain_id> [out_dir]"
  exit 2
fi

if [[ -z "${OUT_DIR}" ]]; then
  OUT_DIR="instances/${BRAIN_ID}"
fi

mkdir -p "${OUT_DIR}/api" "${OUT_DIR}/ui" "${OUT_DIR}/ops" "${OUT_DIR}/data"

STAMP_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---- identity ----
cat > "${OUT_DIR}/api/brain_identity.yaml" <<YAML
brain_id: ${BRAIN_ID}
display_name: ${BRAIN_ID}
lineage: ${BRAND}
domain: authority
role: operator_node
model: llama3.2:1b
tags:
  - authority
  - nodeos
  - operator
stamped_at: ${STAMP_TS}
YAML

# ---- env template ----
cat > "${OUT_DIR}/.env.example" <<ENV
# ${BRAIN_ID} — stamped by molder at ${STAMP_TS}

# REQUIRED in non-dev:
HBAR_ENV=dev
HBAR_IDENTITY_SECRET=dev-secret-please-change

# API exposure
API_PORT=8010
UI_PORT=3010

# Optional toggles
DEV_ENABLE_MEMORY_APPEND=1

# Dependencies (compose will provide these defaults)
NODEOS_URL=http://nodeos:8001
OLLAMA_URL=http://ollama:11434
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/postgres

# UI routing
NEXT_PUBLIC_API_URL=http://api:8000
NEXT_PUBLIC_API_BASE=http://api:8000
ENV

# ---- compose overlay ----
cat > "${OUT_DIR}/docker-compose.overlay.yml" <<YML
services:
  api:
    volumes:
      - ./api/brain_identity.yaml:/app/api/brain_identity.yaml:ro
    environment:
      - HBAR_ENV=\${HBAR_ENV:-dev}
      - HBAR_IDENTITY_SECRET=\${HBAR_IDENTITY_SECRET}
      - DEV_ENABLE_MEMORY_APPEND=\${DEV_ENABLE_MEMORY_APPEND:-0}
    ports:
      - "\${API_PORT:-8010}:8000"

  ui:
    environment:
      - NEXT_PUBLIC_API_URL=\${NEXT_PUBLIC_API_URL:-http://api:8000}
      - NEXT_PUBLIC_API_BASE=\${NEXT_PUBLIC_API_BASE:-http://api:8000}
    ports:
      - "\${UI_PORT:-3010}:3000"
YML

# ---- run instructions ----
cat > "${OUT_DIR}/README_INSTANCE.md" <<MD
# ${BRAIN_ID}

Stamped: ${STAMP_TS}

## Run

From repo root:

    cp ${OUT_DIR}/.env.example ${OUT_DIR}/.env
    docker compose -f docker-compose.dev.yml -f ${OUT_DIR}/docker-compose.overlay.yml --env-file ${OUT_DIR}/.env up -d --build

UI:
    http://127.0.0.1:\${UI_PORT}

Kernel Console:
    http://127.0.0.1:\${UI_PORT}/kernel
MD

echo "OK: stamped ${BRAIN_ID} -> ${OUT_DIR}"
