#!/usr/bin/env bash
# scripts/add-member.sh — a second (third, ...) member's brain on a box that already runs one.
# Created: 2026-10-19 (docs/MULTI_INSTANCE.md; design: hbar.world ops/2026-10-12_next-brains-design.md §1).
#
#   bash scripts/add-member.sh <handle> <n> --dry-run      # prints every action, touches nothing
#   bash scripts/add-member.sh <handle> <n> --apply [--update-tab] [--music[=<plugin checkout>]|--no-music]
#
# Run as the box's admin (hbar: sudo, docker), from any brain checkout on the box.
# Member <m> with port block n gets, walled from every other member:
#   /srv/brains/<m>          its own checkout (owner admin, group <m>-brain, no access for others)
#   <m>-cc, <m>-hands        Unix users: no sudo, not in docker, homes 700 (the hands' home opens
#                            750 to its own bridge only, by split-hands.sh, as on every CC box)
#   .env                     from .env.example, fresh secrets written into the file only (mode 600)
#   brain-<m>                compose project: own containers, own volumes (own Postgres), own network,
#                            host ports 8100+10n (api) +1 ui +2 nodeos +3 postgres +4 public chat
#   cc-bridge-<m>            the bridge on +8, claude-tab-<m> the terminal door on +7 (scripts/cc/install.sh,
#                            then scripts/cc/split-hands.sh, both with CC_MEMBER)
#   box packages           nodejs and npm (when node >= 16 with npm is not already there), cmake, python3-dev,
#                            build-essential, libcairo2: only the missing ones, apt, once per box (2026-11-09)
#   the Codex seat         the CLI for <m>-hands (scripts/cc/install-codex.sh <m>), CC_CODEX_WRITE=1 and
#                            CC_CODEX_WRITE_SANDBOX=off: Sign in with ChatGPT works on day one (2026-11-08)
# and the box's one Ollama (the first brain's, 127.0.0.1 only) joins the member's network as "ollama".
# It prints the Caddy site block for <m>.brainfoundry.ai and console.<m>.brainfoundry.ai; it never
# edits the Caddyfile, DNS or the cloud.
# The console's Update button works without the socket, through the member's bridge and a narrow root
# helper (scripts/member-update-door.sh, 2026-10-21).
# --update-tab: also mount the docker socket into the member's api (the single brain's way). That socket
# is root on the box: a member whose api is compromised then holds every member. Off by default.
# The music pack (scripts/member-music-kit.sh, the ableton.systems plugin for <m>-hands): --music installs it
# from MUSIC_PLUGIN (or --music=<checkout>); --no-music skips it; neither: asked on a terminal with --apply,
# else skipped with the one line to run later. One run, no pastes after it (SEAT-1 inventory #7 #10 #13).
# Limits (2026-11-06, docs/MEMBER_LIMITS.md): the override carries cpus, memory ceiling and reservation and
# a process limit per service; the member's bridge and terminal (so its reasoner and every cc-job) run in
# brain-<m>.slice (CPUQuota, MemoryHigh/Max/Low, TasksMax); root's /etc/brainfoundry/limits-<m>.env caps
# running jobs (CC_MAX_JOBS) and, if set, the spend ledger (CC_SPEND_CAP_EUR); <m>-cc and <m>-hands get no
# cron or at (a crontab would run outside the slice). Numbers: scripts/member_limits.py, overridable by
# BRAIN_LIMIT_* in this shell; `python3 scripts/member_limits.py check --plan --add 1` first says if they fit.
#
# Refuses: a bad or reserved handle, a block outside 1..99, a handle or block already in
# /srv/brains/members.tsv, an existing checkout, user, unit or compose project, a port of the block in use.
set -euo pipefail

