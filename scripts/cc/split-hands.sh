#!/usr/bin/env bash
# split-hands.sh
# Created: 2026-09-27
# Moves the reasoner out of the bridge's user. After this the bridge (user `cc` today) keeps
# its state, keys and tokens in its own home, closed to the reasoner; the reasoner and its
# jobs run as a new user `hands` through sudo with a sanitized environment; every page route
# of the bridge needs an operator token that only the console's proxy adds. Closes the gap
# recorded in hbar.security (the bridge and the reasoner shared a user).
#
# Runs ON the box as the brain user (hbar) with sudo, once; rerunnable (each step checks).
#   bash scripts/cc/split-hands.sh          -> do it
#   bash scripts/cc/split-hands.sh verify   -> the four checks, nothing changed
# Rollback: remove CC_HANDS_USER, CC_HANDS_HOME, CC_OPERATOR_TOKEN from the bridge env,
# empty /etc/caddy/cc.env, move the folders back, restart cc-bridge and reload caddy.
set -euo pipefail
BRAIN_DIR=${BRAIN_DIR:-/home/hbar/brain}
BRIDGE_USER=${BRIDGE_USER:-cc}
HANDS_USER=${HANDS_USER:-hands}
BRIDGE_HOME=$(eval echo "~$BRIDGE_USER")
HANDS_HOME=/home/$HANDS_USER
ENV_FILE="$BRIDGE_HOME/.cc-bridge/env"
CADDYFILE=${CADDYFILE:-/etc/caddy/Caddyfile}
setenv() { sudo sh -c "grep -v '^$1=' '$ENV_FILE' > '$ENV_FILE.tmp'; echo '$1=$2' >> '$ENV_FILE.tmp'; mv '$ENV_FILE.tmp' '$ENV_FILE'; chown $BRIDGE_USER:$BRIDGE_USER '$ENV_FILE'; chmod 600 '$ENV_FILE'"; }
getenv() { sudo grep -oP "^$1=\K.*" "$ENV_FILE" 2>/dev/null | tr -d '"' || true; }

verify() {
    echo "== verify"
    echo "hands cannot read the bridge's state: $(sudo -u "$HANDS_USER" ls "$BRIDGE_HOME/.cc-bridge" >/dev/null 2>&1 && echo FAIL || echo ok)"
    echo "hands cannot read the brain's env:    $(sudo -u "$HANDS_USER" cat "$BRAIN_DIR/.env" >/dev/null 2>&1 && echo FAIL || echo ok)"
    if sudo test -d "$HANDS_HOME/world"; then echo "bridge reaches the hands' world:      $(sudo -u "$BRIDGE_USER" ls "$HANDS_HOME/world" >/dev/null 2>&1 && echo ok || echo FAIL)"; else echo "bridge reaches the hands' out:        $(sudo -u "$BRIDGE_USER" ls "$HANDS_HOME/out" >/dev/null 2>&1 && echo ok || echo FAIL)"; fi
    echo "decision route without the token:     $(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:7682/cc/new) (403 expected)"
    echo "health:                               $(curl -s http://127.0.0.1:7682/cc/health | python3 -c 'import sys,json;d=json.load(sys.stdin);print("hands_user", d.get("hands_user"), "operator_token", d.get("operator_token"))')"
}

