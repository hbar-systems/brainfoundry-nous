#!/usr/bin/env bash
# scripts/member-update-door.sh — give one member's console Update button its door. Created 2026-10-21
# (docs/MULTI_INSTANCE.md "Update from the console"). scripts/add-member.sh runs it for every new
# member; run it by hand for a member added before 2026-10-21, and again after an Update that
# changes scripts/brain-member-update.sh (it refreshes the one helper of the box).
#
#   bash scripts/member-update-door.sh <handle> --dry-run     # prints every action, touches nothing
#   bash scripts/member-update-door.sh <handle> --apply
#
# Run as the box's admin (sudo). It installs:
#   /usr/local/sbin/brain-member-update   root 755, from this checkout (one per box, every member uses it)
#   /var/lib/brain-update                 root 711 (each member's log dir is made by the helper, 750)
#   /etc/sudoers.d/brain-update-<m>       <m>-cc may run exactly "brain-member-update <m>" and
#                                         "brain-member-update <m> check", nothing else
# The member's api keeps no docker socket: the button goes through the member's bridge (/cc/update).
set -euo pipefail

usage() { echo "usage: $0 <handle> --dry-run|--apply" >&2; exit 2; }
[ $# -eq 2 ] || usage
HANDLE=$1
case "$2" in --dry-run) APPLY=0 ;; --apply) APPLY=1 ;; *) usage ;; esac

REPO=$(cd "$(dirname "$0")/.." && pwd)
. "$REPO/scripts/cc/member.sh"
member_handle_ok "$HANDLE" || { echo "refused: bad member handle: $HANDLE" >&2; exit 2; }
HELPER=/usr/local/sbin/brain-member-update
SUDOERS=/etc/sudoers.d/brain-update-$HANDLE
BRIDGE_USER=$HANDLE-cc

run() { echo "+ $*"; [ "$APPLY" = 1 ] && "$@"; return 0; }

echo "== Update door for member $HANDLE ($([ "$APPLY" = 1 ] && echo apply || echo 'dry run: nothing is changed'))"
if [ "$APPLY" = 1 ]; then
    id "$BRIDGE_USER" >/dev/null 2>&1 || { echo "refused: no user $BRIDGE_USER (add the member first)" >&2; exit 1; }
    getent group "$HANDLE-brain" >/dev/null 2>&1 || { echo "refused: no group $HANDLE-brain" >&2; exit 1; }
fi
run sudo install -o root -g root -m 755 "$REPO/scripts/brain-member-update.sh" "$HELPER"
run sudo install -d -o root -g root -m 711 /var/lib/brain-update
LINE="$BRIDGE_USER ALL=(root) NOPASSWD: $HELPER $HANDLE, $HELPER $HANDLE check"
echo "    | $LINE"
if [ "$APPLY" = 1 ]; then
    printf '# The Update door of member %s (scripts/member-update-door.sh): two exact command lines.\n%s\n' "$HANDLE" "$LINE" \
        | sudo tee "$SUDOERS.tmp" >/dev/null
    sudo chmod 440 "$SUDOERS.tmp"
    if sudo visudo -cf "$SUDOERS.tmp" >/dev/null; then sudo mv -f "$SUDOERS.tmp" "$SUDOERS"
    else sudo rm -f "$SUDOERS.tmp"; echo "refused: visudo rejected the line; nothing installed in sudoers" >&2; exit 1; fi
fi
echo "+ write $SUDOERS (440, checked with visudo)"
[ "$APPLY" = 1 ] || echo "Dry run: nothing was changed. Rerun with --apply."
