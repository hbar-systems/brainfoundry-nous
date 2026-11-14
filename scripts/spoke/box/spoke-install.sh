#!/usr/bin/env bash
# spoke-install.sh: give one member's brain its spoke network and door on a shared box (SPOKE-2A, 2026-11-14).
# Written on the brain box and run there only as --dry-run; the apply on friends-1 is the watched thread's.
#
#   bash scripts/spoke/box/spoke-install.sh <m> --block <n> [--bridge-user U] [--console URL] [--domain D] --dry-run
#   bash scripts/spoke/box/spoke-install.sh <m> --block <n> [...] --apply      on the box named by --host (default friends-1)
#   bash scripts/spoke/box/spoke-install.sh <m> --block <n> --undo [--dry-run] stop, disable, move aside; deletes nothing
#
# --dry-run is the default: it prints every step and every file it would write, measures the ports
# (ss -ltn, read-only) and the programs it needs, and changes nothing. --apply needs: this box's hostname
# equal to --host, sudo, headscale, tailscale(d), caddy, nc, python3, ssh-keygen and visudo present, all four
# ports free, the member's group <m>-brain present (or --group), and DNS for spoke.<m>.<domain> pointing here
# before the laptop joins (the brain's own node joins over the local port, without DNS).
#
# What --apply does, in order (each with its undo, written to /var/lib/spoke/<m>/INSTALLED as it goes):
#   1. user <m>-spoke (system, no shell, home /var/lib/spoke/<m>)        undo: user left, locked (nothing deleted)
#   2. /var/lib/spoke/<m> 750 <m>-spoke:<group>, key/ 700, node/ 700, out/ 2770, door.log 640
#                                                                          undo: moved to /var/backups/spoke-<m>-<date>/
#   3. two ed25519 keys made by the door user: key/door (the laptop's key line), key/signing (the bundle)
#                                                                          undo: moved with the folder
#   4. /etc/headscale/<m>/config.yaml + policy.json (root:<m>-spoke 640), /etc/spoke/<m>.env (644)
#                                                                          undo: moved to the backup folder
#   5. /etc/systemd/system/headscale@.service, spoke-node@.service (once per box); headscale@<m> enabled and started;
#      Headscale user <m>                                                  undo: headscale@<m> stopped, disabled
#   6. Caddy: /etc/caddy/Caddyfile backed up as Caddyfile.bak-spoke-<m>-<date>, the site appended, `caddy validate`,
#      reload; a failed validate restores the backup and stops       undo: the block dropped (caddy_sites.py), validate, reload
#   7. spoke-node@<m> enabled and started; it joins with a 10-minute tag:brain key over 127.0.0.1
#                                                                          undo: stopped, disabled
#   8. /usr/local/share/spoke/ (the laptop files, root 755) and /usr/local/sbin/spoke-door (root 755)
#                                                                          undo: left (shared by every member)
#   9. /etc/sudoers.d/spoke-<m> (440, visudo -cf first)                    undo: moved to the backup folder
# Never touched: the member's brain stack, its compose project, its .env, other members' files.
set -euo pipefail

usage() { sed -n '4,7p' "$0" >&2; exit 2; }
[ $# -ge 1 ] || usage
M=$1; shift
BLOCK=""; BRIDGE=""; CONSOLE=""; DOMAIN=brainfoundry.ai; MODE=dry; UNDO=0; HOST=friends-1; GROUP=""
while [ $# -gt 0 ]; do
    case "$1" in
        --block) BLOCK=${2:-}; shift ;;
        --bridge-user) BRIDGE=${2:-}; shift ;;
        --console) CONSOLE=${2:-}; shift ;;
        --domain) DOMAIN=${2:-}; shift ;;
        --host) HOST=${2:-}; shift ;;
        --group) GROUP=${2:-}; shift ;;
        --dry-run) MODE=dry ;;
        --apply) MODE=apply ;;
        --undo) UNDO=1 ;;
        *) usage ;;
    esac; shift
