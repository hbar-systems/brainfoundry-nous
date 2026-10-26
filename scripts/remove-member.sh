#!/usr/bin/env bash
# scripts/remove-member.sh — the inverse of add-member.sh: one member's brain off a shared box.
# Created: 2026-10-26 from docs/MULTI_INSTANCE.md "Removing a member (by hand, 2026-10-25)", the list
# run on friends-1 when two fresh members were renamed.
#
#   bash scripts/remove-member.sh <handle> --dry-run                 # prints every action, touches nothing
#   bash scripts/remove-member.sh <handle> --apply [--carry DIR]
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
# Refuses: root, a bad or reserved handle, a handle that is neither in /srv/brains/members.tsv nor a
# checkout under /srv/brains.
set -euo pipefail

usage() { echo "usage: $0 <handle> --dry-run|--apply [--carry DIR]" >&2; exit 2; }
[ $# -ge 2 ] || usage
HANDLE=$1; MODE=$2; shift 2
case "$MODE" in --dry-run) APPLY=0 ;; --apply) APPLY=1 ;; *) usage ;; esac
CARRY=""
if [ $# -gt 0 ]; then [ "$1" = --carry ] && [ $# -eq 2 ] || usage; CARRY=$2; fi

REPO=$(cd "$(dirname "$0")/.." && pwd)
BRAINS_ROOT=${BRAINS_ROOT:-/srv/brains}
SYSTEMD_DIR=${SYSTEMD_DIR:-/etc/systemd/system}
SUDOERS_DIR=${SUDOERS_DIR:-/etc/sudoers.d}
CADDY_DIR=${CADDY_DIR:-/etc/caddy}
CADDYFILE=${CADDYFILE:-$CADDY_DIR/Caddyfile}
UPDATE_STATE=${UPDATE_STATE:-/var/lib/brain-update}
ADMIN_USER=${ADMIN_USER:-$(id -un)}
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

say "== 1 carry into $CARRY (persona from the api_runtime volume, the console's hash line)"
run install -d -m 700 "$CARRY"
if [ "$DOCKER" = 0 ] || [ -n "$(docker ps -q --filter "label=com.docker.compose.project=$PROJECT" --filter "label=com.docker.compose.service=api")" ]; then
    into "$CARRY/persona-$HANDLE.md" docker compose --project-directory "$DIR" exec -T api cat /app/runtime/brain_persona.local.md
else
    say "   note: no running api in $PROJECT; the persona cannot be read (start it first if it matters)"
fi
into "$CARRY/hash-$HANDLE.txt" sudo grep -E "^[[:space:]]+$HANDLE [\$]2" "$CADDYFILE" || true   # none for a half-made member
run chmod -R go-rwx "$CARRY"
say "   memory is not carried: bash $DIR/scripts/backup_brain.sh first if anyone may want it"

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

say "== 9 Caddyfile: drop $HANDLE.brainfoundry.ai and console.$HANDLE.brainfoundry.ai (braces matched), validate, restart"
SITES=("$HANDLE.brainfoundry.ai" "console.$HANDLE.brainfoundry.ai")
TMP=$(mktemp); trap 'rm -f "$TMP" "$TMP.new"' EXIT
if readf "$CADDYFILE" > "$TMP"; then
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
say ""
say "DNS (by hand, not here): delete $HANDLE.brainfoundry.ai and console.$HANDLE.brainfoundry.ai."
[ "$APPLY" = 1 ] || say "Dry run: nothing was changed. Rerun with --apply."
