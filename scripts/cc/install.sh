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
# The Codex seat is opt-in and separate: scripts/cc/install-codex.sh (pinned version, hands
# user only); this script only adds the door's "codex-login" case for its sign-in.
# It does not touch .env, docker, the database, or the brain repo checkout.
# The CC tab itself is switched on with BRAIN_CC_ENABLED=true in the brain's .env
# (docs/CC.md), which this script does not edit.
#
# Rollback: sudo systemctl disable --now claude-tab cc-bridge; restore the Caddyfile
# backup named below; sudo systemctl reload caddy.
#
# A member on a shared box (2026-10-19, docs/MULTI_INSTANCE.md; scripts/multi/add-member.sh
# runs this): CC_MEMBER=<m> CC_MEMBER_N=<n> BRAIN_DIR=/srv/brains/<m>. Then the units are
# claude-tab-<m> and cc-bridge-<m>, the ports come from block n, the bridge and the terminal
# door run as <m>-cc (never the admin), the root verbs are that member's own units only, and
# CADDY_ROUTES=0 leaves the Caddyfile alone (add-member prints the whole site block).
# No CC_MEMBER: everything below is exactly the single brain of before.
set -euo pipefail

BRAIN_USER=${BRAIN_USER:-$(id -un)}
BRAIN_DIR=${BRAIN_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}
HOME_DIR=$(eval echo "~$BRAIN_USER")
CADDYFILE=${CADDYFILE:-/etc/caddy/Caddyfile}
. "$(dirname "$0")/member.sh"; member_load
TERM_PORT=${TERM_PORT:-$M_TERM_PORT}
CC_PORT=${CC_PORT:-$M_CC_PORT}
UI_PORT=${UI_PORT:-$M_UI_PORT}
API_PORT=${API_PORT:-$M_API_PORT}
CADDY_ROUTES=${CADDY_ROUTES:-1}
SFX=$M_SFX   # unit and file suffix: empty for the single brain, -<m> for a member
STAMP=$(date +%Y-%m-%d_%H%M%S)
# The bridge may run as a separate user without sudo (scripts/cc/harden-user.sh, hardening
# item 3). If the unit already names one, keep it; everything of the bridge lives in that
# user's home. The terminal door stays the brain user's (the operator's back door).
BRIDGE_USER=${BRIDGE_USER:-$(grep -oP '^User=\K.*' /etc/systemd/system/cc-bridge$SFX.service 2>/dev/null || echo "${M_BRIDGE_USER:-$BRAIN_USER}")}
BRIDGE_HOME=$(eval echo "~$BRIDGE_USER")
# The terminal door's user: the brain user on a single brain (the operator's back door); a
# member's door runs as the member's bridge user, so a member's console never holds an admin shell.
TERM_USER=${TERM_USER:-${MEMBER:+$BRIDGE_USER}}; TERM_USER=${TERM_USER:-$BRAIN_USER}
TERM_HOME=$(eval echo "~$TERM_USER")
ENV_FILE="$BRIDGE_HOME/.cc-bridge/env"
SUDO_AS_BRIDGE=""; [ "$BRIDGE_USER" != "$(id -un)" ] && SUDO_AS_BRIDGE="sudo -u $BRIDGE_USER"
# When the watcher runs this as root, files written into the brain user's home must stay theirs.
FIX_OWNER() { [ "$(id -un)" = root ] && chown -R "$BRAIN_USER":"$BRAIN_USER" "$HOME_DIR/.cc-bridge" 2>/dev/null || true; }

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

if [ -n "$MEMBER" ]; then echo "== 2/6 reasoner CLI (user $BRIDGE_USER, member $MEMBER)"; else echo "== 2/6 reasoner CLI (user $BRAIN_USER)"; fi
if [ -z "$MEMBER" ]; then   # a member's admin needs no reasoner; the member's own users get theirs below
    if [ ! -x "$HOME_DIR/.local/bin/claude" ]; then
        curl -fsSL https://claude.ai/install.sh -o /tmp/claude-install.sh
        echo "installer sha256: $(sha256sum /tmp/claude-install.sh | cut -c1-16)"
        bash /tmp/claude-install.sh
    fi
    "$HOME_DIR/.local/bin/claude" --version
