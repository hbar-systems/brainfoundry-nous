#!/usr/bin/env bash
# scripts/member-music-kit.sh — the music pack for one member's hands user (created 2026-11-03).
#
#   bash scripts/member-music-kit.sh <handle> <ableton-systems plugin checkout> [--dry-run|--check] [--sf2]
#
# Run as the box's admin (the one with sudo), after add-member.sh. It installs nothing as root:
# it makes a git bundle of the plugin checkout in a temporary directory the member's hands user can
# read, then runs the plugin's scripts/install-member.sh AS <handle>-hands (sudo -u, -H), which puts
# uv, a static ffmpeg, the plugin, its light venv (no torch, no demucs) and the MCP entry under that
# user's home. The bridge already names ~/.cc-bridge/mcp.json as CC_MCP_CONFIG (split-hands.sh).
# What stays with the admin: ABLETON_SYSTEMS_SPOKE and ABLETON_SYSTEMS_SPOKE_TOKEN in the member's
# bridge env (scripts/cc/set-env.sh), the free tools in CC_TOOLS, and a bridge restart.
set -euo pipefail
[ $# -ge 2 ] || { sed -n '2,13p' "$0"; exit 2; }
HANDLE="$1"; PLUGIN="$2"; shift 2
HANDS="$HANDLE-hands"
id "$HANDS" >/dev/null 2>&1 || { echo "no user $HANDS (run add-member.sh first)" >&2; exit 1; }
git -C "$PLUGIN" rev-parse --verify -q HEAD:scripts/install-member.sh >/dev/null \
  || { echo "$PLUGIN has no committed scripts/install-member.sh" >&2; exit 1; }
STAGE="$(mktemp -d /tmp/music-kit.XXXXXX)"; trap 'rm -rf "$STAGE"' EXIT
git -C "$PLUGIN" bundle create -q "$STAGE/plugin.bundle" HEAD
git -C "$PLUGIN" show HEAD:scripts/install-member.sh > "$STAGE/install-member.sh"
chmod 755 "$STAGE"; chmod 644 "$STAGE"/*
echo "== plugin $(git -C "$PLUGIN" log -1 --format='%h %ad' --date=short) for $HANDS"
sudo -u "$HANDS" -H bash "$STAGE/install-member.sh" "$HANDLE" --src "$STAGE/plugin.bundle" "$@"
