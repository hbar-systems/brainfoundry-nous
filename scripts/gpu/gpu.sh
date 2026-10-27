#!/usr/bin/env bash
# gpu.sh: start an open-weight model on a rented GPU for one sitting, and give it back (2026-10-23).
#
#   gpu.sh up <profile> [--model TAG] [--minutes N] [--dry-run]
#   gpu.sh down [<profile>]          # all running profiles when none is named
#   gpu.sh status
#
# A profile (scripts/gpu/profiles/<name>.env) fixes the port, the model, the time cap and
# whether the brain may use it. `private` is the brain's spoke: set OLLAMA_SPOKE_URL to
# http://<GPU_BIND>:11500 once, and the brain uses the pod while it is up and falls back to
# its own Ollama when it is down, with no restart. `lab` is never the brain's spoke.
#
# Nothing listens on the pod's public address but SSH. Ollama binds to the pod's localhost and
# is reached through an SSH tunnel that listens on GPU_BIND on this box (a private address:
# the brain counts a model as local by its address). Nothing is stored on the pod: the
# weights are pulled at start, and the pod is terminated by `down`, by a failed `up`, or by a
# watchdog at the profile's time cap. No pod outlives a sitting unless GPU_ALLOW_LONG=1.
#
# Settings (optional) in ~/.config/gpu/config, sourced as shell:
#   GPU_BIND        address the tunnel listens on (default 127.0.0.1)
#   GPU_KEY_FILE    file holding the RunPod API key (default ~/.config/runpod/api-key)
#   GPU_SSH_KEY     SSH key the pod accepts (default ~/.ssh/id_ed25519)
#   GPU_TYPES       GPU types, preferred first (24 GB cards by default)
# The API key is read from its file, passed to curl on stdin, and never printed.
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF="${GPU_CONFIG:-$HOME/.config/gpu/config}"
[ -f "$CONF" ] && . "$CONF"
STATE="${GPU_STATE_DIR:-$HOME/.local/state/gpu}"
BIND="${GPU_BIND:-127.0.0.1}"
KEYFILE="${GPU_KEY_FILE:-$HOME/.config/runpod/api-key}"
SSHKEY="${GPU_SSH_KEY:-$HOME/.ssh/id_ed25519}"
TYPES="${GPU_TYPES:-NVIDIA L4,NVIDIA RTX A5000,NVIDIA GeForce RTX 4090,NVIDIA RTX 4000 Ada Generation}"
IMAGE="${GPU_IMAGE:-runpod/base:0.6.3-cuda12.4.1}"
LONGEST=240
DRY=0
mkdir -p "$STATE"; chmod 700 "$STATE"

say() { echo "gpu: $*" >&2; }
die() { say "$*"; exit 1; }

api() {  # api METHOD PATH [BODYFILE]
  if [ "$DRY" = 1 ]; then say "(dry run) $1 https://rest.runpod.io/v1$2"; [ "$1" = POST ] && echo '{"id":"DRYRUN"}'; return 0; fi
  [ -s "$KEYFILE" ] || die "no RunPod API key in $KEYFILE"
  local cfg; cfg=$(printf 'header = "Authorization: Bearer %s"\n' "$(head -1 "$KEYFILE" | tr -d '[:space:]')")
  if [ -n "${3:-}" ]; then
    printf '%s\n' "$cfg" | curl -s -K - -H 'Content-Type: application/json' -X "$1" --data-binary @"$3" "https://rest.runpod.io/v1$2"
  else
    printf '%s\n' "$cfg" | curl -s -K - -X "$1" "https://rest.runpod.io/v1$2"
  fi
}

