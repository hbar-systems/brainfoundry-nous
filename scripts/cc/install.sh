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
#      (a plain shell; type `claude` when you need it. An idle interactive Claude Code sitting
#      there competes with the bridge's headless runs for the sign-in token refresh.)
#   4. systemd unit cc-bridge: scripts/cc/cc-bridge.py on 127.0.0.1:7682, base /cc,
#      with the brain's api key in a mode-600 env file so the bridge can search memory,
#      running in a small venv that holds permitd (the permit gate for writes)
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
# The bridge may run as a separate user without sudo (scripts/cc/harden-user.sh, hardening
# item 3). If the unit already names one, keep it; everything of the bridge lives in that
# user's home. The terminal door stays the brain user's (the operator's back door).
BRIDGE_USER=${BRIDGE_USER:-$(grep -oP '^User=\K.*' /etc/systemd/system/cc-bridge.service 2>/dev/null || echo "$BRAIN_USER")}
BRIDGE_HOME=$(eval echo "~$BRIDGE_USER")
ENV_FILE="$BRIDGE_HOME/.cc-bridge/env"
SUDO_AS_BRIDGE=""; [ "$BRIDGE_USER" != "$(id -un)" ] && SUDO_AS_BRIDGE="sudo -u $BRIDGE_USER"

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
if [ "$BRIDGE_USER" != "$BRAIN_USER" ] && ! sudo test -x "$BRIDGE_HOME/.local/bin/claude"; then
    curl -fsSL https://claude.ai/install.sh -o /tmp/claude-install.sh
    sudo -u "$BRIDGE_USER" bash /tmp/claude-install.sh >/dev/null 2>&1 && echo "reasoner CLI installed for $BRIDGE_USER"
fi

echo "== 3/6 unit claude-tab (the door: a styled terminal that runs one thing)"
# door.sh: what the terminal runs. No argument: a persistent shell in the brain repo (the
# operator's back door). "login": Anthropic's own sign-in flow for the reasoner, and nothing
# else, so the CC sign-in card can open the door straight into it. The look follows the
# console (colours, font, no status bar) so it does not read as a terminal.
cat > "$HOME_DIR/.cc-bridge/door.sh" <<'DOOR'
#!/usr/bin/env bash
export PATH="$HOME/.local/bin:$PATH" TERM=xterm-256color
case "${1:-}" in
  login)
    clear
    printf '\n  Signing in to your own account, through the provider'"'"'s own flow.\n'
    printf '  1. A link appears below. Open it and sign in.\n  2. Copy the code it shows.\n  3. Paste the code here and press Enter.\n\n'
    claude auth login --claudeai
    printf '\n  Done. You can close this panel.\n'
    sleep 3600 ;;
  *)
    exec tmux -f /dev/null new-session -A -s claude -c "${BRAIN_DIR:-$HOME/brain}" \; set -g status off ;;
esac
DOOR
chmod 755 "$HOME_DIR/.cc-bridge/door.sh"
THEME='{"background":"#0f0e0c","foreground":"#e8e0d5","cursor":"#c9a96e","selectionBackground":"#3a3520","black":"#0f0e0c","brightBlack":"#6b5f52","white":"#e8e0d5","brightWhite":"#ffffff","yellow":"#c9a96e","brightYellow":"#e0c48a","blue":"#8fb3c9","green":"#9fbf8f","red":"#d08a7a"}'
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
EnvironmentFile=-$ENV_FILE
Environment=BRAIN_DIR=$BRAIN_DIR
ExecStart=/usr/bin/ttyd -i 127.0.0.1 -p $TERM_PORT -b /claude -W -a -t titleFixed="brain" -t fontSize=15 -t fontFamily="DM Mono, Menlo, monospace" -t disableLeaveAlert=true -t 'theme=$THEME' /usr/bin/bash $HOME_DIR/.cc-bridge/door.sh
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT

echo "== 4/6 unit cc-bridge (runs as $BRIDGE_USER)"
$SUDO_AS_BRIDGE mkdir -p "$BRIDGE_HOME/.cc-bridge"
# A small venv for the bridge: permitd (the permit gate for writes; stdlib-only, tiny).
if [ ! -x "$BRIDGE_HOME/.cc-bridge/venv/bin/python" ]; then
    $SUDO_AS_BRIDGE python3 -m venv "$BRIDGE_HOME/.cc-bridge/venv" 2>/dev/null || { sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3-venv >/dev/null; $SUDO_AS_BRIDGE python3 -m venv "$BRIDGE_HOME/.cc-bridge/venv"; }
