#!/bin/bash
#
# restore_brain.sh — bring a brain back from a backup_brain.sh artifact.
#
# The restore is the half people skip. This is the proof the backup is real:
# a fresh box + one artifact dir + this script = the brain is back.
#
# WHAT IT DOES (destructive — it overwrites live state):
#   1. Replays db.sql.gz into Postgres   (the dump is --clean --if-exists, so it
#      drops and recreates every table — existing data is replaced).
#   2. Untars runtime.tar.gz back into the api container (settings, persona,
#      peers, audit logs, brain-apps).
#   3. Restarts the api container so it reloads settings.json + the persona.
#
# PRE-REQUISITES (see docs/RESTORE.md for the fresh-box runbook):
#   - The brain repo is checked out at BRAIN_DIR with a valid .env. Secrets are
#     NOT in the artifact by design — you supply .env separately.
#   - `docker compose up -d` has been run; postgres + api are up.
#
# USAGE
#   scripts/restore_brain.sh <artifact_dir>        # prompts before overwriting
#   scripts/restore_brain.sh <artifact_dir> --force
#
# ENV OVERRIDES
#   BRAIN_DIR   brain checkout / compose dir   (default /home/hbar/brain)

set -euo pipefail

BRAIN_DIR="${BRAIN_DIR:-/home/hbar/brain}"
ARTIFACT=""
FORCE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --force|-y) FORCE=1; shift ;;
        -h|--help) sed -n '2,38p' "$0"; exit 0 ;;
        -*) echo "✗ unknown argument: $1" >&2; exit 2 ;;
        *) ARTIFACT="$1"; shift ;;
    esac
done

COMPOSE="docker compose -f ${BRAIN_DIR}/docker-compose.yml"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8010/health}"

log() { echo "$(date -u +%H:%M:%S) $*"; }
fail() { echo "✗ $*" >&2; exit 1; }

# ── Validate the artifact ────────────────────────────────────────────────────
[ -n "$ARTIFACT" ] || fail "usage: restore_brain.sh <artifact_dir> [--force]"
[ -d "$ARTIFACT" ] || fail "artifact dir not found: ${ARTIFACT}"
[ -f "${ARTIFACT}/db.sql.gz" ] || fail "missing db.sql.gz in ${ARTIFACT}"
[ -f "${ARTIFACT}/runtime.tar.gz" ] || fail "missing runtime.tar.gz in ${ARTIFACT}"

command -v docker >/dev/null 2>&1 || fail "docker not found on PATH"
[ -f "${BRAIN_DIR}/docker-compose.yml" ] || fail "no docker-compose.yml at ${BRAIN_DIR}"

# ── Containers must be up to receive the restore ─────────────────────────────
$COMPOSE ps postgres 2>/dev/null | grep -q "Up\|running" \
    || fail "postgres is not running. Run: cd ${BRAIN_DIR} && docker compose up -d"
$COMPOSE ps api 2>/dev/null | grep -q "Up\|running" \
    || fail "api is not running. Run: cd ${BRAIN_DIR} && docker compose up -d"

PGUSER="$($COMPOSE exec -T postgres printenv POSTGRES_USER 2>/dev/null | tr -d '\r' || true)"
PGDB="$($COMPOSE exec -T postgres printenv POSTGRES_DB 2>/dev/null | tr -d '\r' || true)"
PGUSER="${PGUSER:-postgres}"
PGDB="${PGDB:-llm_db}"

echo ""
echo "==> Restore plan"
[ -f "${ARTIFACT}/manifest.txt" ] && sed 's/^/    /' "${ARTIFACT}/manifest.txt"
echo ""
echo "    This will OVERWRITE the live database '${PGDB}' and runtime state"
echo "    in the running api container at ${BRAIN_DIR}."
echo ""

if [ "$FORCE" -ne 1 ]; then
    printf "Type 'restore' to proceed: "
    read -r answer
    [ "$answer" = "restore" ] || fail "aborted (no changes made)"
fi

# ── 1. Restore Postgres ──────────────────────────────────────────────────────
log "==> restoring database ${PGDB}..."
set -o pipefail
gunzip -c "${ARTIFACT}/db.sql.gz" \
    | $COMPOSE exec -T postgres psql -v ON_ERROR_STOP=1 -U "$PGUSER" -d "$PGDB" >/dev/null
restore_status=${PIPESTATUS[1]}
[ "$restore_status" -eq 0 ] || fail "psql restore failed (exit ${restore_status})"
log "    database restored"

# ── 2. Restore runtime state ─────────────────────────────────────────────────
log "==> restoring runtime state into api container..."
$COMPOSE exec -T api tar xzf - -C / < "${ARTIFACT}/runtime.tar.gz"
log "    runtime state restored"

# ── 3. Restart api to reload settings + persona ──────────────────────────────
log "==> restarting api..."
$COMPOSE restart api >/dev/null

# ── 4. Health check ──────────────────────────────────────────────────────────
log "==> waiting for brain to come back online..."
sleep 5
for _ in $(seq 1 30); do
    if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
        echo ""
        echo "✓ Restore complete. Brain is healthy."
        ROWS="$($COMPOSE exec -T postgres psql -U "$PGUSER" -d "$PGDB" -tAc \
            'SELECT count(*) FROM document_embeddings' 2>/dev/null | tr -d '\r' || echo '?')"
        echo "  document_embeddings rows: ${ROWS}"
        exit 0
    fi
    sleep 2
done

echo ""
echo "✗ Brain did not return to healthy state after restore."
echo "  Check: cd ${BRAIN_DIR} && docker compose logs api"
exit 1
