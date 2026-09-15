#!/usr/bin/env bash
# scripts/cc/install.sh — box side of the CC tab, one command.
# Created: 2026-09-15 (from two hbar.world ops scripts of 2026-09-14).
#
# Run ON the brain's server as the brain user (needs sudo), from the brain repo:
#     bash scripts/cc/install.sh
# Idempotent: re-run after an Update to pick up a newer bridge.
#
# What it does, in order:
#   1. apt installs ttyd (a web terminal; the back door for maintenance, at /claude/)
#   2. installs the reasoner CLI for this user (native binary, ~/.local/bin/claude)
#   3. systemd unit claude-tab: ttyd on 127.0.0.1:7681, base /claude, one persistent tmux
#   4. systemd unit cc-bridge: scripts/cc/cc-bridge.py on 127.0.0.1:7682, base /cc,
#      with the brain's api key in a mode-600 env file so the bridge can search memory
#   5. two routes in the console's Caddy block, /claude* and /cc*, validated before reload
#   6. starts both, checks them
# It does not touch .env, docker, the database, or the brain repo checkout.
# The CC tab itself is switched on with BRAIN_CC_ENABLED=true in the brain's .env
# (docs/CC.md), which this script does not edit.
#
# Rollback: sudo systemctl disable --now claude-tab cc-bridge; restore the Caddyfile
# backup named below; sudo systemctl reload caddy.
set -euo pipefail

BRAIN_USER=${BRAIN_USER:-$(id -un)}
BRAIN_DIR=${BRAIN_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}
HOME_DIR=$(eval echo "~$BRAIN_USER")
CADDYFILE=${CADDYFILE:-/etc/caddy/Caddyfile}
TERM_PORT=${TERM_PORT:-7681}
CC_PORT=${CC_PORT:-7682}
STAMP=$(date +%Y-%m-%d_%H%M%S)
ENV_FILE="$HOME_DIR/.cc-bridge/env"

echo "== brain user $BRAIN_USER, repo $BRAIN_DIR"
[ -f "$BRAIN_DIR/VERSION" ] || { echo "not a brain repo: $BRAIN_DIR"; exit 1; }

echo "== 1/6 ttyd"
if ! command -v ttyd >/dev/null; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q ttyd
fi
# The Ubuntu package enables its own ttyd.service on the same port; only ours may own it.
sudo systemctl disable --now ttyd.service 2>/dev/null || true
sudo systemctl mask ttyd.service 2>/dev/null || true
ttyd --version

echo "== 2/6 reasoner CLI (user $BRAIN_USER)"
if [ ! -x "$HOME_DIR/.local/bin/claude" ]; then
    curl -fsSL https://claude.ai/install.sh -o /tmp/claude-install.sh
    echo "installer sha256: $(sha256sum /tmp/claude-install.sh | cut -c1-16)"
    bash /tmp/claude-install.sh
fi
"$HOME_DIR/.local/bin/claude" --version

echo "== 3/6 unit claude-tab (terminal back door)"
sudo tee /etc/systemd/system/claude-tab.service >/dev/null <<UNIT
[Unit]
Description=Reasoner web terminal for the brain console (ttyd + tmux)
After=network.target

[Service]
User=$BRAIN_USER
WorkingDirectory=$BRAIN_DIR
Environment=HOME=$HOME_DIR
Environment=PATH=$HOME_DIR/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=TERM=xterm-256color
ExecStart=/usr/bin/ttyd -i 127.0.0.1 -p $TERM_PORT -b /claude -W -t titleFixed="terminal" -t fontSize=14 -t disableLeaveAlert=true /usr/bin/tmux new-session -A -s claude -c $BRAIN_DIR "claude; exec bash"
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT

