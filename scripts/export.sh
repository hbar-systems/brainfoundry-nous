#!/bin/bash
#
# export.sh — the one command: export this brain to a single .tar.gz.
#
# Runs api/export.py inside the api container (it has the database and the
# runtime volume) and writes the archive next to you on the host. No secrets
# inside: no .env, no keys, no settings sidecar (see docs/EXPORT.md).
#
# USAGE (on the brain host)
#   scripts/export.sh                  # -> ./brain-export-<id>-<UTC>.tar.gz
#   scripts/export.sh /path/to/dir     # -> archive in that directory
#
# Restore: docs/EXPORT.md (db + persona via scripts/import_brain.py; apps
# re-installed from apps/installed.json; md copied back).
set -euo pipefail
BRAIN_DIR="${BRAIN_DIR:-/home/hbar/brain}"
DEST="${1:-.}"
mkdir -p "$DEST"
cd "$BRAIN_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BRAIN_ID="$(grep -E '^BRAIN_ID=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -c 'a-z0-9._-\n' '-')"
OUT="$DEST/brain-export-${BRAIN_ID:-brain}-${STAMP}.tar.gz"
docker compose exec -T api python -m api.export --stdout > "$OUT"
echo "export: $OUT ($(wc -c < "$OUT" | tr -d ' ') bytes)"