field() { python3 -c 'import sys,json
try: d=json.load(sys.stdin)
except Exception: d={}
for k in sys.argv[1:]: d = d.get(k, {}) if isinstance(d, dict) else {}
print(d if d not in ({}, None, "") else "-")' "$@"; }

load_profile() {
  local f="$HERE/profiles/$1.env"
  [ -f "$f" ] || die "no profile $1 (have: $(ls "$HERE/profiles" | sed 's/\.env$//' | tr '\n' ' '))"
  PORT=; MODEL=; MAX_MIN=; SPOKE=; DISK_GB=
  . "$f"
}

st() { echo "$STATE/$1.env"; }

answers() {  # answers <port> <model>: the model is listed at the tunnel.
  # Host: localhost because the pod's Ollama listens on its loopback and refuses (403) a Host it
  # does not count as local, such as a tailnet address in GPU_BIND (2026-10-27).
  curl -s --max-time 3 -H 'Host: localhost' "http://$BIND:$1/api/tags" | grep -q "\"$2\""
}

ssh_to() {  # ssh_to <profile> <command...>, from the profile's state
  local s; s=$(st "$1"); shift
  # shellcheck disable=SC1090
  . "$s"
  ssh -i "$SSHKEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$STATE/$PROFILE.known" \
      -o ConnectTimeout=15 -p "$SSHPORT" "root@$HOST" "$@"
}

terminate() {  # terminate <profile>: tunnel, pod, watchdog, state. Safe to call twice.
  local p="$1" s; s=$(st "$p")
  [ -f "$s" ] || return 0
  # shellcheck disable=SC1090
  . "$s"
  [ -n "${TUNNEL:-}" ] && kill "$TUNNEL" 2>/dev/null || true
  if [ -n "${POD:-}" ]; then api DELETE "/pods/$POD" >/dev/null 2>&1 || true; fi
  local mins=$(( ($(date +%s) - STARTED) / 60 ))
  local usd; usd=$(python3 -c "print(f'{${COST:-0} * $mins / 60:.2f}')")
  say "$p: pod ${POD:-?} terminated after $mins min, about USD $usd"
  rm -f "$s" "$STATE/$p.known"
  if [ -n "${WATCH:-}" ] && [ "$WATCH" != "$$" ]; then kill "$WATCH" 2>/dev/null || true; fi
}

cmd_up() {
  local p="${1:?usage: gpu.sh up <profile>}"; shift
  load_profile "$p"
  while [ $# -gt 0 ]; do
    case "$1" in
      --model) MODEL="$2"; shift 2;;
      --minutes) MAX_MIN="$2"; shift 2;;
      --dry-run) DRY=1; shift;;
      *) die "unknown option $1";;
    esac
  done
  [ -f "$(st "$p")" ] && die "$p is already up (gpu.sh status, or gpu.sh down $p)"
  if [ "$MAX_MIN" -gt "$LONGEST" ] && [ "${GPU_ALLOW_LONG:-0}" != 1 ]; then
    die "$MAX_MIN min is longer than a sitting ($LONGEST); set GPU_ALLOW_LONG=1 to mean it"
  fi
  [ -f "$SSHKEY.pub" ] || die "no SSH public key at $SSHKEY.pub"
  local tmp; tmp=$(mktemp -d); trap 'rm -rf "$tmp"' RETURN
  python3 - "$SSHKEY.pub" "$TYPES" "$IMAGE" "$DISK_GB" "$p" > "$tmp/body.json" <<'PY'
import json, sys
pub, types, image, disk, prof = sys.argv[1:6]
print(json.dumps({"name": f"gpu-{prof}", "imageName": image, "gpuTypeIds": [t.strip() for t in types.split(",")],
  "gpuCount": 1, "cloudType": "SECURE", "containerDiskInGb": int(disk), "ports": ["22/tcp"],
  "supportPublicIp": True, "env": {"PUBLIC_KEY": open(pub).read().strip()}}))
PY
  say "$p: renting a GPU ($MODEL, cap $MAX_MIN min)"
  local pod; pod=$(api POST /pods "$tmp/body.json" | field id)
  [ "$pod" != "-" ] || die "pod not created (no GPU of $TYPES free, or the key was refused)"
  if [ "$DRY" = 1 ]; then say "(dry run) would wait for SSH, install Ollama, pull $MODEL, tunnel $BIND:$PORT, watch $MAX_MIN min"; return 0; fi
  local started; started=$(date +%s)
  cat > "$(st "$p")" <<EOF