fi
if [ "$BRIDGE_USER" != "$BRAIN_USER" ] && ! sudo test -x "$BRIDGE_HOME/.local/bin/claude"; then
    curl -fsSL https://claude.ai/install.sh -o /tmp/claude-install.sh
    sudo -u "$BRIDGE_USER" bash /tmp/claude-install.sh >/dev/null 2>&1 && echo "reasoner CLI installed for $BRIDGE_USER"
fi

echo "== 3/6 unit claude-tab (the door: a styled terminal that runs one thing)"
# door.sh: what the terminal runs. No argument: a persistent shell in the brain repo (the
# operator's back door). "login": Anthropic's own sign-in flow for the reasoner, and nothing
# else, so the CC sign-in card can open the door straight into it. The look follows the
# console (colours, font, no status bar) so it does not read as a terminal.
DOOR_DIR="$TERM_HOME/.cc-bridge"; DOOR_TMP=$(mktemp)
cat > "$DOOR_TMP" <<'DOOR'
#!/usr/bin/env bash
export PATH="$HOME/.local/bin:$PATH" TERM=xterm-256color
case "${1:-}" in
  login)
    clear
    printf '\n  Signing in to your own account, through the provider'"'"'s own flow.\n'
    printf '  1. A link appears below. Open it and sign in.\n  2. Copy the code it shows.\n  3. Paste the code here and press Enter.\n\n'
    # The sign-in must land with the user the bridge runs as. After harden-user.sh that is
    # not the door's user; signing in here as the door's user left the bridge disconnected
    # (observed 2026-09-21). __BRIDGE_USER__ is filled in by the installer.
    if [ "__LOGIN_USER__" != "$(id -un)" ]; then
        sudo -n -u "__LOGIN_USER__" -H env PATH="/home/__LOGIN_USER__/.local/bin:/usr/local/bin:/usr/bin:/bin" TERM="$TERM" claude auth login --claudeai \
            || printf '\n  Could not switch to the reasoner user from here. In a terminal on the box run:\n  sudo -u __LOGIN_USER__ -H claude auth login --claudeai\n'
    else
        claude auth login --claudeai
    fi
    printf '\n  Done. Close this panel and press reconnect.\n'
    sleep 3600 ;;
  codex-login)
    # The Codex seat (2026-10-15, opt-in: scripts/cc/install-codex.sh). OpenAI's own device-code
    # flow for the hands user; the token lands in that user's ~/.codex and nowhere else.
    clear
    printf '\n  Signing in the Codex seat with your own ChatGPT account, through OpenAI'"'"'s own flow.\n'
    printf '  0. Once: ChatGPT > Settings > Security > turn on Device code authorization.\n'
    printf '  1. A link and a one-time code appear below. Open the link on any device and sign in.\n'
    printf '  2. Enter the code there. This panel says when it is done.\n\n'
    # the check runs as the hands too: the door's user may not see into their home
    AS=(env); [ "__LOGIN_USER__" != "$(id -un)" ] && AS=(sudo -n -u "__LOGIN_USER__" -H env)
    AS+=(PATH="/home/__LOGIN_USER__/.local/bin:/usr/local/bin:/usr/bin:/bin" TERM="$TERM")
    if ! "${AS[@]}" test -x "/home/__LOGIN_USER__/.local/bin/codex"; then
        printf '  The Codex CLI is not installed for __LOGIN_USER__ (or this door cannot act as them).\n  On the box, from the brain repo: bash scripts/cc/install-codex.sh\n'
    else
        "${AS[@]}" codex login --device-auth \
            || printf '\n  The sign-in did not finish. In a terminal on the box run:\n  sudo -u __LOGIN_USER__ -H codex login --device-auth\n'
    fi
    printf '\n  Close this panel and press recheck beside the Codex seat.\n'
    sleep 3600 ;;
  *)
    exec tmux -f /dev/null new-session -A -s claude -c "${BRAIN_DIR:-$HOME/brain}" \; set -g status off ;;
