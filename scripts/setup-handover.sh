#!/usr/bin/env bash
# setup-handover.sh: end a member's setup period and hand the brain over (STEWARD-1, 2026-11-27, docs/STEWARD.md).
# The operator's press on the member's box, after the member chose their new console password on their own
# Setup screen (/setup, "Choose your password"; the api kept a bcrypt hash only, never the password).
#
#   sudo bash scripts/setup-handover.sh <handle>                  # dry run: what would change, nothing written
#   sudo bash scripts/setup-handover.sh <handle> --apply          # swap the hash, restart caddy, end the setup key
#   sudo bash scripts/setup-handover.sh --single <user> [--apply] # a brain on its own box (console.<name>)
#
# What --apply does, in order, and stops at the first failure with nothing half done:
#   1. reads the member's chosen hash from the api runtime (setup/console-hash); none: stops, tells why;
#   2. backs up /etc/caddy/Caddyfile beside itself (.bak-handover-<handle>-<UTC time>);
#   3. swaps exactly one line: the member's user in their console block gets the new hash
#      (api/setup_steward.py swap_console_hash; zero or two matches: stops, Caddyfile untouched);
#   4. caddy validate, then systemctl restart caddy (restart, as docs/MULTI_INSTANCE.md says);
#   5. ends the setup key through the api (POST /setup/revoke, by the operator) and removes the kept hash;
#   6. prints the steward's last action from the brain's own log.
# Undo: copy the backup back over /etc/caddy/Caddyfile and restart caddy; the old password works again.
# Prints no password, no hash, no key.
set -euo pipefail
APPLY=0; SINGLE=0
[ "${1:-}" = --single ] && { SINGLE=1; shift; }
H=${1:?usage: setup-handover.sh <handle> [--apply] | --single <user> [--apply]}; shift
[ "${1:-}" = --apply ] && APPLY=1
if [ "$SINGLE" = 1 ]; then D=/home/hbar/brain; PREFIX="console."; else D=/srv/brains/$H; PREFIX="console.$H."; fi
CF=/etc/caddy/Caddyfile
[ -d "$D" ] || { echo "no brain at $D"; exit 1; }
cd "$D"
api() { docker compose exec -T api "$@" </dev/null; }

HASH=$(api sh -c 'cat /app/runtime/setup/console-hash 2>/dev/null' | tr -d '\r\n' || true)
if [ -z "$HASH" ]; then
  echo "STOP: $H has not chosen a new password yet (their console: /setup, Choose your password)."
  exit 2
fi
NEW=$(mktemp); trap 'rm -f "$NEW"' EXIT
HASH="$HASH" python3 -I - "$D/api/setup_steward.py" "$CF" "$PREFIX" "$H" "$NEW" <<'PY'
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("setup_steward", sys.argv[1])
ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
old = open(sys.argv[2], encoding="utf-8").read()
new = ss.swap_console_hash(old, sys.argv[3], sys.argv[4], os.environ["HASH"])
open(sys.argv[5], "w", encoding="utf-8").write(new)
changed = sum(1 for a, b in zip(old.split("\n"), new.split("\n")) if a != b)
print(f"one password line found for {sys.argv[4]} under {sys.argv[3]}: {changed} line would change")
PY
if [ "$APPLY" = 0 ]; then
  echo "dry run: nothing written. Run again with --apply to hand over."
  exit 0
fi
BAK="$CF.bak-handover-$H-$(date -u +%FT%H%MZ)"
cp -p "$CF" "$BAK"
caddy validate --config "$NEW" --adapter caddyfile >/dev/null 2>&1 || { echo "STOP: caddy validate failed; $CF untouched"; exit 3; }
cat "$NEW" > "$CF"
systemctl restart caddy
echo "+ new console password in place (backup $BAK)"
api python - <<'PY'
import json, os, urllib.request
h = {"Content-Type": "application/json", "X-API-Key": os.environ.get("BRAIN_API_KEY", "")}
r = urllib.request.urlopen(urllib.request.Request("http://localhost:8000/setup/revoke", method="POST", headers=h,
    data=json.dumps({"by": "operator", "why": "handover"}).encode()), timeout=20)
out = json.loads(r.read())
last = out.get("last_steward_action") or {}
print("+ setup period ended; the steward's last action:", last.get("action", "none"), last.get("at", ""))
PY
api sh -c 'rm -f /app/runtime/setup/console-hash'
echo "+ done: $H's brain is theirs (old password no longer opens the console)"
