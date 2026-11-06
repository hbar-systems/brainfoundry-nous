#!/usr/bin/env bash
# scripts/remove-member.sh — the inverse of add-member.sh: one member's brain off a shared box.
# Created: 2026-10-26 from docs/MULTI_INSTANCE.md "Removing a member (by hand, 2026-10-25)", the list
# run on friends-1 when two fresh members were renamed.
#
#   bash scripts/remove-member.sh <handle> --dry-run [--export] [--site NAME]...   # prints every action, touches nothing
#   bash scripts/remove-member.sh <handle> --apply --export|--no-export [--carry DIR] [--site NAME]...
#
# Run as the box's admin (hbar: sudo, docker), from any brain checkout on the box. Never reads .env.
# Carries first (into DIR, default ~/member-carry/<m>-<UTC stamp>, mode 700): the persona from the
# api_runtime volume (it dies with down -v) and the console's bcrypt line from the Caddy site block
# (a hash, kept so the same password can open another block). Backs up the Caddyfile and members.tsv.
# Then takes away what add-member.sh made: the compose project brain-<m> with its volumes and built
# images, its network (the shared Ollama is disconnected first), the units, the sudoers files, the
# Caddy token env and drop-in, the users <m>-cc and <m>-hands and the group <m>-brain, the checkout,
# the members.tsv line, and the two site blocks (brace-matched by scripts/caddy_sites.py, validated
# before Caddy restarts). It does not take the memory: back it up first (backup_brain.sh or export.sh)
# if anyone may want it. DNS is by hand, as for add-member.
#
# 2026-11-06 (SEC-1 Wardens, docs/MEMBER_LIFECYCLE.md):
#   --export     carry the memory too, before anything is taken: scripts/export.sh of this checkout
#                (INCLUDE_VAULT=1: the vault is theirs) and the hands' ~/in uploads, into DIR.
#   --no-export  say out loud that the memory dies with down -v. --apply refuses without one of the two.
#   --site NAME  one more site block to drop (repeatable). Besides <m>.brainfoundry.ai and
#                console.<m>.brainfoundry.ai, every block whose local upstreams are all in the member's
#                port block is found and dropped (showcase-1 names them brain.hbar.university and so
#                on); a block that mixes the member's ports with others is refused at step 0, because a
#                stale block would route the old name, and the old password, to the next member of the block.
#   Step 11 prints what this script cannot take: backups and snapshots, peers that pin the member's
#   key, the tripwire baseline, the registry in hbar.world, DNS, Telegram bots, provider keys.
#
# Refuses: root, a bad or reserved handle, a handle that is neither in /srv/brains/members.tsv nor a
# checkout under /srv/brains.
set -euo pipefail

usage() { echo "usage: $0 <handle> --dry-run|--apply [--export|--no-export] [--carry DIR] [--site NAME]..." >&2; exit 2; }
[ $# -ge 2 ] || usage
HANDLE=$1; MODE=$2; shift 2
case "$MODE" in --dry-run) APPLY=0 ;; --apply) APPLY=1 ;; *) usage ;; esac
CARRY=""; EXPORT=""; EXTRA_SITES=()
while [ $# -gt 0 ]; do
    case "$1" in
        --carry) [ $# -ge 2 ] || usage; CARRY=$2; shift 2 ;;
        --site) [ $# -ge 2 ] || usage; EXTRA_SITES+=("$2"); shift 2 ;;
        --export) [ -z "$EXPORT" ] || usage; EXPORT=1; shift ;;
        --no-export) [ -z "$EXPORT" ] || usage; EXPORT=0; shift ;;
        *) usage ;;
    esac
done
if [ "$APPLY" = 1 ] && [ -z "$EXPORT" ]; then
    echo "usage: --apply needs --export (carry the memory first) or --no-export (it dies with down -v); docs/MEMBER_LIFECYCLE.md" >&2
    exit 2
