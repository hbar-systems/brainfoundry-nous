#!/usr/bin/env bash
# gpu-run.sh: rent one GPU for one job, then give it back (2026-10-12).
#
# Starts a RunPod pod, copies inputs in, runs one command, copies outputs back,
# and terminates the pod even when the command fails. Nothing stays on the pod.
# The person whose job it is pays for its minutes; storage stays with that person.
#
#   gpu-run.sh --in <file-or-dir> [--in ...] --out <local-dir> [--setup '<cmd>'] -- '<command>'
#
# On the pod, inputs land in /w/in/ and the command runs in /w; whatever it writes
# to /w/out/ is copied back to --out.
#
# The API key is never printed or passed on the command line. Either:
#   RUNPOD_API_KEY in the environment, or
#   RUNPOD_API_RELAY=user@host: a machine holding the key that runs
#   ~/bin/runpod-rest.sh METHOD PATH [BODYFILE] for us (same API, key stays there).
# The pod is reached with the local SSH key (GPU_SSH_KEY, default ~/.ssh/id_ed25519).
#
# Options via env: GPU_TYPES (comma list, cheapest suitable first), GPU_IMAGE,
# GPU_DISK_GB (default 40), GPU_MAX_MIN (hard stop, default 60).
set -euo pipefail

INS=(); OUT=""; SETUP=""
while [ $# -gt 0 ]; do
  case "$1" in
    --in) INS+=("$2"); shift 2;;
    --out) OUT="$2"; shift 2;;
    --setup) SETUP="$2"; shift 2;;
    --) shift; break;;
    *) echo "unknown option $1" >&2; exit 2;;
  esac
done
CMD="${1:?usage: gpu-run.sh --in X --out DIR -- 'command'}"
[ -n "$OUT" ] || { echo "--out is required" >&2; exit 2; }
KEY="${GPU_SSH_KEY:-$HOME/.ssh/id_ed25519}"
TYPES="${GPU_TYPES:-NVIDIA L4,NVIDIA RTX A4000,NVIDIA RTX A5000,NVIDIA RTX 4000 Ada Generation,NVIDIA GeForce RTX 4090}"
IMAGE="${GPU_IMAGE:-runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04}"
MAXMIN="${GPU_MAX_MIN:-60}"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

api() {  # api METHOD PATH [BODYFILE]
  if [ -n "${RUNPOD_API_KEY:-}" ]; then
    if [ -n "${3:-}" ]; then
      printf 'header = "Authorization: Bearer %s"\n' "$RUNPOD_API_KEY" | curl -s -K - -H 'Content-Type: application/json' -X "$1" --data-binary @"$3" "https://rest.runpod.io/v1$2"
    else
      printf 'header = "Authorization: Bearer %s"\n' "$RUNPOD_API_KEY" | curl -s -K - -X "$1" "https://rest.runpod.io/v1$2"
    fi
  elif [ -n "${RUNPOD_API_RELAY:-}" ]; then
    if [ -n "${3:-}" ]; then
      scp -q -o BatchMode=yes "$3" "$RUNPOD_API_RELAY:/tmp/gpu-run-body.json"
      ssh -o BatchMode=yes "$RUNPOD_API_RELAY" "~/bin/runpod-rest.sh $1 $2 /tmp/gpu-run-body.json; rm -f /tmp/gpu-run-body.json"
    else
      ssh -o BatchMode=yes "$RUNPOD_API_RELAY" "~/bin/runpod-rest.sh $1 $2"
    fi
  else
    echo "set RUNPOD_API_KEY or RUNPOD_API_RELAY" >&2; return 2
  fi
}

python3 - "$KEY.pub" "$TYPES" "$IMAGE" "${GPU_DISK_GB:-40}" > "$TMP/body.json" <<'PY'
import json, sys
pub, types, image, disk = sys.argv[1:5]
print(json.dumps({"name": "gpu-run", "imageName": image, "gpuTypeIds": [t.strip() for t in types.split(",")],
  "gpuCount": 1, "cloudType": "SECURE", "containerDiskInGb": int(disk), "ports": ["22/tcp"],
  "supportPublicIp": True, "env": {"PUBLIC_KEY": open(pub).read().strip()}}))
PY

POD=$(api POST /pods "$TMP/body.json" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("id",""))')
[ -n "$POD" ] || { echo "pod not created" >&2; exit 1; }
START=$(date +%s)
cleanup() {
  api DELETE "/pods/$POD" >/dev/null 2>&1 || true
  echo "gpu-run: pod $POD terminated after $(( ($(date +%s) - START) / 60 )) min" >&2
}
trap 'cleanup; rm -rf "$TMP"' EXIT
echo "gpu-run: pod $POD created" >&2

HOST=""; PORT=""
for _ in $(seq 1 60); do
  read -r HOST PORT < <(api GET "/pods/$POD" | python3 -c 'import sys,json; d=json.load(sys.stdin); m=d.get("portMappings") or {}; print(d.get("publicIp") or "-", m.get("22","-"))')
  [ "$HOST" != "-" ] && [ "$PORT" != "-" ] && break
  sleep 5
done
[ "$HOST" != "-" ] || { echo "pod never got an address" >&2; exit 1; }
SSH=(ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$TMP/known" -p "$PORT" "root@$HOST")
SCP=(scp -q -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$TMP/known" -P "$PORT")
for _ in $(seq 1 30); do "${SSH[@]}" true 2>/dev/null && break; sleep 5; done
echo "gpu-run: $("${SSH[@]}" 'nvidia-smi --query-gpu=name --format=csv,noheader') at $HOST" >&2

"${SSH[@]}" 'mkdir -p /w/in /w/out'
for i in "${INS[@]}"; do "${SCP[@]}" -r "$i" "root@$HOST:/w/in/"; done
[ -z "$SETUP" ] || "${SSH[@]}" "cd /w && $SETUP"
timeout "$((MAXMIN * 60))" "${SSH[@]}" "cd /w && $CMD"
mkdir -p "$OUT"
"${SCP[@]}" -r "root@$HOST:/w/out/." "$OUT/"
echo "gpu-run: outputs in $OUT" >&2
