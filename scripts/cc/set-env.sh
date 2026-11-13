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
# `|| true`: a value piped in without a final newline (printf '1' | ...) makes read return 1; under
# set -e that ended the script before it wrote anything (CC_CODEX_WRITE, 2026-11-07, twice). An empty
# value still stops at the check below.
read -rsp "$KEY: " VALUE || true; echo
[ -n "$VALUE" ] || { echo "nothing given"; exit 1; }
if [ "$KEY" = "CC_TELEGRAM_TOKEN" ]; then
    # a bot token is <8-10 digits>:<35 letters, digits, _ or ->; anything else Telegram answers with Not Found
    if ! printf '%s' "$VALUE" | grep -Eq '^[0-9]{8,10}:[A-Za-z0-9_-]{35}$'; then
        tail=${VALUE#*:}
        echo "that is not the shape of a bot token: ${#VALUE} characters, ${#tail} after the colon (35 expected). Copy only the token line from @BotFather (API Token), or revoke and take the fresh one."
        unset VALUE; exit 1
    fi
fi
# written as the bridge user, who owns the file and its folder: root never writes by path into a folder
# a member user owns (audit 2026-11-13); the value goes on stdin, never into a shell program
. "$(dirname "$0")/member.sh"
printf '%s' "$VALUE" | bridge_env_set "$KEY"
unset VALUE
# a member's bridge (BRIDGE_USER=<m>-cc) is cc-bridge-<m>; this restarted the owner's own cc-bridge (2026-11-08)
UNIT=cc-bridge; [ "$BRIDGE_USER" != cc ] && [ "${BRIDGE_USER%-cc}" != "$BRIDGE_USER" ] && UNIT="cc-bridge-${BRIDGE_USER%-cc}"
sudo systemctl restart "$UNIT"; sleep 3
echo "set $KEY; $UNIT restarted"
[ "$UNIT" = cc-bridge ] || exit 0   # the lane line below reads the owner's port only
curl -s http://127.0.0.1:7682/cc/health | python3 -c 'import sys,json;d=json.load(sys.stdin);print("telegram lane:", {None:"off (no token)",False:"on, waiting for the first message (it pins the owner)",True:"on, owner pinned"}[d.get("telegram")], "| voice:", "on" if d.get("voice") else "off")'