case "${1:-do}" in
verify) verify ;;
do)
    sudo test -f "$ENV_FILE" || { echo "no bridge env at $ENV_FILE"; exit 1; }
    echo "== 1/7 the hands user"
    id "$HANDS_USER" >/dev/null 2>&1 || sudo adduser --disabled-password --gecos "the reasoner's hands" "$HANDS_USER" >/dev/null
    sudo usermod -aG "$HANDS_USER" "$BRIDGE_USER"          # the bridge reads the hands' files through the group
    sudo chmod 750 "$HANDS_HOME"
    echo "== 2/7 the reasoner's things move to $HANDS_HOME"
    for d in world in out .claude .ableton-systems .numa-systems .work; do
        if sudo test -e "$BRIDGE_HOME/$d" && ! sudo test -e "$HANDS_HOME/$d"; then
            sudo mv "$BRIDGE_HOME/$d" "$HANDS_HOME/$d"; echo "  moved $d"
        fi
    done
    sudo mkdir -p "$HANDS_HOME/in" "$HANDS_HOME/out" "$HANDS_HOME/.cc-bridge"
    HAS_WORLD=0; sudo test -d "$HANDS_HOME/world" && HAS_WORLD=1   # a box without the world (e2e) skips the world steps
    if sudo test -f "$BRIDGE_HOME/.cc-bridge/mcp.json" && ! sudo test -f "$HANDS_HOME/.cc-bridge/mcp.json"; then
        sudo cp "$BRIDGE_HOME/.cc-bridge/mcp.json" "$HANDS_HOME/.cc-bridge/mcp.json"     # the packs' file: the hands run the packs
        sudo sed -i "s#$BRIDGE_HOME/#$HANDS_HOME/#g" "$HANDS_HOME/.cc-bridge/mcp.json"
    fi
    sudo chown -R "$HANDS_USER:$HANDS_USER" "$HANDS_HOME"
    # the bridge writes uploads into in/, reads out/ and the world, and the reconciler (as the
    # bridge user) commits into the world: group read everywhere, group write where needed
    sudo chmod -R g+rX "$HANDS_HOME/out" "$HANDS_HOME/in"
    sudo chmod -R g+w "$HANDS_HOME/in"
    sudo find "$HANDS_HOME/in" -type d -exec chmod g+s {} +
    if [ "$HAS_WORLD" = 1 ]; then
        sudo chmod -R g+rX "$HANDS_HOME/world"; sudo chmod -R g+w "$HANDS_HOME/world"
        sudo find "$HANDS_HOME/world" -type d -exec chmod g+s {} +
    fi
    sudo -u "$BRIDGE_USER" git config --global --add safe.directory '*' 2>/dev/null || true
    sudo -u "$HANDS_USER" git config --global --add safe.directory '*' 2>/dev/null || true
    # the hands' git identity and token for pushes (the bridge user had them)
    if sudo test -f "$HANDS_HOME/.work/git-credentials"; then
        sudo -u "$HANDS_USER" -H git config --global credential.helper "store --file=$HANDS_HOME/.work/git-credentials"
        sudo -u "$HANDS_USER" -H git config --global user.name "$(sudo -u "$BRIDGE_USER" -H git config --global user.name 2>/dev/null || echo 'hbar (via brain)')"
        sudo -u "$HANDS_USER" -H git config --global user.email "$(sudo -u "$BRIDGE_USER" -H git config --global user.email 2>/dev/null || echo 'brain@hbar.systems')"
        sudo -u "$HANDS_USER" -H git config --global pull.ff only
    fi
    echo "== 3/7 the reasoner CLI for $HANDS_USER"
    if ! sudo test -x "$HANDS_HOME/.local/bin/claude"; then
        sudo -u "$HANDS_USER" -H bash -c 'curl -fsSL https://claude.ai/install.sh -o /tmp/claude-install.sh && echo "installer sha256: $(sha256sum /tmp/claude-install.sh | cut -c1-16)" && bash /tmp/claude-install.sh >/dev/null && rm -f /tmp/claude-install.sh'
    fi
    sudo -u "$HANDS_USER" -H "$HANDS_HOME/.local/bin/claude" --version 2>/dev/null | head -1 || echo "  (claude for $HANDS_USER not verified; run: sudo -u $HANDS_USER -H claude --version)"
    echo "== 4/7 sudoers: the bridge may run commands as the hands, nothing else"
    printf '%s ALL=(%s) NOPASSWD: /usr/bin/env\n%s ALL=(%s) NOPASSWD: /usr/bin/env\n' "$BRIDGE_USER" "$HANDS_USER" "hbar" "$HANDS_USER" | sudo tee /etc/sudoers.d/cc-hands >/dev/null
    sudo chmod 440 /etc/sudoers.d/cc-hands; sudo visudo -cf /etc/sudoers.d/cc-hands >/dev/null
    echo "== 5/7 the operator token"
    TOK=$(getenv CC_OPERATOR_TOKEN); [ -n "$TOK" ] || TOK=$(python3 -c 'import secrets;print(secrets.token_hex(24))')
    setenv CC_OPERATOR_TOKEN "$TOK"
    printf 'CC_OPERATOR_TOKEN=%s\n' "$TOK" | sudo tee /etc/caddy/cc.env >/dev/null; sudo chmod 600 /etc/caddy/cc.env; sudo chown root:root /etc/caddy/cc.env
    sudo mkdir -p /etc/systemd/system/caddy.service.d
    printf '[Service]\nEnvironmentFile=/etc/caddy/cc.env\n' | sudo tee /etc/systemd/system/caddy.service.d/cc.conf >/dev/null
    if ! sudo grep -q "X-CC-Operator" "$CADDYFILE"; then
        sudo cp "$CADDYFILE" "$CADDYFILE.bak-split-$(date +%Y%m%d%H%M)"
        sudo python3 - "$CADDYFILE" <<'PY'