fi
$SUDO_AS_BRIDGE "$BRIDGE_HOME/.cc-bridge/venv/bin/pip" install -q --upgrade permitd >/dev/null 2>&1 && echo "permitd $($SUDO_AS_BRIDGE "$BRIDGE_HOME/.cc-bridge/venv/bin/python" -c 'import permitd;print(permitd.__version__)' 2>/dev/null || echo installed)"
if ! sudo test -s "$ENV_FILE"; then
    # The brain's api key, so the bridge can search memory. .env is root-owned on most brains.
    if sudo grep -q "^BRAIN_API_KEY=" "$BRAIN_DIR/.env" 2>/dev/null; then
        sudo sh -c "grep '^BRAIN_API_KEY=' '$BRAIN_DIR/.env' > '$ENV_FILE'"
        sudo chown "$BRIDGE_USER":"$BRIDGE_USER" "$ENV_FILE"; sudo chmod 600 "$ENV_FILE"
        echo "api key copied into $ENV_FILE (mode 600)"
    else
        echo "no BRAIN_API_KEY in .env; the bridge will run without memory until $ENV_FILE holds one"
    fi
fi
# Syntax check that writes nothing: the repo dir is often root-owned (container-side git), so no __pycache__.
python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$BRAIN_DIR/scripts/cc/cc-bridge.py" && echo "cc-bridge.py parses"
sudo tee /etc/systemd/system/cc-bridge.service >/dev/null <<UNIT
[Unit]
Description=CC bridge: headless reasoner turns for the brain console CC tab
After=network.target

[Service]
User=$BRIDGE_USER
WorkingDirectory=$BRAIN_DIR
Environment=HOME=$BRIDGE_HOME
Environment=PATH=$BRIDGE_HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=CC_PORT=$CC_PORT
Environment=CC_BASE=/cc
Environment=CC_CWD=$BRAIN_DIR
Environment=CC_TOOLS=Read,Grep,Glob
EnvironmentFile=-$ENV_FILE
ExecStart=$BRIDGE_HOME/.cc-bridge/venv/bin/python $BRAIN_DIR/scripts/cc/cc-bridge.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT

echo "== 4a/6 hands (only when a One key is present in the bridge env file)"
if sudo grep -q "^ONE_SECRET=" "$ENV_FILE" 2>/dev/null; then
    # Looking and doing are separate. The reasoner's own directory carries NO One restriction,
    # so its lookups see every action, reads and writes. It may run only: list, search,
    # knowledge, and one-read. one-read executes from a directory whose .onerc allows GET only.
    # Writes run only from the bridge, from ~/.cc-bridge/exec, with an approved permit.
    $SUDO_AS_BRIDGE mkdir -p "$BRIDGE_HOME/.cc-bridge/read" "$BRIDGE_HOME/.cc-bridge/exec" "$BRIDGE_HOME/.local/bin"
    echo "ONE_PERMISSIONS=read"  | $SUDO_AS_BRIDGE tee "$BRIDGE_HOME/.cc-bridge/read/.onerc" >/dev/null
    echo "ONE_PERMISSIONS=write" | $SUDO_AS_BRIDGE tee "$BRIDGE_HOME/.cc-bridge/exec/.onerc" >/dev/null
    $SUDO_AS_BRIDGE tee "$BRIDGE_HOME/.local/bin/one-read" >/dev/null <<'WRAP'
#!/usr/bin/env bash
# one-read: run ONE read action through One. Same arguments and flags as
# `one --agent actions execute`. Executes from a directory whose .onerc allows GET only,
# so a write passed here is refused by the One CLI itself.
cd "$HOME/.cc-bridge/read" || exit 1
exec one --agent actions execute "$@"
WRAP
    $SUDO_AS_BRIDGE chmod 755 "$BRIDGE_HOME/.local/bin/one-read"
    # An earlier setup put a read-only .onerc into the brain directory; it hides write actions
    # from lookups. Remove it only if it is exactly that one line.
    if [ -f "$BRAIN_DIR/.onerc" ] && [ "$(tr -d '[:space:]' < "$BRAIN_DIR/.onerc")" = "ONE_PERMISSIONS=read" ]; then
        sudo rm -f "$BRAIN_DIR/.onerc" && echo "removed the old read-only .onerc from the brain directory"
    fi
    TOOLS='Read,Grep,Glob,Bash(one --agent list:*),Bash(one --agent actions search:*),Bash(one --agent actions knowledge:*),Bash(one --agent platforms:*),Bash(one-read:*)'
    sudo sh -c "grep -v '^CC_TOOLS=' '$ENV_FILE' > '$ENV_FILE.tmp'; echo 'CC_TOOLS=$TOOLS' >> '$ENV_FILE.tmp'; mv '$ENV_FILE.tmp' '$ENV_FILE'; chown $BRIDGE_USER:$BRIDGE_USER '$ENV_FILE'; chmod 600 '$ENV_FILE'"
    echo "hands configured: lookups open, reads via one-read, writes only through the permit gate"
