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

echo ""
echo "==> Brain update — $TS"
echo "==> Working directory: $BRAIN_DIR"
echo ""

# Confirm we're in a git repo with a remote
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "✗ Not a git repository. This brain wasn't provisioned with update support."
    echo "  See docs to retrofit, or contact support."
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
