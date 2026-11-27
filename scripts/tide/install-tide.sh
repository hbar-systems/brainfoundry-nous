#!/usr/bin/env bash
# scripts/tide/install-tide.sh: install the Tide's root timer once (AUTO-UPDATE-1, 2026-11-27, docs/TIDE.md).
#
#   sudo bash scripts/tide/install-tide.sh --dry-run      # prints every action, touches nothing
#   sudo bash scripts/tide/install-tide.sh --apply        # installs and starts the timer, then asks once
#   sudo bash scripts/tide/install-tide.sh --remove       # stops and removes the timer, the unit and the copy
#
# Installs:
#   /usr/local/sbin/brain-tide                 root 755, a copy of scripts/tide/brain-tide.sh
#   /etc/systemd/system/brain-tide.service     root 644, BRAIN_DIR, the bridge's port and user, the tab's user
#   /etc/systemd/system/brain-tide.timer       root 644, every five minutes
#   /var/lib/brain-tide                        root 755 (update.log, tide.log, last.json)
# It touches no sudoers file and gives the bridge or the hands no new verb. Installing changes nothing by
# itself: the brain updates only after the owner turns the switch on /update on. Rerun --apply after an
# Update that changes scripts/tide/ (the timer runs the fixed copy, not the checkout's file).
# A member brain is refused: member brains keep their own Update door (scripts/member-update-door.sh).
set -euo pipefail
REPO=$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)
MODE=${1:-}
case "$MODE" in --dry-run|--apply|--remove) ;; *) echo "usage: sudo bash $0 --dry-run|--apply|--remove" >&2; exit 2 ;; esac
[ "$(id -u)" = 0 ] || { echo "refused: run with sudo" >&2; exit 2; }
SRC=$REPO/scripts/tide
BIN=/usr/local/sbin/brain-tide
UNITS=/etc/systemd/system
run() { echo "+ $*"; [ "$MODE" = --dry-run ] || "$@"; }

if [ "$MODE" = --remove ]; then
    run systemctl disable --now brain-tide.timer
    run rm -f "$UNITS/brain-tide.timer" "$UNITS/brain-tide.service" "$BIN"
    run systemctl daemon-reload
    echo "removed (the logs in /var/lib/brain-tide stay)"
    exit 0
fi

# what the bridge's own unit says: its user, its port, its checkout; a member's bridge is refused
BRIDGE_USER=$(systemctl show cc-bridge.service -p User --value)
ENVS=$(systemctl show cc-bridge.service -p Environment --value)
CC_PORT=$(tr ' ' '\n' <<<"$ENVS" | sed -n 's/^CC_PORT=//p' | head -1)
BRAIN_DIR=$(tr ' ' '\n' <<<"$ENVS" | sed -n 's/^CC_CWD=//p' | head -1)
TAB_USER=$(systemctl show claude-tab.service -p User --value 2>/dev/null || true)
[ -n "$BRIDGE_USER" ] && [ -n "$CC_PORT" ] && [ -n "$BRAIN_DIR" ] || { echo "refused: cc-bridge.service names no User, CC_PORT or CC_CWD" >&2; exit 1; }
if tr ' ' '\n' <<<"$ENVS" | grep -q '^CC_MEMBER=.'; then echo "refused: this is a member's bridge; members keep their own Update door" >&2; exit 1; fi
[[ "$CC_PORT" =~ ^[0-9]+$ ]] || { echo "refused: CC_PORT is not a number" >&2; exit 1; }
[[ "$BRAIN_DIR" =~ ^/[A-Za-z0-9._/-]+$ ]] || { echo "refused: odd checkout path $BRAIN_DIR" >&2; exit 1; }
[ -f "$BRAIN_DIR/scripts/update_brain.sh" ] || { echo "refused: no scripts/update_brain.sh in $BRAIN_DIR" >&2; exit 1; }
echo "== Tide for $BRAIN_DIR: bridge $BRIDGE_USER on 127.0.0.1:$CC_PORT, terminal of ${TAB_USER:-nobody} ($([ "$MODE" = --apply ] && echo apply || echo 'dry run: nothing is changed'))"

render() {
    sed -e "s#@BRAIN_DIR@#$BRAIN_DIR#g" -e "s#@CC_PORT@#$CC_PORT#g" -e "s#@BRIDGE_USER@#$BRIDGE_USER#g" -e "s#@TAB_USER@#$TAB_USER#g" "$1"
}
run install -o root -g root -m 755 "$SRC/brain-tide.sh" "$BIN"
run install -d -o root -g root -m 755 /var/lib/brain-tide
echo "+ write $UNITS/brain-tide.service (BRAIN_DIR=$BRAIN_DIR CC_PORT=$CC_PORT BRIDGE_USER=$BRIDGE_USER TAB_USER=$TAB_USER)"
echo "+ write $UNITS/brain-tide.timer"
if [ "$MODE" = --apply ]; then
    render "$SRC/brain-tide.service" > "$UNITS/brain-tide.service.tmp" && mv -f "$UNITS/brain-tide.service.tmp" "$UNITS/brain-tide.service"
    install -o root -g root -m 644 "$SRC/brain-tide.timer" "$UNITS/brain-tide.timer"
    chmod 644 "$UNITS/brain-tide.service"
fi
run systemctl daemon-reload
run systemctl enable --now brain-tide.timer
if [ "$MODE" = --apply ]; then
    echo "== one look now (asks only, never updates):"
    env BRAIN_DIR="$BRAIN_DIR" CC_PORT="$CC_PORT" BRIDGE_USER="$BRIDGE_USER" TAB_USER="$TAB_USER" "$BIN" --dry-run || true
    echo "== timer: $(systemctl is-active brain-tide.timer), next: $(systemctl show brain-tide.timer -p NextElapseUSecRealtime --value)"
    echo "Installed. Nothing updates until the switch on /update is on."
else
    echo "Dry run: nothing was changed. Rerun with --apply."
fi