PROFILE=$p
POD=$pod
STARTED=$started
DEADLINE=$(( started + MAX_MIN * 60 ))
MODEL=$MODEL
PORT=$PORT
SPOKE=$SPOKE
EOF
  chmod 600 "$(st "$p")"
  trap 'say "$p: start failed, giving the pod back"; terminate "$p"' ERR

  local host=- sshport=- cost=0 info
  for _ in $(seq 1 72); do
    info=$(api GET "/pods/$pod")
    host=$(printf '%s' "$info" | field publicIp); sshport=$(printf '%s' "$info" | field portMappings 22)
    cost=$(printf '%s' "$info" | field costPerHr)
    [ "$host" != "-" ] && [ "$sshport" != "-" ] && break
    sleep 5
  done
  [ "$host" != "-" ] || { say "$p: the pod never got an address"; false; }
  [ "$cost" = "-" ] && cost=0
  printf 'HOST=%s\nSSHPORT=%s\nCOST=%s\n' "$host" "$sshport" "$cost" >> "$(st "$p")"
  for _ in $(seq 1 36); do ssh_to "$p" true 2>/dev/null && break; sleep 5; done
  say "$p: $(ssh_to "$p" 'nvidia-smi --query-gpu=name,memory.total --format=csv,noheader') at USD $cost/h"

  say "$p: installing Ollama and pulling $MODEL (a few minutes)"
  ssh_to "$p" "command -v ollama >/dev/null || (curl -fsSL https://ollama.com/install.sh | sh) >/tmp/ollama-install.log 2>&1
    (OLLAMA_HOST=127.0.0.1:11434 nohup ollama serve >/tmp/ollama.log 2>&1 &)
    for i in \$(seq 1 30); do curl -s 127.0.0.1:11434/api/version >/dev/null && break; sleep 2; done
    OLLAMA_HOST=127.0.0.1:11434 ollama pull '$MODEL' >/tmp/ollama-pull.log 2>&1"

  setsid ssh -i "$SSHKEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$STATE/$p.known" \
      -o ServerAliveInterval=30 -o ServerAliveCountMax=4 -o ExitOnForwardFailure=yes -o GatewayPorts=yes \
      -N -L "$BIND:$PORT:127.0.0.1:11434" -p "$sshport" "root@$host" </dev/null >"$STATE/$p.tunnel.log" 2>&1 &
  echo "TUNNEL=$!" >> "$(st "$p")"
  setsid "$HERE/gpu.sh" _watch "$p" </dev/null >>"$STATE/$p.watch.log" 2>&1 &
  echo "WATCH=$!" >> "$(st "$p")"
  trap - ERR

  for _ in $(seq 1 15); do answers "$PORT" "$MODEL" && break; sleep 2; done
  if answers "$PORT" "$MODEL"; then
    say "$p: up. $MODEL answers at http://$BIND:$PORT until $(date -d @$(( started + MAX_MIN * 60 )) +%H:%M) (box time)"
  else
    say "$p: the pod runs but $MODEL does not answer through the tunnel yet; see $STATE/$p.tunnel.log, or gpu.sh down $p"
  fi
  [ "$SPOKE" = 1 ] && say "$p: the brain uses it if OLLAMA_SPOKE_URL=http://$BIND:$PORT (its health shows spoke_up)"
  return 0
}

cmd_watch() {  # internal: terminate at the deadline, or when the tunnel dies for good
  local p="$1" s; s=$(st "$p")
  while [ -f "$s" ]; do
    # shellcheck disable=SC1090
    . "$s"
    if [ "$(date +%s)" -ge "$DEADLINE" ]; then say "$p: time cap reached"; WATCH=$$ terminate "$p"; exit 0; fi
    sleep 60
  done
}

cmd_down() {
  local any=0 f
  if [ -n "${1:-}" ]; then terminate "$1"; return; fi
  for f in "$STATE"/*.env; do [ -e "$f" ] || continue; any=1; terminate "$(basename "$f" .env)"; done
  [ "$any" = 1 ] || say "nothing is up"
}

cmd_status() {
  local any=0 f now; now=$(date +%s)
  for f in "$STATE"/*.env; do
    [ -e "$f" ] || continue; any=1
    ( . "$f"
      tun=down; [ -n "${TUNNEL:-}" ] && kill -0 "$TUNNEL" 2>/dev/null && tun=up
      ans=no; answers "$PORT" "$MODEL" && ans=yes
      echo "$PROFILE  pod $POD  $MODEL  tunnel $tun  answers $ans  $(( (now - STARTED) / 60 )) min used, $(( (DEADLINE - now) / 60 )) min left  http://$BIND:$PORT" )
  done
  [ "$any" = 1 ] || echo "nothing is up"
}

case "${1:-}" in
  up) shift; cmd_up "$@";;
  down) shift; cmd_down "$@";;
  status) cmd_status;;
  _watch) shift; cmd_watch "$@";;
  *) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 2;;
esac
