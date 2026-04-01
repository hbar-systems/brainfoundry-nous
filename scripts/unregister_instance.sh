#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <brain_id> [compose_file]"
  echo "example: $0 hbar.brain.gamma docker-compose.instantiator.yml"
  exit 1
fi

BRAIN_ID="$1"
COMPOSE_FILE="${2:-docker-compose.instantiator.yml}"

LAST="${BRAIN_ID##*.}"
SVC="api_${LAST//[^a-zA-Z0-9_]/_}"

python3 - <<PY
import yaml
from pathlib import Path

p = Path("$COMPOSE_FILE")
doc = yaml.safe_load(p.read_text())
svc = "$SVC"

services = doc.get("services", {}) or {}
if svc not in services:
    raise SystemExit(f"ERROR: service {svc} not found in {p}")

del services[svc]
doc["services"] = services

p.write_text(yaml.safe_dump(doc, sort_keys=False))
print(f"OK: unregistered $BRAIN_ID (service {svc}) from {p}")
PY