esac
DOOR
LOGIN_USER=$(sudo grep -oP '^CC_HANDS_USER=\K.*' "$ENV_FILE" 2>/dev/null || true); LOGIN_USER=${LOGIN_USER:-$BRIDGE_USER}
sed -i "s|__LOGIN_USER__|$LOGIN_USER|g; s|__BRIDGE_USER__|$BRIDGE_USER|g" "$DOOR_TMP"
if [ "$TERM_USER" = "$(id -un)" ] || [ "$TERM_USER" = "$BRAIN_USER" ]; then
    mkdir -p "$DOOR_DIR"   # a fresh box has no state dir yet (found on e2e 2026-09-22)
    cat "$DOOR_TMP" > "$DOOR_DIR/door.sh"; chmod 755 "$DOOR_DIR/door.sh"; FIX_OWNER
else   # a member's door lives in its own user's home, written as that user
    sudo -u "$TERM_USER" mkdir -p "$DOOR_DIR"; sudo chmod 700 "$DOOR_DIR"
    sudo install -o "$TERM_USER" -g "$TERM_USER" -m 755 "$DOOR_TMP" "$DOOR_DIR/door.sh"
    mkdir -p "$HOME_DIR/.cc-bridge"; FIX_OWNER   # the installer's own log stays in the admin's home
fi
rm -f "$DOOR_TMP"
THEME='{"background":"#0f0e0c","foreground":"#e8e0d5","cursor":"#c9a96e","selectionBackground":"#3a3520","black":"#0f0e0c","brightBlack":"#6b5f52","white":"#e8e0d5","brightWhite":"#ffffff","yellow":"#c9a96e","brightYellow":"#e0c48a","blue":"#8fb3c9","green":"#9fbf8f","red":"#d08a7a"}'
# -O (--check-origin, 2026-10-16, the app lane): the terminal's websocket opens only from a page
# on the console's own host. A brain app's frame (opaque origin, Origin "null") or another site is
# refused, even though the browser would send the console login with the handshake.
sudo tee /etc/systemd/system/claude-tab$SFX.service >/dev/null <<UNIT
[Unit]
Description=Reasoner web terminal for the brain console (ttyd + tmux)${MEMBER:+, member $MEMBER}
After=network.target

[Service]
User=$TERM_USER
WorkingDirectory=$BRAIN_DIR
Environment=HOME=$TERM_HOME
Environment=PATH=$TERM_HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=TERM=xterm-256color
EnvironmentFile=-$ENV_FILE
Environment=BRAIN_DIR=$BRAIN_DIR
ExecStart=/usr/bin/ttyd -i 127.0.0.1 -p $TERM_PORT -b /claude -O -W -a -t titleFixed="brain" -t fontSize=15 -t fontFamily="DM Mono, Menlo, monospace" -t disableLeaveAlert=true -t 'theme=$THEME' /usr/bin/bash $DOOR_DIR/door.sh
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT

