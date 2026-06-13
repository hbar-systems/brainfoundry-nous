#!/bin/bash
#
# backup_brain.sh — sovereign, local, rotating backups of a running brain.
#
# A brain holds its owner's accumulated cognition. The vector DB and a handful
# of per-brain runtime files are NOT in git and cannot be regenerated. This
# script captures both into a single restorable artifact on the OWNER's storage
# and never phones home — backups stay on the box the owner controls.
#
# WHAT IT CAPTURES (one timestamped artifact dir per run):
#   db.sql.gz       — pg_dump of the whole vector DB, gzipped. All tables,
#                     including document_embeddings (the knowledge corpus).
#   runtime.tar.gz  — the irreplaceable runtime state, tarred from inside the
#                     api container so it works regardless of whether a path is
#                     a named volume or a bind mount:
#                       /app/runtime/settings.json          (operator settings)
#                       /app/runtime/brain_persona.local.md (personalized identity)
#                       /app/runtime/federation_audit.jsonl (cross-brain calls)
#                       /app/runtime/tool_audit.jsonl       (tool-use audit)
#                       /app/data/peers.json                (introduced peers)
#                       /app/brain-apps/                     (installed apps + registry)
#                       /app/brainfoundry/audit.jsonl       (governance audit, if present)
#                       /app/api/brain_persona.local.md      (legacy persona location)
#   manifest.txt    — what/when/which-commit, file sizes, row counts.
#
# WHAT IT DELIBERATELY DOES NOT CAPTURE:
#   .env / secrets / private keys. Same rule as scripts/export_brain.py: an
#   artifact that may be copied around must be safe to hold. On a fresh-box
#   restore the operator supplies .env separately (see docs/RESTORE.md).
#
# USAGE
#   scripts/backup_brain.sh                 # a normal (daily) backup + retention
#   scripts/backup_brain.sh --pre-update    # snapshot before an update/rebuild
#   scripts/backup_brain.sh --label TEXT    # tag the manifest (e.g. a commit)
#
# ENV OVERRIDES
#   BRAIN_DIR      brain checkout / compose dir   (default /home/hbar/brain)
#   BACKUP_DIR     where artifacts land           (default /home/hbar/brain-backups)
#   DAILY_KEEP     daily artifacts to retain       (default 7)
#   WEEKLY_KEEP    weekly artifacts to retain       (default 4)
#   PREUPDATE_KEEP pre-update snapshots to retain   (default 10)
#
# SCHEDULE (host cron — simplest, sovereign; see docs/RESTORE.md):
#   15 3 * * *  /home/hbar/brain/scripts/backup_brain.sh >> /home/hbar/brain-backups/backup.log 2>&1

set -euo pipefail

BRAIN_DIR="${BRAIN_DIR:-/home/hbar/brain}"
BACKUP_DIR="${BACKUP_DIR:-/home/hbar/brain-backups}"
DAILY_KEEP="${DAILY_KEEP:-7}"
WEEKLY_KEEP="${WEEKLY_KEEP:-4}"
PREUPDATE_KEEP="${PREUPDATE_KEEP:-10}"

CATEGORY="daily"
LABEL=""
while [ $# -gt 0 ]; do
    case "$1" in
        --pre-update) CATEGORY="pre-update"; shift ;;
        --label) LABEL="${2:-}"; shift 2 ;;
        --label=*) LABEL="${1#*=}"; shift ;;
        -h|--help) sed -n '2,55p' "$0"; exit 0 ;;
        *) echo "✗ unknown argument: $1" >&2; exit 2 ;;
    esac
done

COMPOSE="docker compose -f ${BRAIN_DIR}/docker-compose.yml"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${BACKUP_DIR}/${CATEGORY}/${TS}"

log() { echo "$(date -u +%H:%M:%S) $*"; }
fail() { echo "✗ $*" >&2; exit 1; }

# ── Pre-flight ──────────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || fail "docker not found on PATH"
[ -f "${BRAIN_DIR}/docker-compose.yml" ] || fail "no docker-compose.yml at ${BRAIN_DIR}"

# The DB must be reachable — we cannot dump a stopped Postgres. For --pre-update
# this always holds (the brain is up when an update starts).
$COMPOSE ps postgres 2>/dev/null | grep -q "Up\|running" \
    || fail "postgres container is not running; start the brain before backing up"

PGUSER="$($COMPOSE exec -T postgres printenv POSTGRES_USER 2>/dev/null | tr -d '\r' || true)"
PGDB="$($COMPOSE exec -T postgres printenv POSTGRES_DB 2>/dev/null | tr -d '\r' || true)"
PGUSER="${PGUSER:-postgres}"
PGDB="${PGDB:-llm_db}"

mkdir -p "$DEST"
log "==> Brain backup [${CATEGORY}] → ${DEST}"
[ -n "$LABEL" ] && log "    label: ${LABEL}"

