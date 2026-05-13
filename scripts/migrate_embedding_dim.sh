#!/usr/bin/env bash
# scripts/migrate_embedding_dim.sh — idempotent embedding-column dim migration.
#
# Source-of-truth fix for the 384→1024 drift introduced by 06b5691 (2026-05-10),
# which switched the default embedding model to BAAI/bge-large-en-v1.5
# (1024-dim) without updating vector-db/init.sql. Brains provisioned before
# the schema fix run vector(384) and reject 1024-dim writes with
# "expected 384 dimensions, not 1024".
#
# USAGE
#   scripts/migrate_embedding_dim.sh <ssh_host>           # report dim + rows, no change
#   scripts/migrate_embedding_dim.sh <ssh_host> --apply   # migrate if dim=384 AND rows=0
#   scripts/migrate_embedding_dim.sh <ssh_host> --force   # migrate even if rows>0 (backs up first)
#
# WHAT HAPPENS
#   - dim=1024 already: no-op (idempotent)
#   - dim=384, rows=0, --apply: DROP+ADD embedding vector(1024) + recreate ivfflat
#   - dim=384, rows>0, --force: pg_dump backup -> DROP+ADD + recreate ivfflat
#       Existing rows keep content + metadata; embedding becomes NULL until
#       re-embedded. Run the re-embed loop separately to refill from content
#       (no source-file re-upload needed since `content` survives the ALTER).
#
# ASSUMPTIONS
#   - Host runs the brainfoundry-nous compose stack at /home/hbar/brain
#   - SSH as `hbar` with $HOME/.ssh/id_ed25519_brainfoundry_automation
#     (override with $BRAINFOUNDRY_KEY)
#   - The postgres service in compose is named `postgres`

set -euo pipefail

HOST=${1:-}
shift || true
MODE=report
for arg in "$@"; do
  case "$arg" in
    --apply) MODE=apply ;;
    --force) MODE=force ;;
    *) echo "unknown flag: $arg" >&2; exit 1 ;;
  esac
done

if [[ -z "$HOST" ]]; then
  cat >&2 <<USAGE
usage: $0 <ssh_host> [--apply | --force]
  default: report dim + row count, no DB change
  --apply : migrate iff dim=384 AND rows=0 (safe pattern)
  --force : migrate even with rows>0 (pg_dump backup first)
USAGE
  exit 1
fi

KEY="${BRAINFOUNDRY_KEY:-$HOME/.ssh/id_ed25519_brainfoundry_automation}"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "hbar@${HOST}")
PSQL='docker compose -f /home/hbar/brain/docker-compose.yml exec -T postgres psql -U postgres -d llm_db'

echo "== ${HOST} =="

# atttypmod is the type modifier; for vector(N), atttypmod is N.
DIM=$("${SSH[@]}" "$PSQL -tA -c \"SELECT atttypmod FROM pg_attribute WHERE attrelid='document_embeddings'::regclass AND attname='embedding'\"" 2>/dev/null | tr -d '\r\n[:space:]')
ROWS=$("${SSH[@]}" "$PSQL -tA -c 'SELECT count(*) FROM document_embeddings'" 2>/dev/null | tr -d '\r\n[:space:]')

echo "  embedding dim : ${DIM:-unknown}"
echo "  row count     : ${ROWS:-unknown}"

if [[ "$DIM" == "1024" ]]; then
  echo "  -> already on 1024; no schema change"
  exit 0
fi
if [[ "$DIM" != "384" ]]; then
  echo "  -> unexpected dim '${DIM}'; refusing to touch" >&2
  exit 2
fi

if [[ "$MODE" == "report" ]]; then
  echo "  -> would migrate 384 -> 1024 (re-run with --apply or --force to execute)"
  exit 0
fi

if [[ "${ROWS:-0}" -gt 0 && "$MODE" != "force" ]]; then
  echo "  REFUSE: ${ROWS} rows present; re-run with --force to backup + migrate" >&2
  exit 3
fi

if [[ "${ROWS:-0}" -gt 0 ]]; then
  STAMP=$(date -u +%Y%m%dT%H%M%SZ)
  SAFE_HOST=${HOST//./_}
  BACKUP="/home/hbar/brain-backups/${SAFE_HOST}-document_embeddings-${STAMP}.sql"
  echo "  pg_dump backup -> ${BACKUP}"
  "${SSH[@]}" "mkdir -p /home/hbar/brain-backups && docker compose -f /home/hbar/brain/docker-compose.yml exec -T postgres pg_dump -U postgres -d llm_db -t document_embeddings --column-inserts > ${BACKUP} && wc -c ${BACKUP}"
fi

echo "  ALTER + recreate ivfflat..."
"${SSH[@]}" "$PSQL" <<'SQL'
ALTER TABLE document_embeddings DROP COLUMN embedding;
ALTER TABLE document_embeddings ADD COLUMN embedding vector(1024);
CREATE INDEX IF NOT EXISTS document_embeddings_embedding_idx
  ON document_embeddings USING ivfflat (embedding vector_cosine_ops);
SQL

echo "  -> migration complete"
if [[ "${ROWS:-0}" -gt 0 ]]; then
  echo "  WARN: ${ROWS} rows now have NULL embedding; run re-embed to refill (content + metadata preserved)"
fi
