#!/usr/bin/env bash
# scripts/cc/set-token.sh — store the reasoner's long-lived sign-in token for headless use.
# Created: 2026-09-18.
#
# On a machine where the owner is signed in to the reasoner CLI, they run:
#     claude setup-token
# and copy the token it prints. Then, on the brain box:
#     bash scripts/cc/set-token.sh
# This prompts for the token (nothing echoes), writes CLAUDE_CODE_OAUTH_TOKEN into
# ~/.cc-bridge/env (mode 600), restarts the bridge and the terminal door, and prints the
# sign-in status. No browser, no terminal login on the server. The token is the owner's;
# it never enters a repo or a chat.
set -euo pipefail
ENV_FILE="$HOME/.cc-bridge/env"
mkdir -p "$HOME/.cc-bridge"; touch "$ENV_FILE"; chmod 600 "$ENV_FILE"
read -rsp "Reasoner token (from 'claude setup-token'): " TOKEN; echo
[ -n "$TOKEN" ] || { echo "no token given"; exit 1; }
grep -v "^CLAUDE_CODE_OAUTH_TOKEN=" "$ENV_FILE" > "$ENV_FILE.tmp" || true
echo "CLAUDE_CODE_OAUTH_TOKEN=$TOKEN" >> "$ENV_FILE.tmp"
mv "$ENV_FILE.tmp" "$ENV_FILE"; chmod 600 "$ENV_FILE"
unset TOKEN
sudo systemctl restart cc-bridge claude-tab 2>/dev/null || true
sleep 2
echo "auth: $(curl -s http://127.0.0.1:7682/cc/health | python3 -c 'import sys,json;d=json.load(sys.stdin);a=d.get("auth",{});print("signed in" if a.get("loggedIn") else "NOT signed in", a.get("email") or "")')"