fi
for s in ${EXTRA_SITES[@]+"${EXTRA_SITES[@]}"}; do
    [[ "$s" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] || { echo "usage: --site takes a host name, got '$s'" >&2; exit 2; }
done

REPO=$(cd "$(dirname "$0")/.." && pwd)
BRAINS_ROOT=${BRAINS_ROOT:-/srv/brains}
SYSTEMD_DIR=${SYSTEMD_DIR:-/etc/systemd/system}
SUDOERS_DIR=${SUDOERS_DIR:-/etc/sudoers.d}
CADDY_DIR=${CADDY_DIR:-/etc/caddy}
CADDYFILE=${CADDYFILE:-$CADDY_DIR/Caddyfile}
UPDATE_STATE=${UPDATE_STATE:-/var/lib/brain-update}
ADMIN_USER=${ADMIN_USER:-$(id -un)}
BACKUP_DIR=${BACKUP_DIR:-/home/$ADMIN_USER/brain-backups}   # backup_brain.sh's default, listed at step 11
SHARED_OLLAMA=${SHARED_OLLAMA:-brain-ollama-1}
REGISTRY="$BRAINS_ROOT/members.tsv"
STAMP=$(date -u +%Y-%m-%dT%H%MZ)

say()  { echo "$*"; }
run()  { echo "+ $*"; [ "$APPLY" = 1 ] && "$@"; return 0; }
# A command whose output goes to a file: printed always, run only with --apply.
into() { local out=$1; shift; echo "+ $* > $out"; [ "$APPLY" = 1 ] && "$@" > "$out" </dev/null; return 0; }
fail() { echo "refused: $*" >&2; exit 1; }
# Root-owned files: look with sudo -n only, so a dry run never prompts.
exists() { [ -e "$1" ] || sudo -n test -e "$1" 2>/dev/null; }
readf()  { cat "$1" 2>/dev/null || sudo -n cat "$1" 2>/dev/null; }

say "== member $HANDLE: remove ($([ "$APPLY" = 1 ] && echo apply || echo 'dry run: nothing is changed'))"

say "== 0 checks"
[ "$ADMIN_USER" != root ] || fail "run as the box's admin user (or set ADMIN_USER), not root"
# shellcheck source=cc/member.sh
. "$REPO/scripts/cc/member.sh"
member_handle_ok "$HANDLE" || fail "bad member handle: $HANDLE (a-z0-9, 2-16, starts with a letter, not reserved)"
DIR="$BRAINS_ROOT/$HANDLE"; GROUP="$HANDLE-brain"
N=$(readf "$REGISTRY" | awk -v h="$HANDLE" '$1==h {print $2; exit}' || true)
[ -n "$N" ] || [ -e "$DIR" ] || fail "$HANDLE is neither in $REGISTRY nor a checkout at $DIR: nothing to remove"
if [ -n "$N" ]; then
    CC_MEMBER=$HANDLE CC_MEMBER_N=$N member_load || exit 2
    say "   port block $N: api $M_API_PORT  ui $M_UI_PORT  nodeos $M_NODEOS_PORT  postgres $M_PG_PORT  public chat $M_PUBLIC_CHAT_PORT  terminal $M_TERM_PORT  bridge $M_CC_PORT"
else
    say "   note: $HANDLE is not in $REGISTRY (a half-made member); ports are not checked afterwards"
fi
PROJECT="brain-$HANDLE"; BRIDGE_USER="$HANDLE-cc"; HANDS_USER="$HANDLE-hands"; NET="${PROJECT}_llm-network"
DOCKER=0
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then DOCKER=1; else say "   note: docker not reachable from here; the stack steps are printed, not inspected"; fi
CARRY=${CARRY:-/home/$ADMIN_USER/member-carry/$HANDLE-$STAMP}
case "$CARRY" in /*) ;; *) CARRY="$PWD/$CARRY" ;; esac   # export.sh cds into the checkout
if [ "${EXPORT:-}" = 1 ] && [ "$DOCKER" = 1 ] && [ -z "$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" --filter "label=com.docker.compose.service=api")" ]; then
    fail "--export needs $PROJECT's api running (start it, or choose --no-export)"
fi

# The member's site blocks: the two default names, --site, and every block that proxies only to the
# member's port block. A mixed block is refused here, before anything is taken.
SITES=("$HANDLE.brainfoundry.ai" "console.$HANDLE.brainfoundry.ai" ${EXTRA_SITES[@]+"${EXTRA_SITES[@]}"})
TMP=$(mktemp); trap 'rm -f "$TMP" "$TMP.new"' EXIT
CADDY_READ=0
if readf "$CADDYFILE" > "$TMP"; then CADDY_READ=1
elif [ "$APPLY" = 1 ]; then fail "$CADDYFILE not readable: the site blocks could not be dropped; nothing is taken"; fi
if [ "$CADDY_READ" = 1 ] && [ -n "$N" ]; then
    BY_PORT=$(python3 "$REPO/scripts/caddy_sites.py" ports "$TMP" "$M_API_PORT" "$M_UI_PORT" "$M_NODEOS_PORT" "$M_PG_PORT" "$M_PUBLIC_CHAT_PORT" "$M_TERM_PORT" "$M_CC_PORT") \
        || fail "$CADDYFILE does not parse (caddy_sites.py ports); nothing is taken"
    MIXED=$(awk -F'\t' '$1=="mixed" {print "   " $3 " (" $4 ")"}' <<<"$BY_PORT")
    [ -z "$MIXED" ] || fail "a site block mixes $HANDLE's ports with other upstreams; split it by hand first:
$MIXED"
    while IFS=$'\t' read -r kind first _ _; do
        [ "$kind" = pure ] || continue
        case " ${SITES[*]} " in *" $first "*) ;; *) SITES+=("$first") ;; esac
    done <<<"$BY_PORT"
fi
say "   site blocks to drop: ${SITES[*]}"

say "== 1 carry into $CARRY (persona from the api_runtime volume, the console's hash line$([ "$EXPORT" = 1 ] && echo ', the memory'))"
run install -d -m 700 "$CARRY"
if [ "$EXPORT" = 1 ]; then
    # the admin's checkout runs the export (the member's own copy is theirs to change); vault included
    echo "+ BRAIN_DIR=$DIR INCLUDE_VAULT=1 bash $REPO/scripts/export.sh $CARRY"
    [ "$APPLY" = 1 ] && BRAIN_DIR="$DIR" INCLUDE_VAULT=1 bash "$REPO/scripts/export.sh" "$CARRY" </dev/null
    if exists "/home/$HANDS_USER/in"; then
        run sudo tar -C "/home/$HANDS_USER" -czf "$CARRY/in-$HANDLE.tar.gz" in
        run sudo chown "$ADMIN_USER" "$CARRY/in-$HANDLE.tar.gz"
    fi
fi
if [ "$DOCKER" = 0 ] || [ -n "$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" --filter "label=com.docker.compose.service=api")" ]; then
    into "$CARRY/persona-$HANDLE.md" docker compose --project-directory "$DIR" exec -T api cat /app/runtime/brain_persona.local.md
else
    say "   note: no running api in $PROJECT; the persona cannot be read (start it first if it matters)"
fi
into "$CARRY/hash-$HANDLE.txt" sudo grep -E "^[[:space:]]+$HANDLE [\$]2" "$CADDYFILE" || true   # none for a half-made member
run chmod -R go-rwx "$CARRY"
if [ "$EXPORT" = 1 ]; then
    say "   not in the export: NodeOS memory_proposals (scripts/export_brain.py over ssh has them), the bridge's threads and tokens"
else
    say "   memory is not carried: rerun with --export, or bash $DIR/scripts/backup_brain.sh first, if anyone may want it"
fi

say "== 2 backups"
run sudo cp -p "$CADDYFILE" "$CADDYFILE.bak-remove-$HANDLE-$STAMP"
[ -f "$REGISTRY" ] && run sudo cp -p "$REGISTRY" "$REGISTRY.bak-remove-$HANDLE-$STAMP"

say "== 3 the stack: compose project $PROJECT (containers, volumes, built images), then its network"
[ -e "$DIR/docker-compose.yml" ] && run docker compose --project-directory "$DIR" down -v --rmi local --remove-orphans
if [ "$DOCKER" = 0 ] || docker network inspect "$NET" >/dev/null 2>&1; then
    # the shared Ollama sits on the member's network and keeps it "in use" (brains-ollama-link timer)
    run docker network disconnect "$NET" "$SHARED_OLLAMA" || true
    run docker network rm "$NET"
fi

say "== 4 units"
FOUND_UNITS=()
for u in cc-bridge claude-tab cc-bridge-watch cc-install-watch cc-work-pull; do
    for ext in service path timer; do
        [ -e "$SYSTEMD_DIR/$u-$HANDLE.$ext" ] && FOUND_UNITS+=("$u-$HANDLE.$ext")
    done
done
[ ${#FOUND_UNITS[@]} -eq 0 ] && say "   none in $SYSTEMD_DIR"
for f in "${FOUND_UNITS[@]}"; do
    run sudo systemctl disable --now "$f"
    run sudo rm -f "$SYSTEMD_DIR/$f"
done
run sudo systemctl daemon-reload
run sudo systemctl reset-failed

say "== 5 sudoers and the Update door's state"
SUDOERS=()
for f in "cc-bridge-$HANDLE" "cc-hands-$HANDLE" "brain-update-$HANDLE"; do
    exists "$SUDOERS_DIR/$f" && SUDOERS+=("$SUDOERS_DIR/$f")
done
if [ ${#SUDOERS[@]} -gt 0 ]; then run sudo rm -f "${SUDOERS[@]}"; else say "   none in $SUDOERS_DIR"; fi
run sudo visudo -c
exists "$UPDATE_STATE/$HANDLE" && run sudo rm -rf "$UPDATE_STATE/$HANDLE"

say "== 6 Caddy token env and its drop-in (daemon-reload before any caddy restart)"
for f in "$CADDY_DIR/cc-$HANDLE.env" "$SYSTEMD_DIR/caddy.service.d/cc-$HANDLE.conf"; do
    exists "$f" && run sudo rm -f "$f"
done
run sudo systemctl daemon-reload

say "== 7 users and group"
for u in "$BRIDGE_USER" "$HANDS_USER"; do
    if id "$u" >/dev/null 2>&1; then
        run sudo pkill -u "$u" || true
        run sudo userdel -r "$u"
    else
        say "   no user $u"
    fi
done
if getent group "$GROUP" >/dev/null 2>&1; then run sudo groupdel "$GROUP"; else say "   no group $GROUP"; fi

say "== 8 checkout and registry"
[ -e "$DIR" ] && run sudo rm -rf "$DIR"
if [ -f "$REGISTRY" ]; then
    run sudo sed -i "/^$HANDLE\t/d" "$REGISTRY"
    if [ "$APPLY" = 1 ]; then sudo awk 'NF && $1 !~ /^#/' "$REGISTRY" | wc -l | tr -d ' ' | sudo tee "$BRAINS_ROOT/count" >/dev/null; sudo chmod 644 "$BRAINS_ROOT/count"; fi
    echo "+ write $BRAINS_ROOT/count (the number of members, no names; mode 644)"
fi

say "== 9 Caddyfile: drop ${SITES[*]} (braces matched), validate, restart"
if [ "$CADDY_READ" = 1 ]; then
    python3 "$REPO/scripts/caddy_sites.py" list "$TMP" "${SITES[@]}" | sed 's/^/   /' || true
else
    [ "$APPLY" = 1 ] && fail "$CADDYFILE not readable; the site blocks stay (everything above is done)"
    say "   note: $CADDYFILE not readable from here"
fi
NEW="$CADDYFILE.new-remove-$HANDLE"
if [ "$APPLY" = 1 ]; then
    python3 "$REPO/scripts/caddy_sites.py" drop "$TMP" "$TMP.new" "${SITES[@]}" >/dev/null || true
    sudo install -m 644 "$TMP.new" "$NEW"
fi
echo "+ python3 scripts/caddy_sites.py drop $CADDYFILE -> $NEW"
if [ "$APPLY" = 1 ]; then
    if sudo caddy validate --config "$NEW" --adapter caddyfile >/dev/null 2>&1; then
        sudo cp "$NEW" "$CADDYFILE" && sudo rm -f "$NEW"
        sudo systemctl restart caddy
        echo "+ caddy validate: Valid; $CADDYFILE replaced; caddy restarted"
    else
        echo "caddy validate failed on $NEW; $CADDYFILE untouched, caddy not restarted. Fix by hand." >&2
        exit 1
    fi
else
    echo "+ sudo caddy validate --config $NEW --adapter caddyfile; only on Valid: cp over $CADDYFILE, sudo systemctl restart caddy"
fi

say "== 10 leftovers"
if [ "$APPLY" = 1 ]; then
    LEFT=$( { getent passwd; getent group; ls "$SYSTEMD_DIR" "$SYSTEMD_DIR/caddy.service.d" "$CADDY_DIR" "$BRAINS_ROOT" /home 2>/dev/null; sudo ls "$SUDOERS_DIR" 2>/dev/null
              docker ps -a --format '{{.Names}}'; docker volume ls -q; docker network ls --format '{{.Name}}'; docker images --format '{{.Repository}}'; } \
            | grep -E "(^|[^a-z0-9])$HANDLE([^a-z0-9]|$)" | grep -v -e "\.bak-remove-$HANDLE-" || true)
    if [ -n "$N" ]; then
        LISTEN=$(ss -Htln 2>/dev/null | awk '{print $4}' | sed 's/.*://' | sort -u)
        for p in "$M_API_PORT" "$M_UI_PORT" "$M_NODEOS_PORT" "$M_PG_PORT" "$M_PUBLIC_CHAT_PORT" "$M_TERM_PORT" "$M_CC_PORT"; do
            grep -qx "$p" <<<"$LISTEN" && LEFT="$LEFT
port $p still listening"
        done
    fi
    if [ -n "$LEFT" ]; then echo "leftovers:"; echo "$LEFT" | sed 's/^/   /'; else echo "   none"; fi
else
    say "   after --apply: users, groups, units, caddy, sudoers, /srv/brains, /home, containers, volumes, networks, images grepped for $HANDLE; the block's ports"
fi
say "== 11 what this script cannot take (docs/MEMBER_LIFECYCLE.md, procedures a and b)"
BK=$( { ls -d "$BACKUP_DIR"/*/ 2>/dev/null || sudo -n ls -d "$BACKUP_DIR"/*/ 2>/dev/null; } \
      | sed 's:/$::; s:.*/::' | grep -E "(^|[^a-z0-9])$HANDLE([^a-z0-9]|$)" | sed "s:^:$BACKUP_DIR/:" || true)
# and every artifact whose manifest names this checkout (backup_brain.sh writes "brain_dir: <dir>")
BK_M=$( { grep -lsx "brain_dir: *$DIR" "$BACKUP_DIR"/*/*/manifest.txt "$BACKUP_DIR"/*/*/*/manifest.txt 2>/dev/null \
          || sudo -n sh -c 'grep -lsx "brain_dir: *$1" "$2"/*/*/manifest.txt "$2"/*/*/*/manifest.txt' _ "$DIR" "$BACKUP_DIR" 2>/dev/null; } \
        | sed 's:/manifest.txt$::' || true)
BK=$(printf '%s\n%s\n' "$BK" "$BK_M" | sed '/^$/d' | sort -u)
if [ -n "$BK" ]; then say "   backups under $BACKUP_DIR that name $HANDLE (delete them if the member asked to be forgotten):"; echo "$BK" | sed 's/^/     /'
else say "   no backup under $BACKUP_DIR names $HANDLE or $DIR (backup_brain.sh names artifacts by category and time; make a member's with BACKUP_DIR=$BACKUP_DIR/$HANDLE)"; fi
say "   the carry dir $CARRY: hand it over, then delete it"
say "   Hetzner box backups (7 days) and snapshots still hold the checkout, .env included; the Storage Box may hold brain backups"
say "   peers: every known_peers.toml and data/peers.json that pins this brain's key, on this box and the other"
say "   hbar.world: ops/security/brain-identity-baseline.tsv, registry/nodes.json, ops/security/incidents.tsv (kind removal)"
say "   Telegram: the member's bots stay valid at Telegram until revoked with @BotFather; provider API keys until revoked at the provider"
say ""
say "DNS (by hand, not here): delete ${SITES[*]}."
[ "$APPLY" = 1 ] || say "Dry run: nothing was changed. Rerun with --apply."
