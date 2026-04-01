#!/usr/bin/env bash
set -euo pipefail

export HBAR_IDENTITY_SECRET="${HBAR_IDENTITY_SECRET:-dev-secret-please-change}"
BASE="${BASE:-http://127.0.0.1:8010}"
CLIENT_ID="${CLIENT_ID:-golden-tests}"

ASSERTION="$(python3 - <<'PY'
import os, time, json, hmac, hashlib, base64
def b64url(x): return base64.urlsafe_b64encode(x).decode().rstrip("=")
secret=os.environ["HBAR_IDENTITY_SECRET"].encode()
now=int(time.time())
header=b64url(json.dumps({"alg":"HS256","typ":"HBAR_ASSERTION","v":1}).encode())
claims=b64url(json.dumps({
  "iss":"hbar-brain","sub":"root","aud":os.environ.get("CLIENT_ID","golden-tests"),
  "strain_id":"test","trust_tier":"root",
  "iat":now,"exp":now+900,"v":1
}).encode())
msg=f"{header}.{claims}".encode()
sig=b64url(hmac.new(secret,msg,hashlib.sha256).digest())
print(f"{header}.{claims}.{sig}")
PY
)"

PTOKEN="$(curl -sS "$BASE/v1/brain/command" \
  -H "Content-Type: application/json" \
  -d "{\"command\":\"permit issue MEMORY_WRITE 900 golden\",\"client_id\":\"$CLIENT_ID\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["token"])')"

PERMIT="$(curl -sS "$BASE/v1/brain/command" \
  -H "Content-Type: application/json" \
  -H "X-HBAR-Assertion: $ASSERTION" \
  -d "{\"command\":\"permit issue MEMORY_WRITE 900 golden\",\"client_id\":\"$CLIENT_ID\",\"confirm_token\":\"$PTOKEN\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["result"]["permit"])' \
  | tr -d '\n')"

python3 - <<PY
p="$PERMIT"
dots=p.count(".")
print(f"PERMIT_DOTS={dots}")
if dots != 2:
    raise SystemExit("FAIL: permit not 3-part token")
PY

MTOKEN="$(curl -sS "$BASE/v1/brain/command" \
  -H "Content-Type: application/json" \
  -d "{\"command\":\"memory append\",\"client_id\":\"$CLIENT_ID\",\"payload\":{\"text\":\"permit-backed append\"}}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["token"])')"

curl -sS "$BASE/v1/brain/command" \
  -H "Content-Type: application/json" \
  -H "X-HBAR-Assertion: $ASSERTION" \
  -H "X-HBAR-Permit: $PERMIT" \
  -d "{\"command\":\"memory append\",\"client_id\":\"$CLIENT_ID\",\"payload\":{\"text\":\"permit-backed append\"},\"confirm_token\":\"$MTOKEN\"}"
echo