done
[[ "$M" =~ ^[a-z][a-z0-9]{1,15}$ ]] || { echo "refused: bad handle $M" >&2; exit 2; }
[[ "$BLOCK" =~ ^[1-9][0-9]?$ ]] || { echo "refused: --block 1..99 needed" >&2; exit 2; }
BRIDGE=${BRIDGE:-$M-cc}; GROUP=${GROUP:-$M-brain}
[[ "$BRIDGE" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || { echo "refused: bad bridge user" >&2; exit 2; }
[[ "$GROUP" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || { echo "refused: bad group" >&2; exit 2; }

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../.." && pwd)
CFG="python3 $HERE/spoke_config.py"
DOOR_USER=$M-spoke
VAR=/var/lib/spoke/$M
ETC_HS=/etc/headscale/$M
ENVF=/etc/spoke/$M.env
SUDOERS=/etc/sudoers.d/spoke-$M
SITE=spoke.$M.$DOMAIN
TODAY=$(date -u +%Y-%m-%d)
BACK=/var/backups/spoke-$M-$TODAY
CADDYFILE=${SPOKE_CADDYFILE:-/etc/caddy/Caddyfile}
EXTRA=(--domain "$DOMAIN"); [ -n "$CONSOLE" ] && EXTRA+=(--console "$CONSOLE")

say() { printf '%s\n' "$*"; }
run() { printf '+'; printf ' %q' "$@"; printf '\n'; [ "$MODE" = apply ] && "$@"; return 0; }
rec() { [ "$MODE" = apply ] && printf '%s\t%s\n' "$(date -u +%FT%TZ)" "$*" | sudo tee -a "$VAR/INSTALLED" >/dev/null; return 0; }
stop() { say "STOPPED: $*"; say "Nothing after this step was changed."; exit 1; }

STAGE=$(mktemp -d); trap 'rm -rf "$STAGE"' EXIT
$CFG write "$M" "$BLOCK" "$STAGE" --bridge-user "$BRIDGE" "${EXTRA[@]}" >/dev/null
read -r SOCKS HS_HTTP HS_METRICS HS_GRPC < <($CFG ports "$M" "$BLOCK" | cut -f2 | paste -sd' ')

say "== spoke for $M, block $BLOCK, on $(hostname) ($([ "$MODE" = apply ] && echo APPLY || echo 'dry run: nothing is changed'))$([ "$UNDO" = 1 ] && echo ', UNDO')"
say "   door user $DOOR_USER, bridge user $BRIDGE, group $GROUP, site https://$SITE"
say "   ports: headscale http $HS_HTTP, metrics $HS_METRICS, grpc $HS_GRPC, brain node SOCKS $SOCKS (127.0.0.1 only)"

if [ "$MODE" = apply ]; then
    [ "$(hostname)" = "$HOST" ] || stop "this is $(hostname), not $HOST (--host names the box this may change)"
    sudo -n true 2>/dev/null || stop "sudo is needed for --apply"
fi

if [ "$UNDO" = 1 ]; then
    say; say "-- undo: stop, disable, move aside (nothing is deleted)"
    run sudo mkdir -p "$BACK"
    run sudo systemctl disable --now "spoke-node@$M" "headscale@$M"
    if [ -f "$SUDOERS" ] || [ "$MODE" = dry ]; then run sudo mv -f "$SUDOERS" "$BACK/sudoers-spoke-$M"; fi
    say "+ Caddy: drop the $SITE block, validate, reload (a failed validate puts the file back)"
    if [ "$MODE" = apply ] && grep -q "^$SITE {" "$CADDYFILE"; then
        sudo cp -p "$CADDYFILE" "$BACK/Caddyfile.before-undo"
        python3 "$REPO/scripts/caddy_sites.py" drop "$CADDYFILE" "$STAGE/Caddyfile.new" "$SITE"
        sudo install -m 644 "$STAGE/Caddyfile.new" "$CADDYFILE"
        if sudo caddy validate --config "$CADDYFILE" --adapter caddyfile >/dev/null 2>&1; then sudo systemctl reload caddy
        else sudo install -m 644 "$BACK/Caddyfile.before-undo" "$CADDYFILE"; stop "caddy validate refused the file without $SITE; put back"; fi
    fi
    for p in "$ETC_HS" "$ENVF" "$VAR" "/var/lib/headscale/$M"; do
        if [ -e "$p" ] || [ "$MODE" = dry ]; then run sudo mv "$p" "$BACK/"; fi
    done
    run sudo usermod --lock --expiredate 1 "$DOOR_USER"
    say "   left in place: user $DOOR_USER (locked), /usr/local/sbin/spoke-door and /usr/local/share/spoke (shared),"
    say "   the two unit templates. Everything moved is in $BACK. DNS for $SITE is hbar's (scripts/dns.sh)."
    [ "$MODE" = apply ] || say "Dry run: nothing was changed. Rerun with --apply."
    exit 0
fi

say; say "-- 0. measure (read-only)"
missing=()
for c in headscale tailscale tailscaled caddy nc python3 ssh-keygen visudo ss; do
    command -v "$c" >/dev/null 2>&1 || missing+=("$c")
done
if [ ${#missing[@]} -gt 0 ]; then
    say "   missing programs: ${missing[*]}"
    say "   install first (by hand, read each line; versions are checked at apply time, not here):"
    case " ${missing[*]} " in *" headscale "*)
        say "     headscale: the arm64 .deb from https://github.com/juanfont/headscale/releases (0.26 or newer), sha256 checked against the release's checksums.txt, then sudo apt install ./headscale_<v>_linux_arm64.deb; keep the packaged headscale.service disabled (sudo systemctl disable --now headscale)" ;; esac
    case " ${missing[*]} " in *" tailscale "*|*" tailscaled "*)
        say "     tailscale: the apt repository at https://pkgs.tailscale.com/stable/ubuntu/noble (its signing key, then sudo apt install tailscale); keep the packaged tailscaled.service disabled: this box is not on any tailnet" ;; esac
    case " ${missing[*]} " in *" nc "*) say "     nc: sudo apt install netcat-openbsd (the door's SOCKS hop uses nc -X 5)" ;; esac
    [ "$MODE" = apply ] && stop "programs missing: ${missing[*]}"
fi
busy=()
if command -v ss >/dev/null 2>&1; then
    listening=$(ss -ltnH 2>/dev/null | awk '{print $4}' | sed 's/.*://' | sort -u)
    for p in "$SOCKS" "$HS_HTTP" "$HS_METRICS" "$HS_GRPC"; do
        grep -qx "$p" <<< "$listening" && busy+=("$p")
    done
    if [ ${#busy[@]} -gt 0 ]; then say "   ports in use here: ${busy[*]}"; else say "   ports free here: $SOCKS $HS_HTTP $HS_METRICS $HS_GRPC (measured with ss -ltn)"; fi
fi
[ "$MODE" = apply ] && [ ${#busy[@]} -gt 0 ] && stop "ports in use: ${busy[*]} (pick another --block and record it)"
if getent group "$GROUP" >/dev/null 2>&1; then say "   group $GROUP present"
else say "   group $GROUP not on this box"; [ "$MODE" = apply ] && stop "no group $GROUP (the member's; --group names another)"; fi
if getent passwd "$BRIDGE" >/dev/null 2>&1; then say "   bridge user $BRIDGE present"
else say "   bridge user $BRIDGE not on this box"; [ "$MODE" = apply ] && stop "no user $BRIDGE"; fi
[ -f "$CADDYFILE" ] && grep -q "^$SITE {" "$CADDYFILE" && { say "   $SITE is already in $CADDYFILE"; [ "$MODE" = apply ] && stop "site already present (undo first, or leave it)"; }

say; say "-- 1. door user"
if getent passwd "$DOOR_USER" >/dev/null 2>&1; then say "   $DOOR_USER exists"
else run sudo useradd --system --user-group --home-dir "$VAR" --no-create-home --shell /usr/sbin/nologin "$DOOR_USER"; rec "user $DOOR_USER"; fi

say; say "-- 2. folders"
run sudo install -d -o "$DOOR_USER" -g "$GROUP" -m 750 "$VAR"
run sudo install -d -o "$DOOR_USER" -g "$DOOR_USER" -m 700 "$VAR/key" "$VAR/node" "$VAR/tmp" "$VAR/plans"
run sudo install -d -o "$DOOR_USER" -g "$GROUP" -m 750 "$VAR/inventory"
run sudo install -d -o "$DOOR_USER" -g "$GROUP" -m 2770 "$VAR/out"
run sudo install -o "$DOOR_USER" -g "$GROUP" -m 640 /dev/null "$VAR/door.log"
rec "folders $VAR"

say; say "-- 3. keys (made by the door user, never read by anyone else)"
for k in door signing; do
    if [ "$MODE" = apply ] && sudo test -f "$VAR/key/$k"; then say "   key/$k exists, kept"; continue; fi
    run sudo -u "$DOOR_USER" ssh-keygen -q -t ed25519 -N '' -C "brain-spoke $k $M $TODAY" -f "$VAR/key/$k"
done
rec "keys $VAR/key/door $VAR/key/signing"

say; say "-- 4. Headscale config, policy, env"
say "   $ETC_HS/config.yaml:"; sed 's/^/     | /' "$STAGE/config.yaml" | head -8; say "     | ... ($(wc -l < "$STAGE/config.yaml") lines)"
say "   $ETC_HS/policy.json:"; sed 's/^/     | /' "$STAGE/policy.json"
say "   $ENVF:"; sed 's/^/     | /' "$STAGE/spoke.env"
run sudo install -d -o root -g "$DOOR_USER" -m 750 "$ETC_HS"
run sudo install -o root -g "$DOOR_USER" -m 640 "$STAGE/config.yaml" "$ETC_HS/config.yaml"
run sudo install -o root -g "$DOOR_USER" -m 640 "$STAGE/policy.json" "$ETC_HS/policy.json"
run sudo install -d -o root -g root -m 755 /etc/spoke
run sudo install -o root -g root -m 644 "$STAGE/spoke.env" "$ENVF"
rec "config $ETC_HS $ENVF"

say; say "-- 5. Headscale for $M"
run sudo install -o root -g root -m 644 "$HERE/headscale@.service" /etc/systemd/system/headscale@.service
run sudo install -o root -g root -m 644 "$HERE/spoke-node@.service" /etc/systemd/system/spoke-node@.service
run sudo systemctl daemon-reload
run sudo systemctl enable --now "headscale@$M"
[ "$MODE" = apply ] && sleep 3
run sudo -u "$DOOR_USER" headscale -c "$ETC_HS/config.yaml" users create "$M"
rec "headscale@$M enabled; headscale user $M"

say; say "-- 6. Caddy: https://$SITE -> 127.0.0.1:$HS_HTTP"
sed 's/^/     | /' "$STAGE/Caddyfile.spoke"
CBAK="$CADDYFILE.bak-spoke-$M-$TODAY"
run sudo cp -p "$CADDYFILE" "$CBAK"
say "+ append the block to $CADDYFILE, caddy validate, reload (a failed validate restores $CBAK and stops)"
if [ "$MODE" = apply ]; then
    sudo tee -a "$CADDYFILE" < "$STAGE/Caddyfile.spoke" >/dev/null
    if sudo caddy validate --config "$CADDYFILE" --adapter caddyfile >/dev/null 2>&1; then sudo systemctl reload caddy
    else sudo install -m 644 "$CBAK" "$CADDYFILE"; stop "caddy validate refused the new block; $CADDYFILE restored from $CBAK"; fi
    rec "caddy $SITE (backup $CBAK)"
fi

say; say "-- 7. the brain's node (userspace, as $DOOR_USER, SOCKS 127.0.0.1:$SOCKS)"
run sudo systemctl enable --now "spoke-node@$M"
say "+ a 10-minute tag:brain key from headscale, then: tailscale --socket=/run/spoke/$M/tailscaled.sock up --login-server=http://127.0.0.1:$HS_HTTP --authkey=<that key> --hostname=$M-brain --advertise-tags=tag:brain"
if [ "$MODE" = apply ]; then
    sleep 3
    sudo -u "$DOOR_USER" bash -c '
        set -euo pipefail
        hs() { headscale -c "$1" "${@:2}"; }
        uid=$(hs "$1" users list -o json | python3 -c "import json,sys; print(next((str(u[\"id\"]) for u in json.load(sys.stdin) if u.get(\"name\")==sys.argv[1]), sys.argv[1]))" "$2")
        key=$(hs "$1" preauthkeys create --user "$uid" --expiration 10m --tags tag:brain -o json | python3 -c "import json,sys; print(json.load(sys.stdin)[\"key\"])")
        tailscale --socket="/run/spoke/$2/tailscaled.sock" up --login-server="http://127.0.0.1:$3" --authkey="$key" \
            --hostname="$2-brain" --advertise-tags=tag:brain --accept-dns=false --accept-routes=false
        tailscale --socket="/run/spoke/$2/tailscaled.sock" ip -4' _ "$ETC_HS/config.yaml" "$M" "$HS_HTTP"
    rec "spoke-node@$M joined"
fi

say; say "-- 8. the door: /usr/local/sbin/spoke-door, the laptop files in /usr/local/share/spoke"
run sudo install -o root -g root -m 755 "$HERE/spoke-door.sh" /usr/local/sbin/spoke-door
run sudo install -d -o root -g root -m 755 /usr/local/share/spoke
for f in door.sh inventory.sh spoke.sh make-bundle.sh "Join my brain.command" WHAT-THIS-DOES.txt; do
    run sudo install -o root -g root -m 755 "$REPO/scripts/spoke/$f" "/usr/local/share/spoke/$f"
done
rec "door /usr/local/sbin/spoke-door"

say; say "-- 9. sudoers: $SUDOERS"
sed 's/^/     | /' "$STAGE/sudoers"
say "+ install $SUDOERS (440) only if visudo -cf accepts it"
if [ "$MODE" = apply ]; then
    sudo install -o root -g root -m 440 "$STAGE/sudoers" "$SUDOERS.tmp"
    if sudo visudo -cf "$SUDOERS.tmp" >/dev/null; then sudo mv -f "$SUDOERS.tmp" "$SUDOERS"
    else sudo rm -f "$SUDOERS.tmp"; stop "visudo refused the line; nothing installed in sudoers"; fi
    rec "sudoers $SUDOERS"
fi

say; say "-- check"
say "+ sudo -u $DOOR_USER headscale -c $ETC_HS/config.yaml nodes list        (the brain's node, tag:brain)"
say "+ sudo -u $BRIDGE sudo -n -u $DOOR_USER /usr/local/sbin/spoke-door $M status"
say "   the bridge env needs CC_SPOKE=1 (and CC_SPOKE_HANDLE=$M when the bridge is not member $M) to show /spoke"
[ "$MODE" = apply ] || say "Dry run: nothing was changed. Rerun with --apply on $HOST."