echo "== 4/6 unit cc-bridge (runs as $BRIDGE_USER)"
$SUDO_AS_BRIDGE mkdir -p "$BRIDGE_HOME/.cc-bridge"
# A small venv for the bridge: permitd (the permit gate for writes; stdlib-only, tiny).
if [ ! -x "$BRIDGE_HOME/.cc-bridge/venv/bin/python" ]; then
    # A fresh Ubuntu has python3 but not python3-venv (seen on e2e 2026-09-22); install it first, quietly.
    python3 -c "import ensurepip" 2>/dev/null || sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3-venv >/dev/null 2>&1
    $SUDO_AS_BRIDGE python3 -m venv "$BRIDGE_HOME/.cc-bridge/venv"
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
MEMBER_ENV=""   # a member's bridge: its name (unit names, the prompt) and its own brain's api port
[ -n "$MEMBER" ] && MEMBER_ENV="Environment=CC_MEMBER=$MEMBER
Environment=BRAIN_API_URL=http://127.0.0.1:$API_PORT
"
sudo tee /etc/systemd/system/cc-bridge$SFX.service >/dev/null <<UNIT
[Unit]
Description=CC bridge: headless reasoner turns for the brain console CC tab${MEMBER:+, member $MEMBER}
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
${MEMBER_ENV}EnvironmentFile=-$ENV_FILE
ExecStart=$BRIDGE_HOME/.cc-bridge/venv/bin/python $BRAIN_DIR/scripts/cc/cc-bridge.py
# Reload = "restart when idle" (2026-10-12): SIGHUP queues it, the bridge exits once no turn is answering.
ExecReload=/bin/kill -HUP \$MAINPID
# Only the bridge itself is stopped; cc-jobs it started keep running across restarts (2026-10-12).
KillMode=process
UMask=0002
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
    # Agent: the reasoner may fan out subagents inside one turn (2026-09-29); each subagent's own
    # edits and commands still pass the permission hook, so pre-approving the fan-out opens nothing.
    TOOLS='Read,Grep,Glob,Agent,Bash(one --agent list:*),Bash(one --agent actions search:*),Bash(one --agent actions knowledge:*),Bash(one --agent platforms:*),Bash(one-read:*)'
    # The value carries parentheses (Bash(git status *)), so it is written double-quoted:
    # systemd's EnvironmentFile strips the quotes, and a script that sources the file no
    # longer errors on them (found by the studio chat 2026-09-23).
    # Merge: the One lookups first, then whatever the owner added since (read-only verbs,
    # tool-pack entries such as mcp__...), each kept once. A rerun never drops an entry.
    EXISTING=$(sudo grep '^CC_TOOLS=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"' || true)
    MERGED=$(printf '%s,%s' "$TOOLS" "$EXISTING" | tr ',' '\n' | awk 'NF && !seen[$0]++' | paste -sd, -)
    sudo sh -c "grep -v '^CC_TOOLS=' '$ENV_FILE' > '$ENV_FILE.tmp'; echo 'CC_TOOLS=\"$MERGED\"' >> '$ENV_FILE.tmp'; mv '$ENV_FILE.tmp' '$ENV_FILE'; chown $BRIDGE_USER:$BRIDGE_USER '$ENV_FILE'; chmod 600 '$ENV_FILE'"
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
sudo tee /etc/systemd/system/cc-bridge-watch$SFX.path >/dev/null <<UNIT
[Unit]
Description=Restart cc-bridge$SFX when scripts/cc/cc-bridge.py changes (Update tab swaps files, not host services)

[Path]
PathChanged=$BRAIN_DIR/scripts/cc/cc-bridge.py
Unit=cc-bridge-watch$SFX.service

[Install]
WantedBy=multi-user.target
UNIT
sudo tee /etc/systemd/system/cc-bridge-watch$SFX.service >/dev/null <<UNIT
[Unit]
Description=Restart cc-bridge$SFX after its file changed

[Service]
Type=oneshot
ExecStart=/bin/systemctl reload-or-restart cc-bridge$SFX.service
UNIT

# The installer reruns itself when an Update changes it (units, routes, sudoers, env keys
# all live here), so the owner never types this command again after the first time.
# Runs as root with BRAIN_USER and BRIDGE_USER pinned; every step is idempotent.
sudo tee /etc/systemd/system/cc-install-watch$SFX.path >/dev/null <<UNIT
[Unit]
Description=Rerun scripts/cc/install.sh when an Update changes it

[Path]
PathChanged=$BRAIN_DIR/scripts/cc/install.sh
Unit=cc-install-watch$SFX.service

[Install]
WantedBy=multi-user.target
UNIT
MEMBER_PIN=""   # a member's rerun keeps its name, block, checkout and the Caddyfile choice
[ -n "$MEMBER" ] && MEMBER_PIN="Environment=CC_MEMBER=$MEMBER
Environment=CC_MEMBER_N=$M_N
Environment=BRAIN_DIR=$BRAIN_DIR
Environment=CADDY_ROUTES=$CADDY_ROUTES
"
sudo tee /etc/systemd/system/cc-install-watch$SFX.service >/dev/null <<UNIT
[Unit]
Description=Rerun the CC installer after its file changed