import re, sys
p = sys.argv[1]; t = open(p).read()
new = re.sub(r"(\n(\s+)reverse_proxy localhost:7682)\n", lambda m: f"{m.group(1)} {{\n{m.group(2)}    header_up X-CC-Operator {{$CC_OPERATOR_TOKEN}}\n{m.group(2)}}}\n", t, count=1)
if new == t: sys.exit("could not find the /cc reverse_proxy line")
open(p, "w").write(new)
PY
    fi
    sudo caddy validate --config "$CADDYFILE" --adapter caddyfile >/dev/null
    sudo systemctl daemon-reload; sudo systemctl restart caddy
    echo "== 6/7 the bridge env"
    setenv CC_HANDS_USER "$HANDS_USER"; setenv CC_HANDS_HOME "$HANDS_HOME"
    if [ "$HAS_WORLD" = 1 ]; then setenv CC_WORLD_DIR "$HANDS_HOME/world"; setenv CC_WORK_DIR "$HANDS_HOME/world"; fi
    setenv CC_MCP_CONFIG "$HANDS_HOME/.cc-bridge/mcp.json"; setenv CC_BIN "$HANDS_HOME/.local/bin/claude"
    # units that named the old paths: the pull timer, the reconciler, the memory link
    for u in /etc/systemd/system/cc-work-pull.service /etc/systemd/system/world-propose.service; do
        [ -f "$u" ] && sudo sed -i "s#$BRIDGE_HOME/world#$HANDS_HOME/world#g" "$u"
    done
    if [ "$HAS_WORLD" = 1 ] && sudo test -d "$HANDS_HOME/world/mind/claude"; then
        sudo -u "$HANDS_USER" -H mkdir -p "$HANDS_HOME/.claude/projects/-home-$HANDS_USER-world"
        sudo rm -rf "$HANDS_HOME/.claude/projects/-home-$HANDS_USER-world/memory"
        sudo -u "$HANDS_USER" -H ln -s "$HANDS_HOME/world/mind/claude" "$HANDS_HOME/.claude/projects/-home-$HANDS_USER-world/memory"
    fi
    sudo systemctl daemon-reload
    echo "== 7/7 restart and check"
    bash "$BRAIN_DIR/scripts/cc/install.sh" >/dev/null 2>&1 || true      # rewrites the door for the hands user
    sudo systemctl restart cc-bridge; sleep 2
    verify
    echo
    echo "Sign the reasoner in as $HANDS_USER if its login did not travel: the console's sign-in door, or: sudo -u $HANDS_USER -H claude auth login --claudeai" ;;
*) echo "usage: $0 [do|verify]"; exit 1 ;;
esac
