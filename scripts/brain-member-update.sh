#!/usr/bin/env bash
# brain-member-update: one member's Update door on a shared box. Created 2026-10-21
# (docs/MULTI_INSTANCE.md "Update from the console"). Installed by scripts/member-update-door.sh to
# /usr/local/sbin/brain-member-update (root, 755). The member's bridge <m>-cc may run, by sudoers,
# exactly these two command lines and nothing else:
#
#   brain-member-update <m>         update /srv/brains/<m>: scripts/update_brain.sh, as the checkout's
#                                   owner (the admin), in a transient unit brain-update-<m> so a bridge
#                                   restart mid-update (an Update that changes cc-bridge.py) cannot
#                                   kill it; output to /var/lib/brain-update/<m>/update.log, whose last
#                                   line is "brain-update rc=<n>"
#   brain-member-update <m> check   git fetch in that checkout, as the admin (the page's "behind by")
#
# The third mode, "<m> run", is the unit's own body; sudoers does not list it.
# It never takes a path, a command or an environment from the caller. Before anything runs it
# refuses a checkout whose host-run files (the update and backup scripts, the compose files, .env,
# .git) are not the admin's or root's, or are group- or world-writable, a symlink anywhere in the
# directories the member's api writes (brain-apps, extensions, prepared_docs, input_samples), and a
# local change to tracked scripts/ or docker-compose.yml: those are the ways a member's own api
# (root in its container) or hands could make the admin run something of theirs.
set -euo pipefail
umask 027
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
BRAINS_ROOT=/srv/brains
STATE_ROOT=/var/lib/brain-update
RESERVED="hbar cc hands root admin brain brains ollama caddy console www api test"   # = scripts/cc/member.sh

refuse() { echo "refused: $*" >&2; exit 2; }

[ $# -ge 1 ] && [ $# -le 2 ] || refuse "usage: brain-member-update <handle> [check]"
M=$1; MODE=${2:-update}
[[ "$M" =~ ^[a-z][a-z0-9]{1,15}$ ]] || refuse "bad handle"
case " $RESERVED " in *" $M "*) refuse "reserved handle: $M" ;; esac
case "$MODE" in update|check|run) ;; *) refuse "unknown mode: $MODE" ;; esac
[ "$(id -u)" = 0 ] || refuse "root only (through sudo)"

DIR=$BRAINS_ROOT/$M
UNIT=brain-update-$M
LOG=$STATE_ROOT/$M/update.log
[ -f "$BRAINS_ROOT/members.tsv" ] && awk -v h="$M" '$1==h {f=1} END {exit !f}' "$BRAINS_ROOT/members.tsv" \
    || refuse "$M is not in $BRAINS_ROOT/members.tsv"
[ -d "$DIR" ] && [ ! -L "$DIR" ] || refuse "$DIR is not a directory"
ADMIN=$(stat -c %U "$DIR"); ADMIN_UID=$(stat -c %u "$DIR")
[ "$ADMIN_UID" != 0 ] || refuse "$DIR belongs to root; a member's checkout belongs to the admin"
case "$ADMIN" in "$M-cc"|"$M-hands") refuse "$DIR belongs to the member's own user $ADMIN" ;; esac

CALLER=${SUDO_USER:-root}
if [ "$MODE" = run ]; then
    # only systemd starts the body (systemd-run below); sudo never passes INVOCATION_ID
    [ -n "${INVOCATION_ID:-}" ] && [ -z "${SUDO_USER:-}" ] || refuse "run is the unit's body, not a door"
else
    case "$CALLER" in "$M-cc"|"$ADMIN"|root) ;; *) refuse "$CALLER may not update $M" ;; esac
fi

# A file root's update makes the admin run, or a directory holding one: the admin's or root's,
# a real file or directory, never group- or world-writable.
host_run_ok() {
    local p=$1 uid mode
    [ -e "$p" ] || return 0
    [ ! -L "$p" ] || refuse "$p is a symlink"
    uid=$(stat -c %u "$p"); mode=$(stat -c %a "$p")
    [ "$uid" = "$ADMIN_UID" ] || [ "$uid" = 0 ] || refuse "$p does not belong to $ADMIN or root"
    (( (8#$mode & 8#022) == 0 )) || refuse "$p is group- or world-writable ($mode)"
}
checks() {
    host_run_ok "$BRAINS_ROOT"
    local p
    for p in "$DIR" "$DIR/.git" "$DIR/.git/config" "$DIR/.git/hooks" "$DIR/scripts" "$DIR/scripts/update_brain.sh" \
             "$DIR/scripts/backup_brain.sh" "$DIR/docker-compose.yml" "$DIR/docker-compose.override.yml" "$DIR/.env"; do
        host_run_ok "$p"
    done
    [ -f "$DIR/scripts/update_brain.sh" ] || refuse "$DIR/scripts/update_brain.sh is missing"
    local d found=""
    for d in brain-apps extensions prepared_docs input_samples; do
        [ -d "$DIR/$d" ] || continue
        found=$(find "$DIR/$d" -type l -print -quit)
        [ -z "$found" ] || refuse "symlink in a directory the api writes: ${found#"$DIR/"}"
    done
    as_admin git -C "$DIR" diff --quiet HEAD -- scripts docker-compose.yml \
        || refuse "tracked scripts/ or docker-compose.yml changed locally in $DIR; the admin looks first"
}
as_admin() {
    local home
    home=$(getent passwd "$ADMIN" | cut -d: -f6)
    runuser -u "$ADMIN" -- env -i HOME="$home" PATH="$PATH" LANG=C.UTF-8 "$@"
}

case "$MODE" in
check)
    checks
    timeout 60 runuser -u "$ADMIN" -- env -i HOME="$(getent passwd "$ADMIN" | cut -d: -f6)" PATH="$PATH" \
        git -C "$DIR" fetch origin --quiet || refuse "git fetch failed (offline?)"
    echo "fetched $M"
    ;;
update)
    checks
    if systemctl is-active --quiet "$UNIT"; then refuse "an update of $M is already running ($UNIT)"; fi
    systemctl reset-failed "$UNIT" 2>/dev/null || true
    mkdir -p "$STATE_ROOT/$M"
    chmod 711 "$STATE_ROOT"; chgrp "$M-brain" "$STATE_ROOT/$M"; chmod 750 "$STATE_ROOT/$M"
    rm -f "$LOG"; : > "$LOG"; chgrp "$M-brain" "$LOG"; chmod 640 "$LOG"
    SELF=$(readlink -f "$0")
    systemd-run --unit="$UNIT" --collect --quiet -p RuntimeMaxSec=1800 -p "Description=Update the brain of member $M" \
        "$SELF" "$M" run
    echo "started $UNIT; log $LOG"
    ;;
run)
    exec >>"$LOG" 2>&1
    echo "==> brain-update $M by the console, $(date -u +%Y-%m-%dT%H:%M:%SZ), as $ADMIN"
    rc=0
    ( checks ) || rc=$?
    if [ "$rc" = 0 ]; then as_admin bash "$DIR/scripts/update_brain.sh" "$DIR" || rc=$?; fi
    echo "brain-update rc=$rc"
    exit "$rc"
    ;;
esac