# ── 1. Postgres dump (whole DB, gzipped) ─────────────────────────────────────
log "==> pg_dump ${PGDB} (user ${PGUSER})..."
# --clean --if-exists so the dump can be replayed onto an existing DB on restore.
set -o pipefail
$COMPOSE exec -T postgres pg_dump -U "$PGUSER" -d "$PGDB" --clean --if-exists \
    | gzip -c > "${DEST}/db.sql.gz"
# Guard the producer side of the pipe: a failed pg_dump that still produces a
# valid (tiny) gzip stream would otherwise look like success.
pg_status=${PIPESTATUS[0]}
[ "$pg_status" -eq 0 ] || fail "pg_dump failed (exit ${pg_status}); incomplete artifact left at ${DEST}"
log "    db.sql.gz: $(du -h "${DEST}/db.sql.gz" | cut -f1)"

# ── 2. Runtime state tar (from inside the api container) ─────────────────────
# Tarred from inside the container so named volumes and bind mounts are handled
# uniformly. Only paths that exist are included; missing optional files (e.g. a
# brain that never federated) are skipped, not fatal.
log "==> tar runtime state from api container..."
$COMPOSE exec -T api sh -c '
    set -e
    candidates="app/runtime app/data app/brain-apps app/brainfoundry app/api/brain_persona.local.md"
    paths=""
    for p in $candidates; do
        [ -e "/$p" ] && paths="$paths $p"
    done
    if [ -z "$paths" ]; then
        echo "no runtime paths present" >&2
        exit 3
    fi
    tar czf - -C / $paths
' > "${DEST}/runtime.tar.gz"
log "    runtime.tar.gz: $(du -h "${DEST}/runtime.tar.gz" | cut -f1)"

# ── 3. Manifest ──────────────────────────────────────────────────────────────
GIT_HEAD="$(git -C "$BRAIN_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
VERSION="$(cat "${BRAIN_DIR}/VERSION" 2>/dev/null || echo unknown)"
ROWS="$($COMPOSE exec -T postgres psql -U "$PGUSER" -d "$PGDB" -tAc \
    'SELECT count(*) FROM document_embeddings' 2>/dev/null | tr -d '\r' || echo '?')"
{
    echo "brain backup manifest"
    echo "timestamp_utc: ${TS}"
    echo "category:      ${CATEGORY}"
    echo "label:         ${LABEL:-(none)}"
    echo "brain_dir:     ${BRAIN_DIR}"
    echo "git_head:      ${GIT_HEAD}"
    echo "version:       ${VERSION}"
    echo "pg_db:         ${PGDB}"
    echo "document_embeddings_rows: ${ROWS}"
    echo "db.sql.gz:      $(stat -c%s "${DEST}/db.sql.gz" 2>/dev/null || stat -f%z "${DEST}/db.sql.gz") bytes"
    echo "runtime.tar.gz: $(stat -c%s "${DEST}/runtime.tar.gz" 2>/dev/null || stat -f%z "${DEST}/runtime.tar.gz") bytes"
    echo "note: secrets (.env, keys) are NOT in this artifact by design — supply .env on restore"
} > "${DEST}/manifest.txt"
log "==> artifact complete: ${ROWS} embedding rows captured"

# ── 4. Weekly promotion (hardlink — no extra disk) ───────────────────────────
# Keep one daily per week as a weekly snapshot. We promote when no weekly
# artifact exists yet for the current ISO week.
if [ "$CATEGORY" = "daily" ]; then
    ISO_WEEK="$(date -u +%G-W%V)"
    WEEKLY_BASE="${BACKUP_DIR}/weekly"
    mkdir -p "$WEEKLY_BASE"
    if [ -z "$(find "$WEEKLY_BASE" -maxdepth 1 -name "*_${ISO_WEEK}" -type d -print -quit 2>/dev/null)" ]; then
        WEEKLY_DEST="${WEEKLY_BASE}/${TS}_${ISO_WEEK}"
        if cp -al "$DEST" "$WEEKLY_DEST" 2>/dev/null || cp -a "$DEST" "$WEEKLY_DEST"; then
            log "==> promoted to weekly snapshot (${ISO_WEEK})"
        fi
    fi
fi

# ── 5. Retention (prune oldest; never silent) ────────────────────────────────
prune() {
    local dir="$1" keep="$2" name="$3"
    [ -d "$dir" ] || return 0
    # Newest-first; delete everything past the keep count.
    local victims
    victims="$(ls -1dt "$dir"/*/ 2>/dev/null | tail -n +"$((keep + 1))" || true)"
    if [ -n "$victims" ]; then
        echo "$victims" | while read -r v; do
            [ -n "$v" ] || continue
            log "==> pruning ${name}: $(basename "$v")"
            rm -rf "$v"
        done
    fi
}
prune "${BACKUP_DIR}/daily"      "$DAILY_KEEP"     "daily"
prune "${BACKUP_DIR}/weekly"     "$WEEKLY_KEEP"    "weekly"
prune "${BACKUP_DIR}/pre-update" "$PREUPDATE_KEEP" "pre-update"

log "✓ backup done → ${DEST}"
echo "$DEST"