else
    echo "no ONE_SECRET in $ENV_FILE: hands not configured (docs/CC.md)"
fi

# Reasoner sign-in without a browser on the box: the owner runs `claude setup-token` on a
# machine where they are signed in and stores the long-lived token here (scripts/cc/set-token.sh).
# The CLI reads it from CLAUDE_CODE_OAUTH_TOKEN; both units load this env file.
if sudo grep -q "^CLAUDE_CODE_OAUTH_TOKEN=" "$ENV_FILE" 2>/dev/null; then
    echo "reasoner token present in $ENV_FILE (headless sign-in)"
fi

echo "== 4b/6 restart the bridge by itself when an Update changes its file"
sudo tee /etc/systemd/system/cc-bridge-watch.path >/dev/null <<UNIT
[Unit]
Description=Restart cc-bridge when scripts/cc/cc-bridge.py changes (Update tab swaps files, not host services)

[Path]
PathChanged=$BRAIN_DIR/scripts/cc/cc-bridge.py
Unit=cc-bridge-watch.service

[Install]
WantedBy=multi-user.target
UNIT
sudo tee /etc/systemd/system/cc-bridge-watch.service >/dev/null <<UNIT
[Unit]
Description=Restart cc-bridge after its file changed

[Service]
Type=oneshot
ExecStart=/bin/systemctl restart cc-bridge.service
UNIT

echo "== 4c/6 hands on the box (only when the bridge runs as a user without sudo)"
# The reasoner may edit files and run commands on this box; each call the person has not
# already allowed raises a card in the chat (PermissionRequest hook -> bridge -> card).
# Root is limited to a fixed list of verbs, each also behind a card. When the bridge runs as
# the brain user (who has sudo) this lane stays off: a reasoner with general sudo is the
# whole server, card or no card.
if [ "$BRIDGE_USER" != "$BRAIN_USER" ] && ! sudo -l -U "$BRIDGE_USER" 2>/dev/null | grep -q "(ALL"; then
    sed "s|__BRAIN_DIR__|$BRAIN_DIR|" "$BRAIN_DIR/scripts/cc/brain-write.sh" | sudo tee /usr/local/bin/brain-write >/dev/null
    sudo chown root:root /usr/local/bin/brain-write; sudo chmod 755 /usr/local/bin/brain-write
    sudo tee /etc/sudoers.d/cc-bridge.tmp >/dev/null <<VERBS
# The CC bridge user's root verbs (scripts/cc/install.sh). Each is also behind a card in the chat.
$BRIDGE_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart cc-bridge, /usr/bin/systemctl restart claude-tab, /usr/bin/systemctl status *, /usr/bin/journalctl *, /usr/bin/docker ps *, /usr/bin/docker compose --project-directory $BRAIN_DIR logs *, /usr/bin/bash $BRAIN_DIR/scripts/update_brain.sh, /usr/local/bin/brain-write *
VERBS
    if sudo visudo -cf /etc/sudoers.d/cc-bridge.tmp >/dev/null; then
        sudo chmod 440 /etc/sudoers.d/cc-bridge.tmp && sudo mv /etc/sudoers.d/cc-bridge.tmp /etc/sudoers.d/cc-bridge
        sudo grep -q "^CC_BOX=" "$ENV_FILE" 2>/dev/null || echo "CC_BOX=1" | sudo tee -a "$ENV_FILE" >/dev/null
        echo "box hands on: edits and commands raise a card; root verbs in /etc/sudoers.d/cc-bridge; helper /usr/local/bin/brain-write"
    else
        sudo rm -f /etc/sudoers.d/cc-bridge.tmp; echo "sudoers check failed; box hands left off"
    fi
else
    echo "box hands off: the bridge user has sudo (run scripts/cc/harden-user.sh first)"
fi

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
sudo systemctl enable claude-tab cc-bridge cc-bridge-watch.path >/dev/null 2>&1
sudo systemctl restart claude-tab cc-bridge
sudo systemctl restart cc-bridge-watch.path
sleep 2
echo "claude-tab: $(systemctl is-active claude-tab)   cc-bridge: $(systemctl is-active cc-bridge)"
echo "terminal  /claude/ -> HTTP $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$TERM_PORT/claude/)"
echo "bridge    /cc/health -> $(curl -s http://127.0.0.1:$CC_PORT/cc/health | cut -c1-200)"
HOST=$(grep -oE "^console\.[a-z0-9.-]+" "$CADDYFILE" | head -1)
echo
echo "Done. Now: BRAIN_CC_ENABLED=true in $BRAIN_DIR/.env (sudo), then Update tab or"
echo "'docker compose up -d api', then open https://$HOST/cc and press Connect."