echo "== 4/6 unit cc-bridge"
mkdir -p "$HOME_DIR/.cc-bridge"
if [ ! -s "$ENV_FILE" ]; then
    # The brain's api key, so the bridge can search memory. .env is root-owned on most brains.
    if sudo grep -q "^BRAIN_API_KEY=" "$BRAIN_DIR/.env" 2>/dev/null; then
        sudo sh -c "grep '^BRAIN_API_KEY=' '$BRAIN_DIR/.env' > '$ENV_FILE'"
        sudo chown "$BRAIN_USER":"$BRAIN_USER" "$ENV_FILE"; chmod 600 "$ENV_FILE"
        echo "api key copied into $ENV_FILE (mode 600)"
    else
        echo "no BRAIN_API_KEY in .env; the bridge will run without memory until $ENV_FILE holds one"
    fi
fi
python3 -m py_compile "$BRAIN_DIR/scripts/cc/cc-bridge.py"
sudo tee /etc/systemd/system/cc-bridge.service >/dev/null <<UNIT
[Unit]
Description=CC bridge: headless reasoner turns for the brain console CC tab
After=network.target

[Service]
User=$BRAIN_USER
WorkingDirectory=$BRAIN_DIR
Environment=HOME=$HOME_DIR
Environment=PATH=$HOME_DIR/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=CC_PORT=$CC_PORT
Environment=CC_BASE=/cc
Environment=CC_CWD=$BRAIN_DIR
Environment=CC_TOOLS=Read,Grep,Glob
EnvironmentFile=-$ENV_FILE
ExecStart=/usr/bin/python3 $BRAIN_DIR/scripts/cc/cc-bridge.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT

echo "== 5/6 Caddy routes"
add_route() {  # name base port
    local name=$1 base=$2 port=$3
    if grep -q "@$name path $base $base/\*" "$CADDYFILE"; then
        echo "route $base already present"; return 0
    fi
    sudo cp "$CADDYFILE" "$CADDYFILE.bak.$STAMP"
    sudo python3 - "$CADDYFILE" "$name" "$base" "$port" <<'PY'
import sys, re
path, name, base, port = sys.argv[1:5]
text = open(path).read()
# Insert inside the console host's authenticated block, before its ui reverse_proxy
# (the LAST reverse_proxy to the ui port 3010 in the file).
needle = "reverse_proxy localhost:3010"
idx = text.rfind(needle)
if idx < 0:
    sys.exit("could not find the console ui reverse_proxy line; add the route by hand (docs/CC.md)")
ls = text.rfind("\n", 0, idx) + 1
indent = re.match(r"[ \t]*", text[ls:idx]).group(0)
block = f"{indent}@{name} path {base} {base}/*\n{indent}handle @{name} {{\n{indent}    reverse_proxy localhost:{port}\n{indent}}}\n"
open(path, "w").write(text[:ls] + block + text[ls:])
print(f"inserted {base} route")
PY
    if sudo caddy validate --config "$CADDYFILE" --adapter caddyfile >/dev/null 2>&1; then
        sudo systemctl reload caddy; echo "caddy reloaded"
    else
        echo "caddy validate FAILED, restoring backup"; sudo cp "$CADDYFILE.bak.$STAMP" "$CADDYFILE"; exit 1
    fi
}
add_route claude /claude "$TERM_PORT"
add_route cc /cc "$CC_PORT"

echo "== 6/6 start and check"
sudo systemctl daemon-reload
sudo systemctl enable claude-tab cc-bridge >/dev/null 2>&1
sudo systemctl restart claude-tab cc-bridge
sleep 2
echo "claude-tab: $(systemctl is-active claude-tab)   cc-bridge: $(systemctl is-active cc-bridge)"
echo "terminal  /claude/ -> HTTP $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$TERM_PORT/claude/)"
echo "bridge    /cc/health -> $(curl -s http://127.0.0.1:$CC_PORT/cc/health | cut -c1-200)"
HOST=$(grep -oE "^console\.[a-z0-9.-]+" "$CADDYFILE" | head -1)
echo
echo "Done. Now: BRAIN_CC_ENABLED=true in $BRAIN_DIR/.env (sudo), then Update tab or"
echo "'docker compose up -d api', then open https://$HOST/cc and press Connect."
