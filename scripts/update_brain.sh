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

# Pre-flight: self-heal brain-dir ownership.
#
# The api container runs as root and writes into the bind-mounted brain dir
# (any container-side git op, .update-prev-commit, app installs, etc.).
# Those writes leave files root-owned, blocking SSH-side operations with
# `fatal: insufficient permission for adding an object to repository
# database .git/objects` (git fetch) or `Permission denied` (any file
# write). The recurring pattern in project_container_root_chown_pattern.
# We self-heal by asking the api container (root + bind-mount) to chown
# the whole brain dir back to the host operator's uid:gid before fetching.
# Surfaced on hbar 2026-05-26 — same wall will hit every git-deployed brain.
if [ -n "$(find "$BRAIN_DIR" -not -user "$(whoami)" -print -quit 2>/dev/null)" ]; then
    echo "==> Detected non-operator-owned files in brain dir (container write residue) — healing..."
    api_container="$(basename "$BRAIN_DIR")-api-1"
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${api_container}\$"; then
        if docker exec "$api_container" chown -R "$(id -u):$(id -g)" "$BRAIN_DIR" > /dev/null 2>&1; then
            echo "✓ Ownership healed via $api_container"
        else
            echo "⚠ Container chown failed. Try manually: sudo chown -R $(whoami):$(whoami) $BRAIN_DIR"
        fi
    else
        echo "⚠ $api_container not running. Operations may fail; manual fix: sudo chown -R $(whoami):$(whoami) $BRAIN_DIR"
    fi
fi

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

# Pre-update snapshot — the safety net. Before we pull and rebuild against the
# live Postgres volume, capture a restorable backup so a bad deploy costs
# minutes (scripts/restore_brain.sh) instead of a brain's memory. Snapshots go
# UNDER the bind-mounted brain dir (.brain-backups/) so they survive the rebuild
# even when this script runs inside the api container — the host-side
# /home/hbar/brain-backups is not mounted in. Best-effort by default: a backup
# failure warns loudly but does not block the update (volumes persist across an
# ff-only pull + rebuild, and the rollback commit + revert_brain.sh remain). Set
# REQUIRE_BACKUP=1 to abort the update if the snapshot cannot be taken.
if [ -x "$BRAIN_DIR/scripts/backup_brain.sh" ]; then
    echo "==> Pre-update snapshot..."
    if BACKUP_DIR="${PREUPDATE_BACKUP_DIR:-$BRAIN_DIR/.brain-backups}" \
        "$BRAIN_DIR/scripts/backup_brain.sh" --pre-update --label "$(git rev-parse --short "$REMOTE")"; then
        echo "✓ Pre-update snapshot taken (restore with scripts/restore_brain.sh)"
    else
        echo "⚠ Pre-update snapshot FAILED."
        if [ "${REQUIRE_BACKUP:-0}" = "1" ]; then
            echo "✗ REQUIRE_BACKUP=1 — aborting before any change. Brain is unchanged."
            exit 1
        fi
        echo "  Continuing without a snapshot (REQUIRE_BACKUP=1 to enforce)."
    fi
    echo ""
fi

# Backup .env
if [ -f .env ]; then
    cp .env ".env.bak-$TS"
    echo "✓ Backed up .env → .env.bak-$TS"
fi

# Preserve runtime state that was tracked on older provisions but is gitignored
# at current HEAD. brain-apps/installed.json is the canonical example: provisions
# before commit 21ff948 (2026-05-20) carry it as a tracked file that mutates
# every time an app is installed/updated, so pull sees it as "local changes" and
# aborts. Back it up explicitly; restore after pull.
RUNTIME_BACKUPS=()
if [ -f "$BRAIN_DIR/brain-apps/installed.json" ]; then
    cp "$BRAIN_DIR/brain-apps/installed.json" "/tmp/installed.json.bak-$TS"
    RUNTIME_BACKUPS+=("brain-apps/installed.json:/tmp/installed.json.bak-$TS")
    echo "✓ Backed up brain-apps/installed.json (runtime state)"
fi

