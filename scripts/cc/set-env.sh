#!/usr/bin/env bash
# scripts/cc/set-env.sh — put one secret into the bridge's env file, from the operator's account.
# Created: 2026-09-29. After the split the env file belongs to the bridge user (cc), so the operator
# (hbar, with sudo) sets keys through this instead of editing the file. Nothing echoes; the value
# never enters a repo, a chat or the shell history (it is read, not typed on the command line).
#     bash scripts/cc/set-env.sh CC_TELEGRAM_TOKEN        # then paste the token from @BotFather
#     bash scripts/cc/set-env.sh ELEVENLABS_API_KEY
set -euo pipefail
KEY=${1:-}; [ -n "$KEY" ] || { echo "usage: $0 KEY_NAME"; exit 1; }
[[ "$KEY" =~ ^[A-Z0-9_]+$ ]] || { echo "key names are UPPER_SNAKE"; exit 1; }
BRIDGE_USER=${BRIDGE_USER:-cc}
ENV_FILE=$(eval echo "~$BRIDGE_USER")/.cc-bridge/env
sudo test -f "$ENV_FILE" || { echo "no bridge env at $ENV_FILE"; exit 1; }
read -rsp "$KEY: " VALUE; echo
[ -n "$VALUE" ] || { echo "nothing given"; exit 1; }
printf '%s' "$VALUE" | sudo env KEY="$KEY" ENV_FILE="$ENV_FILE" BRIDGE_USER="$BRIDGE_USER" sh -c '
  v=$(cat); grep -v "^$KEY=" "$ENV_FILE" > "$ENV_FILE.tmp" || true
  printf "%s=%s\n" "$KEY" "$v" >> "$ENV_FILE.tmp"; mv "$ENV_FILE.tmp" "$ENV_FILE"
  chown "$BRIDGE_USER:$BRIDGE_USER" "$ENV_FILE"; chmod 600 "$ENV_FILE"'
unset VALUE
sudo systemctl restart cc-bridge; sleep 3
echo "set $KEY; bridge restarted"
curl -s http://127.0.0.1:7682/cc/health | python3 -c 'import sys,json;d=json.load(sys.stdin);print("telegram lane:", {None:"off (no token)",False:"on, waiting for the first message (it pins the owner)",True:"on, owner pinned"}[d.get("telegram")], "| voice:", "on" if d.get("voice") else "off")'