usage() { echo "usage: $0 <handle> <n> --dry-run|--apply [--update-tab] [--music[=<plugin checkout>]|--no-music]" >&2; exit 2; }
[ $# -ge 3 ] || usage
HANDLE=$1; N=$2; MODE=$3; UPDATE_TAB=0; MUSIC=ask; MUSIC_PLUGIN=${MUSIC_PLUGIN:-}
case "$MODE" in --dry-run) APPLY=0 ;; --apply) APPLY=1 ;; *) usage ;; esac
shift 3
for a in "$@"; do
    case "$a" in
        --update-tab) UPDATE_TAB=1 ;;
        --music) MUSIC=yes ;;
        --music=*) MUSIC=yes; MUSIC_PLUGIN=${a#--music=} ;;
        --no-music) MUSIC=no ;;
        *) usage ;;
    esac
done

REPO=$(cd "$(dirname "$0")/.." && pwd)
BRAINS_ROOT=${BRAINS_ROOT:-/srv/brains}
SYSTEMD_DIR=${SYSTEMD_DIR:-/etc/systemd/system}
ADMIN_USER=${ADMIN_USER:-$(id -un)}
ORIGIN=${BRAIN_REPO_URL:-$(git -C "$REPO" remote get-url origin 2>/dev/null || echo https://github.com/hbar-systems/brainfoundry-nous.git)}
SHARED_OLLAMA=${SHARED_OLLAMA:-brain-ollama-1}
REGISTRY="$BRAINS_ROOT/members.tsv"

. "$REPO/scripts/cc/member.sh"
CC_MEMBER=$HANDLE CC_MEMBER_N=$N member_load || exit 2
DIR="$BRAINS_ROOT/$HANDLE"; GROUP="$HANDLE-brain"
BRIDGE_USER=$M_BRIDGE_USER; HANDS_USER=$M_HANDS_USER; PROJECT=$M_PROJECT

say()  { echo "$*"; }
# One action: printed always, run only with --apply. Never given a secret: the .env is written by
# scripts/member_env.py into the file, and the bridge copies its key from that file.
# Returns the action's own status, so `run X || say ...` notes a failure (before 2026-11-09 it always said 0).
run()  { echo "+ $*"; [ "$APPLY" = 1 ] || return 0; "$@"; }
fail() { echo "refused: $*" >&2; exit 1; }

say "== member $HANDLE, port block $N ($([ "$APPLY" = 1 ] && echo apply || echo 'dry run: nothing is changed'))"
say "   api $M_API_PORT  ui $M_UI_PORT  nodeos $M_NODEOS_PORT  postgres $M_PG_PORT  public chat $M_PUBLIC_CHAT_PORT  terminal $M_TERM_PORT  bridge $M_CC_PORT"

say "== 0 checks"
[ "$ADMIN_USER" != root ] || fail "run as the box's admin user (or set ADMIN_USER), not root"
if [ -f "$REGISTRY" ]; then
    awk -v h="$HANDLE" '$1==h {f=1} END {exit !f}' "$REGISTRY" && fail "handle $HANDLE is already in $REGISTRY"
    awk -v n="$N" '$2==n {f=1} END {exit !f}' "$REGISTRY" && fail "port block $N is already taken in $REGISTRY ($(awk -v n="$N" '$2==n {print $1}' "$REGISTRY"))"
fi
[ -e "$DIR" ] && fail "$DIR exists"
for u in "$BRIDGE_USER" "$HANDS_USER"; do id "$u" >/dev/null 2>&1 && fail "user $u exists"; done
getent group "$GROUP" >/dev/null 2>&1 && fail "group $GROUP exists"
for unit in "cc-bridge-$HANDLE" "claude-tab-$HANDLE"; do [ -e "$SYSTEMD_DIR/$unit.service" ] && fail "unit $unit exists"; done
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
    [ -n "$(docker ps -aq --filter "label=com.docker.compose.project=$PROJECT")" ] && fail "compose project $PROJECT has containers"
    [ -n "$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT")" ] && fail "compose project $PROJECT has volumes"
    docker inspect "$SHARED_OLLAMA" >/dev/null 2>&1 || say "   note: no container $SHARED_OLLAMA (the shared Ollama); set SHARED_OLLAMA or start the first brain"
else
    say "   note: docker not reachable from here; project and Ollama checks skipped"
fi
LISTEN=$(ss -Htln 2>/dev/null | awk '{print $4}' | sed 's/.*://' | sort -u)
for p in "$M_API_PORT" "$M_UI_PORT" "$M_NODEOS_PORT" "$M_PG_PORT" "$M_PUBLIC_CHAT_PORT" "$M_TERM_PORT" "$M_CC_PORT"; do
    grep -qx "$p" <<<"$LISTEN" && fail "port $p of block $N is in use"
done
say "   ok: handle, block, users, units, project and ports are free"

say "== 0b box packages: node for the Codex CLI, build tools and cairo for the music pack (only the missing ones)"
# As on friends-1 (2026-11-07): no node (Codex could not install), no cmake or python3-dev (tinysoundfont
# did not build), no libcairo2 (no PDF score). Box-wide plain packages; never reinstalled, never upgraded.
PKGS=()
NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || true)
[[ "$NODE_MAJOR" =~ ^[0-9]+$ ]] || NODE_MAJOR=0
# a node from elsewhere (nodesource) carries its own npm; apt's npm would fight it, so both or neither
if ! command -v npm >/dev/null 2>&1 || [ "$NODE_MAJOR" -lt 16 ]; then PKGS+=(nodejs npm); fi
for p in cmake python3-dev build-essential libcairo2; do
    dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q 'install ok installed' || PKGS+=("$p")
done
if [ ${#PKGS[@]} -eq 0 ]; then
    say "   ok: node $NODE_MAJOR with npm, cmake, python3-dev, build-essential, libcairo2 are all here"
else
    run sudo env DEBIAN_FRONTEND=noninteractive apt-get update -qq
    run sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${PKGS[@]}"
fi

say "== 1 users (no sudo, not in docker, homes 700)"
run sudo groupadd "$GROUP"
for u in "$BRIDGE_USER" "$HANDS_USER"; do
    run sudo useradd -m -s /bin/bash -U -G "$GROUP" "$u"
    run sudo chmod 700 "/home/$u"
done
run sudo usermod -aG "$GROUP" "$ADMIN_USER"
# ~/in exists before the stack starts: compose mounts it for laptop-import audio (docs/IMPORT.md),
# and a folder docker made would belong to root.
run sudo install -d -o "$HANDS_USER" -g "$HANDS_USER" -m 755 "/home/$HANDS_USER/in"

say "== 2 checkout $DIR (owner $ADMIN_USER, group $GROUP, nothing for anyone else)"
run sudo install -d -o root -g root -m 711 "$BRAINS_ROOT"
run sudo install -d -o "$ADMIN_USER" -g "$GROUP" -m 2750 "$DIR"
run git clone -q "$ORIGIN" "$DIR"   # g-w below; scripts/update_brain.sh keeps it so (umask 027)
run sudo chgrp -R "$GROUP" "$DIR"
run sudo chmod -R g+rX,g-w,o-rwx "$DIR"
run sudo find "$DIR" -type d -exec chmod g+s {} +
# the postgres container runs as its own uid (other here): it must read its init dir
# (schema only, no secrets), or it restart-loops on "initdb.d: Permission denied" (2026-10-21)
run sudo chmod -R o+rX "$DIR/vector-db"

say "== 3 .env (fresh secrets, into the file only)"
run python3 "$REPO/scripts/member_env.py" "$HANDLE" "$N" "$REPO/.env.example" "$DIR/.env"

LIMITS="$REPO/scripts/member_limits.py"
say "== 4 compose override: the shared Ollama, the limits$([ "$UPDATE_TAB" = 1 ] && echo ', the Update tab')"
OVERRIDE=$(python3 "$LIMITS" override $([ "$UPDATE_TAB" = 1 ] && echo --update-tab "$DIR")) || fail "limits: $LIMITS refused the profile"
say "$OVERRIDE" | sed 's/^/    | /'
# 644, never the admin's umask: brain-member-update refuses a group-writable override, so a 664 one
# broke every member's first Update (Alexander, 2026-11-07: "is group- or world-writable (664)")
if [ "$APPLY" = 1 ]; then (umask 022; printf '%s\n' "$OVERRIDE" > "$DIR/docker-compose.override.yml"); chmod 644 "$DIR/docker-compose.override.yml"; fi
echo "+ write $DIR/docker-compose.override.yml (644)"

say "== 4b host limits: brain-$HANDLE.slice for the bridge, terminal, reasoner and jobs; the job cap; no cron"
LIMITS_DIR=${LIMITS_DIR:-/etc/brainfoundry}
SLICE_FILE="$SYSTEMD_DIR/brain-$HANDLE.slice"
BRIDGE_DROPIN="$SYSTEMD_DIR/cc-bridge-$HANDLE.service.d/limits.conf"
TERM_DROPIN="$SYSTEMD_DIR/claude-tab-$HANDLE.service.d/limits.conf"
LIMITS_ENV="$LIMITS_DIR/limits-$HANDLE.env"
for kind_path in "slice:$SLICE_FILE" "bridge:$BRIDGE_DROPIN" "term:$TERM_DROPIN" "env:$LIMITS_ENV"; do
    kind=${kind_path%%:*}; path=${kind_path#*:}
    BODY=$(LIMITS_DIR="$LIMITS_DIR" python3 "$LIMITS" unit "$HANDLE" "$kind") || fail "limits: no $kind file"
    say "$BODY" | sed 's/^/    | /'
    if [ "$APPLY" = 1 ]; then
        sudo install -d -o root -g root -m 755 "$(dirname "$path")"
        printf '%s\n' "$BODY" | sudo tee "$path" >/dev/null
        sudo chmod 644 "$path"
    fi
    echo "+ write $path (root, 644)"
done
# cgroup v2 honours a reservation only up to what the parent carries: brain.slice and system.slice hold the
# sum for every member so far plus this one plus the admin brain (scripts/member_limits.py parent).
for kind_path in "brain:$SYSTEMD_DIR/brain.slice" "system:$SYSTEMD_DIR/system.slice.d/50-brain-limits.conf"; do
    kind=${kind_path%%:*}; path=${kind_path#*:}
    BODY=$(python3 "$LIMITS" parent "$kind" "$REGISTRY" --add 1) || fail "limits: no $kind parent"
    say "$BODY" | sed 's/^/    | /'
    if [ "$APPLY" = 1 ]; then
        sudo install -d -o root -g root -m 755 "$(dirname "$path")"
        printf '%s\n' "$BODY" | sudo tee "$path" >/dev/null
        sudo chmod 644 "$path"
    fi
    echo "+ write $path (root, 644)"
done
if [ "$APPLY" = 1 ]; then printf '%s\n' "$BRIDGE_USER" "$HANDS_USER" | sudo tee -a /etc/cron.deny /etc/at.deny >/dev/null; fi
echo "+ append $BRIDGE_USER and $HANDS_USER to /etc/cron.deny and /etc/at.deny"

say "== 5 the stack: compose project $PROJECT"
run docker compose --project-directory "$DIR" up -d --build

say "== 6 the shared Ollama joins every member's network (a timer, so a recreated container rejoins)"
LINK=/usr/local/sbin/brains-ollama-link
LINK_BODY="#!/usr/bin/env bash
# Written by scripts/add-member.sh: connect the box's one Ollama to each member network as \"ollama\".
for net in \$(docker network ls --format '{{.Name}}' | grep -E '^brain-[a-z0-9]+_llm-network\$'); do
    docker network connect --alias ollama \"\$net\" $SHARED_OLLAMA 2>/dev/null || true
done"
if [ "$APPLY" = 1 ]; then
    printf '%s\n' "$LINK_BODY" | sudo tee "$LINK" >/dev/null
    printf '[Unit]\nDescription=Connect the shared Ollama to every member network\n\n[Service]\nType=oneshot\nExecStart=%s\n' "$LINK" | sudo tee "$SYSTEMD_DIR/brains-ollama-link.service" >/dev/null
    printf '[Unit]\nDescription=Every minute: the shared Ollama on every member network\n\n[Timer]\nOnBootSec=1min\nOnUnitActiveSec=1min\n\n[Install]\nWantedBy=timers.target\n' | sudo tee "$SYSTEMD_DIR/brains-ollama-link.timer" >/dev/null
fi
echo "+ write $LINK, $SYSTEMD_DIR/brains-ollama-link.service and .timer"
run sudo chmod 755 "$LINK"
run sudo systemctl daemon-reload
run sudo systemctl enable --now brains-ollama-link.timer
run sudo systemctl start brains-ollama-link.service

say "== 7 the member's bridge and terminal units (install.sh, then split-hands.sh)"
CC_ENV=(env CC_MEMBER="$HANDLE" CC_MEMBER_N="$N" BRAIN_DIR="$DIR" BRAIN_USER="$ADMIN_USER" ADMIN_USER="$ADMIN_USER"
        BRIDGE_USER="$BRIDGE_USER" HANDS_USER="$HANDS_USER" TERM_PORT="$M_TERM_PORT" CC_PORT="$M_CC_PORT"
        UI_PORT="$M_UI_PORT" API_PORT="$M_API_PORT" CADDY_ROUTES=0)
run "${CC_ENV[@]}" bash "$DIR/scripts/cc/install.sh"
run "${CC_ENV[@]}" bash "$DIR/scripts/cc/split-hands.sh"
# the console's Update button: through the bridge and a narrow root helper, no docker socket (2026-10-21)
run bash "$DIR/scripts/member-update-door.sh" "$HANDLE" --apply

say "== 7b the Codex seat for $HANDS_USER, gated write mode, so Sign in with ChatGPT works on day one (2026-11-08)"
# As on Alexander's brain (2026-11-07): edits and commands through the same cards as Claude, Codex's own
# sandbox off (it cannot start on Ubuntu 24.04; the cards are the gate). Without npm or node the brain is
# still made; the sign-in panel then names the owner's one command (bash scripts/cc/install-codex.sh <m>).
run bash "$DIR/scripts/cc/install-codex.sh" "$HANDLE" \
    || say "   note: the Codex CLI did not install; later, from any checkout: bash scripts/cc/install-codex.sh $HANDLE"

say "== 7c the music pack for $HANDS_USER (scripts/member-music-kit.sh)"
# Before the two set-env lines below: each restarts cc-bridge-$HANDLE, so the bridge reads the new MCP entry.
MUSIC_LATER="bash $DIR/scripts/member-music-kit.sh $HANDLE <ableton-systems plugin checkout>"
if [ "$MUSIC" = ask ]; then
    if [ "$APPLY" = 1 ] && [ -t 0 ] && [ -t 1 ]; then
        read -rp "   install the music pack for $HANDLE now? [y/N] " ans || ans=""
        case "$ans" in y|Y|yes) MUSIC=yes ;; *) MUSIC=no ;; esac
        if [ "$MUSIC" = yes ] && [ -z "$MUSIC_PLUGIN" ]; then
            read -rp "   ableton-systems plugin checkout: " MUSIC_PLUGIN || MUSIC_PLUGIN=""
        fi
    else
        MUSIC=no
    fi
fi
if [ "$MUSIC" = yes ] && [ -n "$MUSIC_PLUGIN" ] && [ -d "$MUSIC_PLUGIN" ]; then
    run bash "$DIR/scripts/member-music-kit.sh" "$HANDLE" "$MUSIC_PLUGIN" \
        || say "   note: the music pack did not install; later: bash $DIR/scripts/member-music-kit.sh $HANDLE $MUSIC_PLUGIN"
elif [ "$MUSIC" = yes ]; then
    say "   note: no plugin checkout (set MUSIC_PLUGIN or --music=<checkout>; got '${MUSIC_PLUGIN}'); later: $MUSIC_LATER"
else
    say "   skipped; later: $MUSIC_LATER"
fi

for kv in CC_CODEX_WRITE=1 CC_CODEX_WRITE_SANDBOX=off; do
    echo "+ printf '${kv#*=}' | BRIDGE_USER=$BRIDGE_USER bash $DIR/scripts/cc/set-env.sh ${kv%%=*}"
    if [ "$APPLY" = 1 ]; then
        printf '%s' "${kv#*=}" | BRIDGE_USER="$BRIDGE_USER" bash "$DIR/scripts/cc/set-env.sh" "${kv%%=*}" \
            || say "   note: ${kv%%=*} was not set; set it with scripts/cc/set-env.sh"
    fi
done

say "== 8 registry"
LINE=$(printf '%s\t%s\t%s\t%s' "$HANDLE" "$N" "$M_API_PORT" "$(date -u +%Y-%m-%d)")
if [ "$APPLY" = 1 ]; then printf '%s\n' "$LINE" | sudo tee -a "$REGISTRY" >/dev/null; fi
echo "+ append to $REGISTRY: $LINE"
# The registry names every member: the admin's group only. Every brain's bridge reads the count of
# members beside it (a number, no names) for its System page (2026-10-19).
ADMIN_GROUP=$(id -gn "$ADMIN_USER" 2>/dev/null || echo "$ADMIN_USER")
run sudo chown "root:$ADMIN_GROUP" "$REGISTRY"
run sudo chmod 640 "$REGISTRY"
if [ "$APPLY" = 1 ]; then awk 'NF && $1 !~ /^#/' "$REGISTRY" | wc -l | tr -d ' ' | sudo tee "$BRAINS_ROOT/count" >/dev/null; sudo chmod 644 "$BRAINS_ROOT/count"; fi
echo "+ write $BRAINS_ROOT/count (the number of members, no names; mode 644)"

TOKEN_VAR=$M_TOKEN_VAR
say "== 9 Caddy: paste into /etc/caddy/Caddyfile, then sudo systemctl restart caddy (restart, not reload: the token env is new)"
cat <<CADDY
$HANDLE.brainfoundry.ai {
    reverse_proxy localhost:$M_API_PORT
}

console.$HANDLE.brainfoundry.ai {
    # Laptop import (docs/IMPORT.md): the helper on the person's computer carries a one-time
    # token, never this password. Only the four token-gated paths, straight to the api (the
    # console's own proxy would add the owner key); minting a token stays behind the login.
    @import path /api/bf/documents/import-laptop/helper.py /api/bf/documents/import-laptop/check /api/bf/documents/import-laptop/file /api/bf/documents/import-laptop/finish
    handle @import {
        uri strip_prefix /api/bf
        reverse_proxy localhost:$M_API_PORT
    }
    @login not path /api/bf/documents/import-laptop/helper.py /api/bf/documents/import-laptop/check /api/bf/documents/import-laptop/file /api/bf/documents/import-laptop/finish
    basicauth @login {
        $HANDLE <hash of the member's console password: caddy hash-password>
    }
    @claude path /claude /claude/*
    handle @claude {
        reverse_proxy localhost:$M_TERM_PORT {
            header_up X-CC-Operator {\$$TOKEN_VAR}
        }
    }
    @cc path /cc /cc/*
    handle @cc {
        reverse_proxy localhost:$M_CC_PORT {
            header_up X-CC-Operator {\$$TOKEN_VAR}
        }
    }
    reverse_proxy localhost:$M_UI_PORT
}
CADDY
say ""
say "DNS (by hand, not here): $HANDLE.brainfoundry.ai and console.$HANDLE.brainfoundry.ai to this box."
[ "$APPLY" = 1 ] || say "Dry run: nothing was changed. Rerun with --apply."
