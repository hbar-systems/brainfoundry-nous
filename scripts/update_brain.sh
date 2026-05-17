#!/bin/bash
#
# update_brain.sh — pull latest brain code from GitHub, rebuild, verify.
#
# Safe by default:
#   - Backs up .env before pulling (timestamped, kept for rollback)
#   - Volumes persist across rebuild (chats, ingested docs, models all survive)
#   - Verifies /health after rebuild; restores .env if rebuild fails
#
# Usage:
#   ./scripts/update_brain.sh
#
# Or via the wrapper CLI:
#   nous update     (alias — same script)

set -e

BRAIN_DIR="${BRAIN_DIR:-/home/hbar/brain}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8010/health}"
TS=$(date +%Y%m%d-%H%M%S)

cd "$BRAIN_DIR"

# git's dubious-ownership guard blocks all git commands when this script runs
# as root in-container against the uid-1000-owned bind-mounted repo. Mark it
# safe. (The api Dockerfile also does this system-wide — belt and suspenders.)
git config --global --add safe.directory "$BRAIN_DIR" 2>/dev/null || true

echo ""
echo "==> Brain update — $TS"
echo "==> Working directory: $BRAIN_DIR"
echo ""

# Confirm git can operate on this repo. Capture stderr so a real failure
# (ownership guard, permissions) is reported accurately rather than being
# misdiagnosed as "not a git repository".
if ! git_dir_err=$(git rev-parse --git-dir 2>&1 >/dev/null); then
    echo "✗ git cannot operate on the repository at $BRAIN_DIR"
    echo "  git said: ${git_dir_err:-(no detail)}"
    echo "  An ownership or permission error here is a deploy bug, not a"
    echo "  missing repo. A genuine non-git directory needs the retrofit"
    echo "  (scripts/retrofit_git.sh)."
    exit 1
fi

if ! git remote get-url origin > /dev/null 2>&1; then
    echo "✗ No 'origin' remote configured. Cannot pull updates."
    exit 1
fi

# Show current vs available
echo "==> Current version:"
git log --oneline -1
echo ""

echo "==> Fetching latest from $(git remote get-url origin)..."
git fetch origin --quiet

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main 2>/dev/null || git rev-parse origin/master)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "✓ Already up to date. No changes."
    exit 0
fi

echo "==> Latest available:"
git log --oneline "$REMOTE" -1
echo ""

# Show what's changing
echo "==> Changes coming in:"
git log --oneline "$LOCAL".."$REMOTE" | head -20
echo ""

# Backup .env
if [ -f .env ]; then
    cp .env ".env.bak-$TS"
    echo "✓ Backed up .env → .env.bak-$TS"
fi

# Pull
echo "==> Pulling..."
if ! git pull --ff-only origin main 2>&1 || git pull --ff-only origin master 2>&1; then
    echo "✗ Pull failed (likely local changes conflict). Aborting — your brain is unchanged."
    exit 1
fi

# Restore .env (in case it was tracked for some reason — defensive)
if [ ! -f .env ] && [ -f ".env.bak-$TS" ]; then
    cp ".env.bak-$TS" .env
    echo "✓ Restored .env from backup"
fi

# Record the pre-update commit as the rollback point. scripts/revert_brain.sh
# (and the console "Revert to previous version" button) read this to undo
# exactly one step — back to the version that was just running, the one known
# to be database-compatible.
echo "$LOCAL" > "$BRAIN_DIR/.update-prev-commit"
echo "✓ Rollback point recorded: $(git rev-parse --short "$LOCAL")"

# Rebuild.
#
# The Update endpoint runs this script INSIDE the api container. A plain
# `docker compose up -d --build` would kill the script — and itself — the
# instant it recreates the api container, leaving the new images built but the
# containers never recreated onto them (the git pull lands, the rebuild does
# not). So: build everything, recreate every service EXCEPT api here (the
# script survives those), then hand the api recreate to a short-lived detached
# helper container that outlives the api container being replaced.
echo ""
echo "==> Rebuilding services (this can take 1-3 minutes)..."
echo "    Your chats, documents, and models persist — only code is rebuilt."
docker compose build
docker compose up -d --no-deps --no-build nodeos ui public-chat
echo "==> Recreating the api container via a detached helper..."
docker run -d --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$BRAIN_DIR":"$BRAIN_DIR" -w "$BRAIN_DIR" \
    "$(basename "$BRAIN_DIR")-api" \
    docker compose up -d --no-deps --no-build api
echo "    api is restarting on the new image. If you ran this from the brain's"
echo "    Update tab, the live log stops here — that is expected; the tab polls"
echo "    until the new version is up."

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
    echo "✓ Update complete. Brain is healthy."
    echo ""
    echo "==> Now running:"
    git log --oneline -1
    echo ""
    echo "Backup of previous .env: .env.bak-$TS (safe to delete after a day)"
else
    echo ""
    echo "✗ Brain did not return to healthy state after update."
    echo "  Restoring .env from backup. Check 'docker compose logs' for errors."
    if [ -f ".env.bak-$TS" ]; then
        cp ".env.bak-$TS" .env
    fi
    exit 1
fi