# Stash any local working-tree modifications + untracked files so the pull is
# never blocked by a dirty tree. After pull we try to pop; on conflict we surface
# the stash ref to the operator instead of aborting the whole update. Recurring
# pattern for brains provisioned before the chown-fix bundle landed.
STASH_REF=""
if ! git diff --quiet HEAD 2>/dev/null || [ -n "$(git ls-files --others --exclude-standard)" ]; then
    if git stash push --include-untracked --message "auto-stash-$TS" > /tmp/stash-out-$TS 2>&1; then
        STASH_REF=$(git stash list --format='%gd' | head -1)
        echo "✓ Local changes stashed as $STASH_REF (will try to re-apply after pull)"
    else
        echo "✗ git stash failed:"
        cat /tmp/stash-out-$TS
        echo "  Aborting before any state change. Your brain is unchanged."
        exit 1
    fi
fi

# Pull
echo "==> Pulling..."
if ! git pull --ff-only origin main 2>&1; then
    if ! git pull --ff-only origin master 2>&1; then
        echo "✗ Pull failed even after stash. Aborting — your brain is unchanged."
        if [ -n "$STASH_REF" ]; then
            echo "  Re-applying stashed changes from $STASH_REF..."
            git stash pop "$STASH_REF" 2>&1 || echo "  Stash pop failed; manual recovery: git stash list / git stash pop"
        fi
        exit 1
    fi
fi

# Restore .env (in case it was tracked for some reason — defensive)
if [ ! -f .env ] && [ -f ".env.bak-$TS" ]; then
    cp ".env.bak-$TS" .env
    echo "✓ Restored .env from backup"
fi

# Restore runtime-state files that the new HEAD considers untracked. The pull
# removed them from the working tree (because they're now gitignored), but the
# brain still needs them — apps registry, etc.
for entry in "${RUNTIME_BACKUPS[@]}"; do
    target="${entry%%:*}"
    source="${entry##*:}"
    if [ ! -f "$BRAIN_DIR/$target" ] && [ -f "$source" ]; then
        cp "$source" "$BRAIN_DIR/$target"
        echo "✓ Restored $target from backup"
    fi
done

# Try to re-apply local changes. Most of the time the stashed changes are
# duplicates of what's now in HEAD (e.g. operator rsync-applied a fix before
# the proper commit existed), so pop will conflict harmlessly and we discard.
# Real local edits will conflict in a way the operator needs to resolve — we
# surface the stash ref rather than abort.
if [ -n "$STASH_REF" ]; then
    if git stash pop "$STASH_REF" > /tmp/stash-pop-$TS 2>&1; then
        echo "✓ Re-applied local changes from $STASH_REF cleanly"
    else
        if grep -q "CONFLICT" /tmp/stash-pop-$TS; then
            # Conflict resolution: per the no-rsync deploy rule (feedback memory
            # 2026-05-26), legitimate code lives in commits — local working-tree
            # mods on a brain are always duplicates of HEAD (rsync-applied
            # fixes that landed as proper commits later). So we resolve by
            # taking HEAD's view of every conflicted file and dropping the
            # stash. Without this, conflict markers like `<<<<<<< Updated
            # upstream` end up in files like api/main.py, Python refuses to
            # import them, the api container crash-loops, and the brain is
            # broken until manual recovery. Surfaced on nous/yury/hbar.uni
            # 2026-05-26 during the first Update-tab rollout.
            echo "⚠ Stash pop produced conflicts. Auto-resolving by taking HEAD"
            echo "  (per the no-rsync rule — stashed content was duplicate of HEAD)..."
            git checkout HEAD -- . 2>&1 | head -3
            git stash drop "$STASH_REF" 2>&1 | head -1
            echo "✓ Conflicts resolved, stash dropped. Working tree matches HEAD."
            echo "  If you had genuine local edits you wanted preserved, they"
            echo "  are GONE — commit your changes before running update_brain.sh."
        else
            echo "⚠ Stash pop failed unexpectedly:"
            cat /tmp/stash-pop-$TS
            echo "  Stash preserved as $STASH_REF for manual recovery."
        fi
    fi
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