[Service]
Type=oneshot
Environment=BRAIN_USER=$BRAIN_USER
Environment=BRIDGE_USER=$BRIDGE_USER
${MEMBER_PIN}Environment=HOME=$HOME_DIR
ExecStart=/usr/bin/bash $BRAIN_DIR/scripts/cc/install.sh
StandardOutput=append:$HOME_DIR/.cc-bridge/install$SFX.log
StandardError=append:$HOME_DIR/.cc-bridge/install$SFX.log
UNIT

# Work clones (CC_WORK_DIR, if the owner set one up): pull each repository every five
# minutes so the reasoner never builds on a stale copy. Fast-forward only; a clone with
# local changes is left alone and named in the log.
WORK_DIR_ENV=$(sudo grep -oP '^CC_WORK_DIR=\K.*' "$ENV_FILE" 2>/dev/null || true)
if [ -n "$WORK_DIR_ENV" ] && sudo test -d "$WORK_DIR_ENV"; then
    sudo tee /etc/systemd/system/cc-work-pull$SFX.service >/dev/null <<UNIT
[Unit]
Description=Fast-forward the CC work clones from their remotes

[Service]
Type=oneshot
User=$BRIDGE_USER
Environment=HOME=$BRIDGE_HOME
ExecStart=/usr/bin/bash -c 'find "$WORK_DIR_ENV" -maxdepth 6 -name .git -type d -prune 2>/dev/null | while read -r g; do d=\$(dirname "\$g"); if [ -n "\$(git -C "\$d" status --porcelain)" ]; then echo "\$(basename "\$d"): local changes, not pulled"; continue; fi; git -C "\$d" pull -q --ff-only 2>/dev/null || echo "\$(basename "\$d"): pull failed"; done'
UNIT
    sudo tee /etc/systemd/system/cc-work-pull$SFX.timer >/dev/null <<UNIT
[Unit]
Description=Every five minutes: refresh the CC work clones

[Timer]
OnBootSec=3min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
UNIT
    sudo systemctl daemon-reload; sudo systemctl enable --now cc-work-pull$SFX.timer >/dev/null 2>&1
    echo "work clones at $WORK_DIR_ENV refresh every 5 min (cc-work-pull$SFX.timer)"
fi

echo "== 4c/6 hands on the box (only when the bridge runs as a user without sudo)"
# The reasoner may edit files and run commands on this box; each call the person has not
# already allowed raises a card in the chat (PermissionRequest hook -> bridge -> card).
# Root is limited to a fixed list of verbs, each also behind a card. When the bridge runs as
# the brain user (who has sudo) this lane stays off: a reasoner with general sudo is the
# whole server, card or no card.
if [ "$BRIDGE_USER" != "$BRAIN_USER" ] && ! sudo -l -U "$BRIDGE_USER" 2>/dev/null | grep -q "(ALL"; then
    if [ -z "$MEMBER" ]; then
        sed "s|__BRAIN_DIR__|$BRAIN_DIR|" "$BRAIN_DIR/scripts/cc/brain-write.sh" | sudo tee /usr/local/bin/brain-write >/dev/null
        sudo chown root:root /usr/local/bin/brain-write; sudo chmod 755 /usr/local/bin/brain-write
        HELPER_NOTE="; helper /usr/local/bin/brain-write"
        VERBS="/usr/bin/systemctl restart cc-bridge, /usr/bin/systemctl restart claude-tab, /usr/bin/systemctl status *, /usr/bin/journalctl *, /usr/bin/docker ps *, /usr/bin/docker compose --project-directory $BRAIN_DIR logs *, /usr/bin/bash $BRAIN_DIR/scripts/update_brain.sh, /usr/local/bin/brain-write *"
    else
        # A member shares the box: no wildcard verb (journalctl, status * and docker ps read other
        # members' units), no root write into the checkout and no root Update (either one could
        # rewrite what root runs next). Its own two units only, exact command lines.
        HELPER_NOTE=""
        VERBS="/usr/bin/systemctl restart cc-bridge$SFX, /usr/bin/systemctl restart claude-tab$SFX, /usr/bin/systemctl status cc-bridge$SFX, /usr/bin/systemctl status claude-tab$SFX"
    fi
    sudo tee /etc/sudoers.d/cc-bridge$SFX.tmp >/dev/null <<SUDOERS
