#!/bin/bash
# spoke-door: the brain's one way to its member's laptop, run as the door user <m>-spoke (SPOKE-2A, 2026-11-14).
# Installed root 755 as /usr/local/sbin/spoke-door by spoke-install.sh; the bridge user calls it through one
# sudoers line (sudo -n -u <m>-spoke spoke-door <m> <verb>), the push-helper pattern: the reasoner asks, the
# bridge raises the card, the door user (who alone holds the keys) runs one narrow verb. Design: docs/spoke.md.
#
#   spoke-door <m> status              the brain's node, the laptop (online or asleep since), its mode
#   spoke-door <m> inventory           counts and sizes from the laptop (no names); kept as inventory/latest.tsv
#   spoke-door <m> plan    < plan.tsv  check a plan here, print it and its counts; the laptop is not touched
#   spoke-door <m> apply   < plan.tsv  the same check, then the laptop's door.sh apply (the card came first)
#   spoke-door <m> undo <id>           the laptop's door.sh undo <id>
#   spoke-door <m> organise on|off     the laptop's mode (on only after the card)
#   spoke-door <m> leave               the laptop's key line goes, the laptop's node leaves the network
#   spoke-door <m> fingerprint         the signing key's fingerprint (the console shows it by Download)
#   spoke-door <m> bundle              a one-device, one-hour network key and the signed "Join my brain" zip
#
# No shell, no delete verb on the laptop, no path the laptop's door.sh would refuse. Every call is one line
# in /var/lib/spoke/<m>/door.log (readable by the member's group) before it runs, refused ones too.
set -u
umask 027
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# the tests put fake tailscale, headscale and ssh first; sudo resets the environment, so a real call never can
[ "${SPOKE_DOOR_TEST:-}" = 1 ] && [ -n "${SPOKE_TEST_BIN:-}" ] && PATH="$SPOKE_TEST_BIN:$PATH"
export LC_ALL=C

