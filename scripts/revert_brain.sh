#!/bin/bash
#
# revert_brain.sh — roll the brain back to the version it was running before
# the last update. The one-step undo for scripts/update_brain.sh.
#
# WHY ONE STEP ONLY
#   The previous version is the one version known to be database-compatible —
#   the brain was just running it. Reverting further back can cross a schema
#   migration (new tables, embedding-dimension changes) and leave old code
#   against a newer database. So this script reverts only to the commit
#   update_brain.sh recorded in .update-prev-commit — no arbitrary version
#   picking.
#
# Safe by default:
#   - Backs up .env (timestamped) before touching anything
#   - Volumes persist across the rebuild (chats, documents, models survive)
#   - Verifies /health after rebuild
#
# Usage:
#   ./scripts/revert_brain.sh
#
# Invoked by the console "Revert to previous version" button via /admin/revert.

set -e

BRAIN_DIR="${BRAIN_DIR:-/home/hbar/brain}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8010/health}"
STAMP="$BRAIN_DIR/.update-prev-commit"
TS=$(date +%Y%m%d-%H%M%S)

cd "$BRAIN_DIR"

# git's dubious-ownership guard blocks all git commands when this runs as root
# in-container against the uid-1000-owned bind-mounted repo. Mark it safe.
git config --global --add safe.directory "$BRAIN_DIR" 2>/dev/null || true

echo ""
echo "==> Brain revert — $TS"
echo "==> Working directory: $BRAIN_DIR"
echo ""

# Confirm git can operate here. Capture stderr so a real failure is reported
# accurately rather than misdiagnosed.
if ! git_dir_err=$(git rev-parse --git-dir 2>&1 >/dev/null); then
    echo "✗ git cannot operate on the repository at $BRAIN_DIR"
    echo "  git said: ${git_dir_err:-(no detail)}"
    exit 1
fi

# Need a recorded rollback point.
if [ ! -s "$STAMP" ]; then
    echo "✗ No previous version recorded — nothing to revert to."
    echo "  A rollback point is created the next time you run an update."
    exit 1
fi
PREV=$(tr -d '[:space:]' < "$STAMP")

if ! git cat-file -e "${PREV}^{commit}" 2>/dev/null; then
    echo "✗ Recorded previous commit $PREV is not present in this repo."
    echo "  Cannot revert."
    exit 1
fi

CURRENT=$(git rev-parse HEAD)
if [ "$CURRENT" = "$PREV" ]; then
    echo "✓ Already on the previous version ($(git rev-parse --short "$PREV")). Nothing to do."
    exit 0
fi

echo "==> Currently running:"
git log --oneline -1 "$CURRENT"
echo "==> Reverting to:"
git log --oneline -1 "$PREV"
echo ""

# Backup .env
if [ -f .env ]; then
    cp .env ".env.bak-revert-$TS"
    echo "✓ Backed up .env → .env.bak-revert-$TS"
fi

echo "==> Resetting code to $(git rev-parse --short "$PREV")..."
git reset --hard "$PREV"

# Rebuild
echo ""
echo "==> Rebuilding services (this can take 1-3 minutes)..."
echo "    Your chats, documents, and models persist — only code is rebuilt."
docker compose up -d --build

# Health check
echo ""
echo "==> Waiting for brain to come back online..."
sleep 5
HEALTHY=0
for i in {1..30}; do
    if curl -fsS "$HEALTH_URL" > /dev/null 2>&1; then
        HEALTHY=1
        break
    fi
    sleep 2
done

if [ $HEALTHY -eq 1 ]; then
    echo ""
    echo "✓ Revert complete. Brain is healthy."
    echo "==> Now running:"
    git log --oneline -1
else
    echo ""
    echo "✗ Brain did not return to a healthy state after the revert."
    echo "  Check 'docker compose logs' for errors."
    exit 1
fi