# The CC bridge user's root verbs (scripts/cc/install.sh). Each is also behind a card in the chat.
$BRIDGE_USER ALL=(root) NOPASSWD: $VERBS
SUDOERS
    if sudo visudo -cf /etc/sudoers.d/cc-bridge$SFX.tmp >/dev/null; then
        sudo chmod 440 /etc/sudoers.d/cc-bridge$SFX.tmp && sudo mv /etc/sudoers.d/cc-bridge$SFX.tmp /etc/sudoers.d/cc-bridge$SFX
        sudo grep -q "^CC_BOX=" "$ENV_FILE" 2>/dev/null || echo "CC_BOX=1" | sudo tee -a "$ENV_FILE" >/dev/null
        # Looking around needs no card: read-only shell verbs join the allowed list (the reasoner
        # already reads files in its working directories freely; these only save clicks). No cat/head/
        # grep here: they would read outside those directories without a card. Writes and root still card.
        RO='Bash(ls:*),Bash(wc:*),Bash(stat:*),Bash(file:*),Bash(pwd),Bash(id:*),Bash(whoami),Bash(date:*),Bash(df:*),Bash(du:*),Bash(ps:*),Bash(uptime),Bash(git status:*),Bash(git log:*),Bash(git diff:*),Bash(git show:*),Bash(git branch:*),Bash(git -C * status:*),Bash(git -C * log:*),Bash(git -C * diff:*),Bash(git -C * show:*),Bash(systemctl status:*),Bash(systemctl is-active:*)'
        # No One key means no CC_TOOLS line yet (found on e2e 2026-09-22: the missing line
        # aborted the whole installer under set -e); seed it with the unit's default.
        CUR=$(sudo grep '^CC_TOOLS=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"' || true)
        [ -n "$CUR" ] || CUR="Read,Grep,Glob"
        if ! printf '%s' "$CUR" | grep -q 'Bash(git status'; then
            sudo sh -c "grep -v '^CC_TOOLS=' '$ENV_FILE' > '$ENV_FILE.tmp'; echo 'CC_TOOLS=\"$CUR,$RO\"' >> '$ENV_FILE.tmp'; mv '$ENV_FILE.tmp' '$ENV_FILE'; chown $BRIDGE_USER:$BRIDGE_USER '$ENV_FILE'; chmod 600 '$ENV_FILE'"
            echo "read-only shell verbs allowed without a card (ls, git status/log/diff, systemctl status, ...; file contents go through Read, which stays inside the working directories)"
        fi
        # cc-job: commands that outlive a turn, started through the bridge (scripts/cc/cc-job.py).
        $SUDO_AS_BRIDGE mkdir -p "$BRIDGE_HOME/.local/bin" "$BRIDGE_HOME/out" "$BRIDGE_HOME/in"
        $SUDO_AS_BRIDGE cp "$BRAIN_DIR/scripts/cc/cc-job.py" "$BRIDGE_HOME/.local/bin/cc-job"
        $SUDO_AS_BRIDGE cp "$BRAIN_DIR/scripts/cc/cc_halt.py" "$BRIDGE_HOME/.local/bin/cc_halt.py"   # the kill switch's module, imported by cc-job (2026-10-25)
        $SUDO_AS_BRIDGE chmod 755 "$BRIDGE_HOME/.local/bin/cc-job"
        echo "box hands on: edits and commands raise a card; root verbs in /etc/sudoers.d/cc-bridge$SFX$HELPER_NOTE; cc-job installed"
    else
        sudo rm -f /etc/sudoers.d/cc-bridge$SFX.tmp; echo "sudoers check failed; box hands left off"
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
    sudo python3 - "$CADDYFILE" "$name" "$base" "$port" "$UI_PORT" "$M_TOKEN_VAR" <<'PY'
