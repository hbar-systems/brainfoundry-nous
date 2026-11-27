#!/usr/bin/env bash
# brain-tide: update the brain at a quiet moment (AUTO-UPDATE-1, 2026-11-27, docs/TIDE.md).
# Installed by scripts/tide/install-tide.sh to /usr/local/sbin/brain-tide (root 755) and started every five
# minutes by brain-tide.timer. A fixed copy: a later change here reaches root only when the owner reruns
# the installer.
#
#   brain-tide              (the timer's unit) fetch, ask the bridge, and at a quiet moment run the Update
#   brain-tide --dry-run    fetch and ask only; prints the bridge's answer; never updates
#
# What it runs is the brain's own Update, nothing more: scripts/update_brain.sh of the checkout, as the
# checkout's owner (root on hbar's box, where the checkout is root's; runuser otherwise), the same script,
# checks and lock (scripts/update_lock.sh) as the Update press and the card's `sudo bash
# scripts/update_brain.sh`. Its output goes to /var/lib/brain-tide/update.log.
#
# Whom it believes: the bridge's answer only gates the moment; it cannot change what runs. The answer is
# asked of the process listening on 127.0.0.1:$CC_PORT only if that socket belongs to $BRIDGE_USER (so a
# program that took the port while the bridge restarted cannot say "quiet"). The bridge answers this
# door only to uid 0 on loopback. Before anything runs it refuses a checkout whose host-run files (the
# update, backup and lock scripts, the compose files, .env, .git and its hooks) are not the owner's or
# root's, are world-writable, or group-writable by a group other than an empty root group, and a local
# change to tracked scripts/ or docker-compose.yml.
set -euo pipefail
umask 022
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
BRAIN_DIR=${BRAIN_DIR:-/home/hbar/brain}
CC_PORT=${CC_PORT:-7682}
BRIDGE_USER=${BRIDGE_USER:-cc}
TAB_USER=${TAB_USER:-}
STATE=${TIDE_STATE:-/var/lib/brain-tide}
LOG=$STATE/update.log
TRACE=$STATE/tide.log
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
[ $# -le 1 ] || { echo "usage: brain-tide [--dry-run]" >&2; exit 2; }
[ $# -eq 0 ] || [ "$DRY" = 1 ] || { echo "usage: brain-tide [--dry-run]" >&2; exit 2; }

refuse() { echo "refused: $*" >&2; note "refused: $*"; exit 2; }
note() {
    [ -d "$STATE" ] || return 0
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >> "$TRACE"
    # keep the trace short: the last 2000 lines
    if [ "$(wc -l < "$TRACE")" -gt 2400 ]; then tail -n 2000 "$TRACE" > "$TRACE.tmp" && mv -f "$TRACE.tmp" "$TRACE"; fi
}
[ "$(id -u)" = 0 ] || { echo "refused: root only (the timer's unit, or sudo for --dry-run)" >&2; exit 2; }
if [ "$DRY" = 0 ] && [ -z "${INVOCATION_ID:-}" ]; then
    echo "refused: the update runs from brain-tide.service only; use --dry-run to ask" >&2; exit 2
fi
install -d -o root -g root -m 755 "$STATE"

[ -d "$BRAIN_DIR" ] && [ ! -L "$BRAIN_DIR" ] || refuse "$BRAIN_DIR is not a directory"
OWNER_UID=$(stat -c %u "$BRAIN_DIR"); OWNER=$(stat -c %U "$BRAIN_DIR")
case "$OWNER" in "$BRIDGE_USER"|hands|*-cc|*-hands) refuse "$BRAIN_DIR belongs to $OWNER, a user the reasoner runs as" ;; esac
ROOT_GROUP_EMPTY=0
[ -z "$(getent group root | cut -d: -f4)" ] && ROOT_GROUP_EMPTY=1

host_run_ok() {
    local p=$1 uid gid mode
    [ -e "$p" ] || [ -L "$p" ] || return 0
    [ ! -L "$p" ] || refuse "$p is a symlink"
    uid=$(stat -c %u "$p"); gid=$(stat -c %g "$p"); mode=$(stat -c %a "$p")
    [ "$uid" = "$OWNER_UID" ] || [ "$uid" = 0 ] || refuse "$p does not belong to $OWNER or root"
    (( (8#$mode & 8#002) == 0 )) || refuse "$p is world-writable ($mode)"
    if (( (8#$mode & 8#020) != 0 )); then
        [ "$gid" = 0 ] && [ "$ROOT_GROUP_EMPTY" = 1 ] || refuse "$p is group-writable ($mode, group $(stat -c %G "$p"))"
    fi
}
as_owner() {
    local home
    home=$(getent passwd "$OWNER" | cut -d: -f6)
    if [ "$OWNER_UID" = 0 ]; then env -i HOME="$home" PATH="$PATH" LANG=C.UTF-8 "$@"
    else runuser -u "$OWNER" -- env -i HOME="$home" PATH="$PATH" LANG=C.UTF-8 "$@"; fi
}
checks() {
    local p
    for p in "$BRAIN_DIR" "$BRAIN_DIR/.git" "$BRAIN_DIR/.git/config" "$BRAIN_DIR/.git/hooks" "$BRAIN_DIR/scripts" \
             "$BRAIN_DIR/scripts/update_brain.sh" "$BRAIN_DIR/scripts/backup_brain.sh" "$BRAIN_DIR/scripts/update_lock.sh" \
             "$BRAIN_DIR/docker-compose.yml" "$BRAIN_DIR/docker-compose.override.yml" "$BRAIN_DIR/.env"; do
        host_run_ok "$p"
    done
    [ -f "$BRAIN_DIR/scripts/update_brain.sh" ] || refuse "$BRAIN_DIR/scripts/update_brain.sh is missing"
    # a hook in .git/hooks runs on every git command of the update
    while IFS= read -r -d '' p; do host_run_ok "$p"; done < <(find "$BRAIN_DIR/.git/hooks" -mindepth 1 ! -name '*.sample' -print0 2>/dev/null)
    as_owner git -c "safe.directory=$BRAIN_DIR" -C "$BRAIN_DIR" diff --quiet HEAD -- scripts docker-compose.yml \
        || refuse "tracked scripts/ or docker-compose.yml changed locally in $BRAIN_DIR; the owner looks first"
}
git_o() { as_owner git -c "safe.directory=$BRAIN_DIR" -C "$BRAIN_DIR" "$@"; }

checks
as_owner timeout 90 git -c "safe.directory=$BRAIN_DIR" -C "$BRAIN_DIR" fetch origin --quiet || { note "no: git fetch failed (offline?)"; [ "$DRY" = 1 ] && echo "git fetch failed"; exit 0; }
HEAD=$(git_o rev-parse HEAD)
LATEST=$(git_o rev-parse origin/main)
N=$(git_o rev-list --count HEAD..origin/main)

# the listener on the bridge's port must be the bridge's user
BRIDGE_UID=$(id -u "$BRIDGE_USER" 2>/dev/null) || refuse "no user $BRIDGE_USER"
LUID=$(ss -Hltne "sport = :$CC_PORT" 2>/dev/null | grep -o 'uid:[0-9]*' | head -1 | cut -d: -f2 || true)
if [ -z "$LUID" ]; then note "no: nothing listens on 127.0.0.1:$CC_PORT (the bridge is restarting?)"; [ "$DRY" = 1 ] && echo "the bridge is not listening"; exit 0; fi
[ "$LUID" = "$BRIDGE_UID" ] || refuse "127.0.0.1:$CC_PORT belongs to uid $LUID, not $BRIDGE_USER"

# the terminal pane's last activity (tmux of the tab's user): input or output in it is his work
TERM_AT=0
if [ -n "$TAB_USER" ] && id "$TAB_USER" >/dev/null 2>&1; then
    TH=$(getent passwd "$TAB_USER" | cut -d: -f6)
    for fmt in '#{session_activity}' '#{client_activity}'; do
        cmd=list-sessions; [ "$fmt" = '#{client_activity}' ] && cmd=list-clients
        while read -r t; do
            [[ "$t" =~ ^[0-9]+$ ]] && [ "$t" -gt "$TERM_AT" ] && TERM_AT=$t
        done < <(timeout 5 runuser -u "$TAB_USER" -- env -i HOME="$TH" PATH="$PATH" tmux "$cmd" -F "$fmt" 2>/dev/null || true)
    done
fi

BASE="http://127.0.0.1:$CC_PORT/cc/autoupdate"
field() { python3 -I -c 'import json,sys; d=json.loads(sys.argv[1]); v=d.get(sys.argv[2]); print("" if v is None else (str(v).lower() if isinstance(v,bool) else v))' "$1" "$2"; }
ANS=$(curl -fsS --max-time 30 "$BASE/quiet?terminal=$TERM_AT" 2>/dev/null) || { note "no: the bridge did not answer"; [ "$DRY" = 1 ] && echo "the bridge did not answer"; exit 0; }
WHY=$(field "$ANS" why)
if [ "$DRY" = 1 ]; then
    echo "checkout $BRAIN_DIR (owner $OWNER): ${HEAD:0:7}, origin/main ${LATEST:0:7}, $N behind; terminal activity $TERM_AT"
    echo "bridge: $WHY"
    exit 0
fi
if [ "$(field "$ANS" quiet)" != "true" ]; then note "no: $WHY"; exit 0; fi
[ "$N" -gt 0 ] && [ "$(field "$ANS" latest)" = "$LATEST" ] && [ "$(field "$ANS" head)" = "$HEAD" ] \
    || { note "no: the bridge saw another version (${HEAD:0:7}..${LATEST:0:7})"; exit 0; }

BEGIN=$(curl -fsS --max-time 30 -X POST -H 'Content-Type: application/json' \
    -d "{\"from\":\"$HEAD\",\"to\":\"$LATEST\",\"terminal\":$TERM_AT}" "$BASE/begin" 2>/dev/null) \
    || { note "no: the bridge refused to begin (asked again: not quiet any more)"; exit 0; }
note "yes: updating ${HEAD:0:7} -> ${LATEST:0:7} ($N commits)"

rc=0
{
    echo ""
    echo "==> brain-tide $(date -u +%Y-%m-%dT%H:%M:%SZ): ${HEAD:0:7} -> ${LATEST:0:7}, $N commits, as $OWNER"
    ( checks ) && as_owner bash "$BRAIN_DIR/scripts/update_brain.sh" "$BRAIN_DIR"
} >> "$LOG" 2>&1 || rc=$?
chmod 644 "$LOG"
HEAD_AFTER=$(git_o rev-parse HEAD 2>/dev/null || echo "")
printf '{"at":"%s","from":"%s","to":"%s","head":"%s","rc":%d}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$HEAD" "$LATEST" "$HEAD_AFTER" "$rc" > "$STATE/last.json"
note "done: rc=$rc head ${HEAD_AFTER:0:7}"

# the line after: the bridge may be restarting (an update that changed it), so try for ten minutes
for _ in $(seq 1 40); do
    if curl -fsS --max-time 20 -X POST -H 'Content-Type: application/json' \
        -d "{\"rc\":$rc,\"head\":\"$HEAD_AFTER\",\"to\":\"$LATEST\"}" "$BASE/end" >/dev/null 2>&1; then
        note "reported to the bridge"; exit "$rc"
    fi
    sleep 15
done
note "the bridge did not take the report in ten minutes; it ends the run as unknown after 40 min"
exit "$rc"