M=${1:-}; VERB=${2:-}
[ $# -ge 2 ] && shift 2 || set --
ETC=${SPOKE_ETC:-/etc/spoke}
VAR=${SPOKE_VAR:-/var/lib/spoke/$M}
SHARE=${SPOKE_SHARE:-/usr/local/share/spoke}
MAX_PLAN=5000

die() { printf 'refused: %s\n' "$*" >&2; exit 3; }
[[ "$M" =~ ^[a-z][a-z0-9]{1,15}$ ]] || die "bad handle"
# sudo resets the environment, so SPOKE_DOOR_TEST only ever reaches a door run by hand (the tests)
if [ "${SPOKE_DOOR_TEST:-}" != 1 ] && [ "$(id -un)" != "$M-spoke" ]; then die "spoke-door $M runs as $M-spoke"; fi
[ -d "$VAR" ] || die "no spoke for $M on this box (spoke-install.sh $M --apply)"
LOG="$VAR/door.log"
log() { printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; }
refuse() { log "REFUSED	$VERB	$*"; die "$*"; }
log "call	$VERB	$*"

# the member's settings: KEY=value lines, read, never sourced
conf() { awk -F= -v k="$1" '$1 == k { sub(/^[^=]*=/, ""); print; exit }' "$ETC/$M.env" 2>/dev/null; }
SOCKS_PORT=$(conf SOCKS_PORT); HS_CONFIG=$(conf HS_CONFIG); LOGIN_SERVER=$(conf LOGIN_SERVER); CONSOLE_URL=$(conf CONSOLE_URL)
[[ "${SOCKS_PORT:-}" =~ ^[0-9]{4,5}$ ]] || refuse "no SOCKS_PORT in $ETC/$M.env"
TS_SOCK=${SPOKE_TS_SOCK:-/run/spoke/$M/tailscaled.sock}
KEY="$VAR/key/door"; SIGN="$VAR/key/signing"

ts() { tailscale --socket="$TS_SOCK" "$@"; }
hs() { headscale -c "$HS_CONFIG" "$@"; }

# The laptop: the peer whose name is "<m>-laptop--<mac user>" (spoke.sh join sets it). Prints
# "<ip>\t<user>\t<online|asleep>\t<last seen>" for the first one, nothing when none joined.
laptop() {
    ts status --json 2>/dev/null | python3 -c '
import json, sys
m = sys.argv[1]
try:
    peers = (json.load(sys.stdin).get("Peer") or {}).values()
except Exception:
    peers = []
for p in peers:
    name = str(p.get("HostName") or "")
    if not name.startswith(m + "-laptop--") or not p.get("TailscaleIPs"):
        continue
    ip = next((a for a in p["TailscaleIPs"] if "." in a), p["TailscaleIPs"][0])
    print("\t".join([ip, name.split("--", 1)[1], "online" if p.get("Online") else "asleep", str(p.get("LastSeen") or "")]))
    break
' "$M"
}

on_laptop() {
    # one door.sh verb on the laptop; the forced command there turns these words into its verb
    local l ip user state
    l=$(laptop); [ -n "$l" ] || refuse "no laptop has joined yet"
    IFS=$'\t' read -r ip user state _ <<< "$l"
    [ "$state" = online ] || refuse "the laptop is asleep or away (last seen $(printf '%s' "$l" | cut -f4))"
    [[ "$user" =~ ^[a-z0-9-]{1,32}$ ]] || refuse "the laptop's user name looks wrong"
    ssh -i "$KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=15 -o ServerAliveInterval=15 \
        -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$VAR/known_hosts" \
        -o ProxyCommand="nc -X 5 -x 127.0.0.1:$SOCKS_PORT %h %p" "$user@$ip" "$*"
}

lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }
rel_ok() {
    # the laptop's door.sh fences paths again; this is the brain's side of the same fence, so a bad
    # plan never leaves the box: relative, no "..", no hidden part, nothing under Library, no control bytes
    local p=$1 lc
    case "$p" in ''|/*|*..*) return 1 ;; esac
    [[ "$p" == *[[:cntrl:]]* ]] && return 1
    lc=$(lower "/$p/")
    case "$lc" in */.*|/library/*) return 1 ;; esac
    return 0
}

# a plan on stdin into $1, checked line by line; prints "<mkdirs>\t<moves>"
read_plan() {
    local out=$1 op a b extra n=0 dirs=0 moves=0
    : > "$out"
    while IFS=$'\t' read -r op a b extra || [ -n "${op:-}" ]; do
        n=$((n+1)); [ "$n" -le "$MAX_PLAN" ] || refuse "plan longer than $MAX_PLAN lines"
        [ -z "${extra:-}" ] || refuse "plan line $n has too many fields"
        case "$op" in
            mkdir) [ -z "${b:-}" ] || refuse "plan line $n: mkdir takes one folder"
                   rel_ok "$a" || refuse "plan line $n: path $a"
                   printf 'mkdir\t%s\n' "$a" >> "$out"; dirs=$((dirs+1)) ;;
            mv) rel_ok "$a" || refuse "plan line $n: path $a"; rel_ok "${b:-}" || refuse "plan line $n: path ${b:-}"
                printf 'mv\t%s\t%s\n' "$a" "$b" >> "$out"; moves=$((moves+1)) ;;
            '') ;;
            *) refuse "plan line $n: $op (only mkdir and mv; there is no delete)" ;;
        esac
    done
    [ $((dirs+moves)) -gt 0 ] || refuse "empty plan"
    printf '%s\t%s\n' "$dirs" "$moves"
}

case "$VERB" in
    status)
        [ $# -eq 0 ] || refuse "status takes no words"
        printf 'handle\t%s\n' "$M"
        printf 'brain\t%s\n' "$(ts ip -4 2>/dev/null | head -1)"
        l=$(laptop)
        if [ -z "$l" ]; then printf 'laptop\tnone\n'
        else
            IFS=$'\t' read -r ip user state seen <<< "$l"
            printf 'laptop\t%s\t%s\t%s\t%s\n' "$M-laptop--$user" "$ip" "$state" "$seen"
            [ "$state" = online ] && printf 'mode\t%s\n' "$(on_laptop mode 2>/dev/null | head -1)"
        fi
        [ -f "$VAR/inventory/latest.tsv" ] && printf 'inventory\t%s\n' "$(date -u -r "$VAR/inventory/latest.tsv" +%Y-%m-%dT%H:%M:%SZ)"
        exit 0 ;;
    inventory)
        [ $# -eq 0 ] || refuse "inventory takes no words"
        mkdir -p "$VAR/inventory"; t=$(date -u +%Y%m%dT%H%M%SZ); f="$VAR/inventory/inv-$t.tsv"
        on_laptop inventory > "$f.part" || { rm -f "$f.part"; refuse "the laptop's inventory did not finish"; }
        grep -q '^meta	finished' "$f.part" || { rm -f "$f.part"; refuse "the inventory came back without its end line"; }
        mv "$f.part" "$f"; ln -sfn "inv-$t.tsv" "$VAR/inventory/latest.tsv"; chmod 640 "$f"
        log "inventory	$f	$(wc -l < "$f") lines"; cat "$f" ;;
    plan|apply)
        [ $# -eq 0 ] || refuse "$VERB reads the plan on stdin, no words"
        mkdir -p "$VAR/plans"; p="$VAR/plans/$(date -u +%Y%m%dT%H%M%SZ)-$$.tsv"
        counts=$(read_plan "$p") || exit 3
        IFS=$'\t' read -r dirs moves <<< "$counts"
        printf 'plan\t%s folders\t%s moves\n' "$dirs" "$moves"
        if [ "$VERB" = plan ]; then cat "$p"; log "plan	$dirs folders	$moves moves	checked"; exit 0; fi
        log "apply	$dirs folders	$moves moves	$p"
        on_laptop apply < "$p" ;;
    undo)
        [ $# -eq 1 ] || refuse "undo takes one id"
        [[ "$1" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || refuse "undo id $1"
        on_laptop undo "$1" ;;
    organise)
        [ $# -eq 1 ] && { [ "$1" = on ] || [ "$1" = off ]; } || refuse "organise on or off"
        on_laptop organise "$1" ;;
    leave)
        [ $# -eq 0 ] || refuse "leave takes no words"
        if on_laptop leave 2>/dev/null; then printf 'laptop\tkey line removed\n'
        else printf 'laptop\tnot reached (asleep or gone): its key line goes when the node goes; Leave my brain on its Desktop removes the rest\n'; fi
        # the laptop's node off the network: headscale's node ids for "<m>-laptop--*", then delete each
        ids=$(hs nodes list -o json 2>/dev/null | python3 -c '
import json, sys
try:
    nodes = json.load(sys.stdin) or []
except Exception:
    nodes = []
m = sys.argv[1]
for n in nodes:
    if str(n.get("given_name") or n.get("name") or "").startswith(m + "-laptop--"):
        print(n.get("id"))
' "$M")
        for id in $ids; do
            [[ "$id" =~ ^[0-9]+$ ]] || continue
            hs nodes delete --identifier "$id" --force >/dev/null && printf 'node\t%s\toff the network\n' "$id"
        done
        log "leave	nodes ${ids:-none}" ;;
    fingerprint)
        [ $# -eq 0 ] || refuse "fingerprint takes no words"
        ssh-keygen -lf "$SIGN.pub" | awk '{print "signing\t" $2}' ;;
    bundle)
        [ $# -eq 0 ] || refuse "bundle takes no words"
        mkdir -p "$VAR/tmp" "$VAR/out"; chmod 700 "$VAR/tmp"
        # Headscale 0.26 takes the user's id; older versions its name (unverified on friends-1 until the apply)
        uid=$(hs users list -o json 2>/dev/null | python3 -c '
import json, sys
m = sys.argv[1]
try:
    users = json.load(sys.stdin) or []
except Exception:
    users = []
print(next((str(u.get("id")) for u in users if u.get("name") == m), ""))
' "$M")
        ak="$VAR/tmp/authkey"; trap 'rm -f "$ak"' EXIT
        hs preauthkeys create --user "${uid:-$M}" --expiration 1h -o json 2>/dev/null \
            | python3 -c 'import json,sys; print(json.load(sys.stdin)["key"])' > "$ak" \
            || refuse "Headscale issued no key"
        [ -s "$ak" ] || refuse "Headscale issued an empty key"
        ip=$(ts ip -4 2>/dev/null | head -1); [ -n "$ip" ] || refuse "the brain's node has no address (spoke-node@$M down?)"
        zip=$(bash "$SHARE/make-bundle.sh" --handle "$M" --console "$CONSOLE_URL" --login-server "$LOGIN_SERVER" \
            --authkey-file "$ak" --brain-ip "$ip" --brain-pubkey "$KEY.pub" --signing-key "$SIGN" --out "$VAR/out" | head -1)
        [ -f "$zip" ] || refuse "make-bundle made no zip"
        chmod 640 "$zip"
        fp=$(ssh-keygen -lf "$SIGN.pub" | awk '{print $2}')
        exp=$(date -u -d '+1 hour' +%Y-%m-%dT%H:%M:%SZ)
        log "bundle	$zip	$fp	expires $exp"
        printf 'bundle\t%s\nsigning\t%s\nexpires\t%s\n' "$zip" "$fp" "$exp" ;;
    *) refuse "verb ${VERB:-none}" ;;
esac