import sys, re
path, name, base, port, ui_port, token_var = sys.argv[1:7]
text = open(path).read()
# Insert inside the console host's authenticated block, before its ui reverse_proxy
# (the LAST reverse_proxy to the ui port, 3010 on a single brain, in the file).
needle = f"reverse_proxy localhost:{ui_port}"
idx = text.rfind(needle)
if idx < 0:
    sys.exit("could not find the console ui reverse_proxy line; add the route by hand (docs/CC.md)")
ls = text.rfind("\n", 0, idx) + 1
indent = re.match(r"[ \t]*", text[ls:idx]).group(0)
# The operator token (2026-09-27): Caddy adds it to every request that passed the owner's login,
# from its own environment (/etc/caddy/cc.env, root only, written by split-hands.sh); a process
# on the box cannot forge it. With no token set the header is empty and the bridge does not check.
block = f"{indent}@{name} path {base} {base}/*\n{indent}handle @{name} {{\n{indent}    reverse_proxy localhost:{port} {{\n{indent}        header_up X-CC-Operator {{${token_var}}}\n{indent}    }}\n{indent}}}\n"
open(path, "w").write(text[:ls] + block + text[ls:])
print(f"inserted {base} route")
PY
    if sudo caddy validate --config "$CADDYFILE" --adapter caddyfile >/dev/null 2>&1; then
        sudo systemctl reload caddy; echo "caddy reloaded"
    else
        echo "caddy validate FAILED, restoring backup"; sudo cp "$CADDYFILE.bak.$STAMP" "$CADDYFILE"; exit 1
    fi
}
if [ "$CADDY_ROUTES" = 1 ]; then
    add_route claude /claude "$TERM_PORT"
    add_route cc /cc "$CC_PORT"
else
    echo "CADDY_ROUTES=0: Caddyfile untouched (the site block from scripts/multi/add-member.sh carries both routes)"
fi

echo "== 6/6 start and check"
sudo systemctl daemon-reload
sudo systemctl enable claude-tab$SFX cc-bridge$SFX cc-bridge-watch$SFX.path cc-install-watch$SFX.path >/dev/null 2>&1
sudo systemctl restart claude-tab$SFX cc-bridge$SFX
sudo systemctl restart cc-bridge-watch$SFX.path cc-install-watch$SFX.path
sleep 2
# A path unit restarted from inside the very script it watches came up inactive once
# (observed 2026-09-22); a plain start afterwards is enough.
for u in cc-bridge-watch$SFX.path cc-install-watch$SFX.path; do
    systemctl is-active --quiet "$u" || sudo systemctl start "$u"
done
echo "claude-tab$SFX: $(systemctl is-active claude-tab$SFX)   cc-bridge$SFX: $(systemctl is-active cc-bridge$SFX)   watchers: $(systemctl is-active cc-bridge-watch$SFX.path) $(systemctl is-active cc-install-watch$SFX.path)   work-pull: $(systemctl is-active cc-work-pull$SFX.timer 2>/dev/null | head -1)"
echo "terminal  /claude/ -> HTTP $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$TERM_PORT/claude/)"
echo "bridge    /cc/health -> $(curl -s http://127.0.0.1:$CC_PORT/cc/health | cut -c1-200)"
HOST=$(grep -oE "^console\.${MEMBER:+$MEMBER\.}[a-z0-9.-]+" "$CADDYFILE" | head -1 || true)   # a member's block may not be pasted yet
echo
echo "Done. Now: BRAIN_CC_ENABLED=true in $BRAIN_DIR/.env (sudo), then Update tab or"
echo "'docker compose up -d api', then open https://$HOST/cc and press Connect."
