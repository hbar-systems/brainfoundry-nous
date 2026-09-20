#!/usr/bin/env bash
# scripts/cc/harden-user.sh — run the CC bridge as its own user without sudo (hardening item 3).
# Created: 2026-09-20.
#
# Before: the bridge (and so the reasoner behind CC) runs as the brain user, who has sudo on
# provisioned brains. After: it runs as a plain user "cc" with its own home, its own reasoner
# sign-in, and the bridge state moved over. The terminal door stays the brain user's.
# Idempotent. Rollback: `BRIDGE_USER=$(id -un) bash scripts/cc/install.sh` moves the unit back
# to the brain user (the old state stays in ~/.cc-bridge).
#
# Run ON the box as the brain user, from the brain repo:
#     bash scripts/cc/harden-user.sh            # migrate state; the reasoner needs a sign-in for "cc"
#     bash scripts/cc/harden-user.sh --copy-login   # also copy this user's reasoner sign-in to "cc"
#                                                    (your own credential onto your own second user;
#                                                     only on a brain you operate yourself)
# Then, if you did not copy the login: from the CC page paste your API key, or run
#     sudo -u cc -H bash scripts/cc/set-token.sh
set -euo pipefail
BRAIN_USER=$(id -un); BRAIN_HOME=$HOME
BRAIN_DIR=${BRAIN_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}
CC_USER=${CC_USER:-cc}
COPY_LOGIN=0; [ "${1:-}" = "--copy-login" ] && COPY_LOGIN=1
command -v rsync >/dev/null || sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q rsync >/dev/null

echo "== 1/5 user $CC_USER (no sudo)"
if ! id "$CC_USER" >/dev/null 2>&1; then
    sudo useradd -m -s /bin/bash -U "$CC_USER"
fi
sudo gpasswd -d "$CC_USER" sudo 2>/dev/null || true
CC_HOME=$(eval echo "~$CC_USER")
# The bridge must traverse into the brain user's home for the repo and the mirror; x only, no listing.
sudo chmod 751 "$BRAIN_HOME"
[ -d "$BRAIN_HOME/world" ] && sudo chmod -R a+rX "$BRAIN_HOME/world" 2>/dev/null || true

echo "== 2/5 bridge state moved to $CC_HOME/.cc-bridge"
if [ -d "$BRAIN_HOME/.cc-bridge" ]; then
    sudo mkdir -p "$CC_HOME/.cc-bridge"
    sudo rsync -a --exclude venv "$BRAIN_HOME/.cc-bridge/" "$CC_HOME/.cc-bridge/"
    sudo chown -R "$CC_USER":"$CC_USER" "$CC_HOME/.cc-bridge"
    sudo chmod 700 "$CC_HOME/.cc-bridge"; sudo chmod 600 "$CC_HOME/.cc-bridge/env" 2>/dev/null || true
    echo "copied (env, permits, audit, threads, allowances); the old copy stays in $BRAIN_HOME/.cc-bridge"
fi

echo "== 3/5 the reasoner for $CC_USER"
sudo mkdir -p "$CC_HOME/.claude/skills"
if [ -d "$BRAIN_HOME/.claude/skills" ]; then
    sudo rsync -a "$BRAIN_HOME/.claude/skills/" "$CC_HOME/.claude/skills/"
fi
if [ "$COPY_LOGIN" = 1 ] && [ -f "$BRAIN_HOME/.claude/.credentials.json" ]; then
    sudo cp "$BRAIN_HOME/.claude/.credentials.json" "$CC_HOME/.claude/.credentials.json"
    echo "reasoner sign-in copied to $CC_USER (your own credential, your own box)"
fi
sudo chown -R "$CC_USER":"$CC_USER" "$CC_HOME/.claude"
sudo chmod 700 "$CC_HOME/.claude"; sudo chmod 600 "$CC_HOME/.claude/.credentials.json" 2>/dev/null || true

echo "== 4/5 units rewritten by the installer for BRIDGE_USER=$CC_USER"
BRIDGE_USER="$CC_USER" bash "$BRAIN_DIR/scripts/cc/install.sh" | grep -E "runs as|permitd|hands|active|reasoner CLI|NOTE" || true

echo "== 5/5 check"
sleep 2
echo "cc-bridge: $(systemctl is-active cc-bridge) as $(systemctl show cc-bridge -p User --value)"
curl -s http://127.0.0.1:7682/cc/health | python3 -c 'import sys,json;d=json.load(sys.stdin);a=d.get("auth",{});print("signed in:",a.get("loggedIn"),"| memory:",d.get("memory"),"| hands:",d.get("hands"))'
echo
echo "If 'signed in' is False: paste your API key on the CC page, or run: sudo -u $CC_USER -H bash $BRAIN_DIR/scripts/cc/set-token.sh"
