#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8010}"

post_capture() {
  local data="$1"
  local hdr
  local body
  hdr="$(mktemp)"
  body="$(mktemp)"
  # Print status code to stdout; headers to $hdr; body to $body
  local status
  status="$(curl -sS --http1.1 --max-time 5 \
    -H "Content-Type: application/json" \
    -X POST "${BASE}/v1/brain/command" \
    -d "${data}" \
    -D "${hdr}" -o "${body}" -w "%{http_code}")"
  echo "${status}|${hdr}|${body}"
}

run_case() {
  local name="$1"
  local expected_status="$2"
  local expected_code="$3"
  local data="$4"

  echo "== ${name} =="

  IFS="|" read -r status hdr body < <(post_capture "${data}")

  if [[ "${status}" != "${expected_status}" ]]; then
    echo "FAIL: expected ${expected_status}, got ${status}"
    echo "--- headers ---"
    sed -n '1,30p' "${hdr}" || true
    echo "--- body ---"
    sed -n '1,120p' "${body}" || true
    rm -f "${hdr}" "${body}"
    exit 1
  fi

  python3 - "${body}" "${expected_code}" "${name}" <<'PY'
import json, sys

path = sys.argv[1]
expected_code = sys.argv[2]
case_name = sys.argv[3]

with open(path, "r", encoding="utf-8") as f:
    j = json.load(f)

assert j["ok"] is False
assert j["error_version"] == 1
assert j["error"]["code"] == expected_code
assert isinstance(j["error"]["message"], str) and j["error"]["message"]
assert isinstance(j["error"]["details"], dict)

details = j["error"]["details"]

if case_name.startswith("Validation "):
    errs = details.get("errors")
    assert isinstance(errs, list) and len(errs) >= 1
    loc = errs[0].get("loc")
    assert isinstance(loc, list)
    if "field:" in case_name:
        field = case_name.split("field:",1)[1].strip()
        assert field in loc, (field, loc)
elif case_name.startswith("Unknown command"):
    assert details.get("normalized_command") == "__does_not_exist__"
elif case_name.startswith("Confirm token not found"):
    assert details.get("reason") == "token_not_found"
elif case_name.startswith("Rate limited"):
    assert details.get("key_type") == "client_id"
    assert isinstance(details.get("max"), int)
    assert isinstance(details.get("window_s"), int)
    ra = details.get("retry_after_s")
    assert isinstance(ra, int) and ra >= 0

print("OK:", j["error"]["code"])
PY

  rm -f "${hdr}" "${body}"
}

run_case "Validation error (missing command)" "422" "KERNEL_VALIDATION_ERROR" '{}'
run_case "Validation missing field field:client_id" "422" "KERNEL_VALIDATION_ERROR" '{"command":"__does_not_exist__"}'
run_case "Validation blank field field:client_id" "422" "KERNEL_VALIDATION_ERROR" '{"command":"__does_not_exist__","client_id":"   "}'
run_case "Validation extra field field:hacker" "422" "KERNEL_VALIDATION_ERROR" '{"command":"__does_not_exist__","client_id":"test-client","hacker":1}'
run_case "Unknown command" "400" "KERNEL_UNKNOWN_COMMAND" '{"command":"__does_not_exist__","client_id":"test-client"}'
run_case "Confirm token not found" "403" "CONFIRMATION_FAILED" '{"command":"health","client_id":"test-client","confirm_token":"CONFIRM-DOESNOTEXIST"}'

echo "== Confirm token expired =="

# 1) PROPOSE echo
propose_raw="$(curl -s --http1.1 --max-time 5 -X POST "$BASE/v1/brain/command" \
  -H "Content-Type: application/json" \
  -d '{"command":"echo","client_id":"test-client","payload":{"text":"expire-me"}}')"

etoken="$(echo "$propose_raw" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')"
if [ -z "$etoken" ]; then
  echo "FAIL: missing token in propose response (expire test)"
  echo "$propose_raw"
  exit 1
fi

# 2) FORCE-EXPIRE proposal timestamp INSIDE the api container
docker compose -f docker-compose.dev.yml exec -T api sh -lc "python3 - << 'PY2'
import json
from pathlib import Path
p = Path('/app/ops/audit/proposals.jsonl')
lines = p.read_text(encoding='utf-8').splitlines()
out = []
for line in lines:
    o = json.loads(line)
    if o.get('token') == '$etoken':
        o['timestamp'] = '1970-01-01T00:00:00'
    out.append(json.dumps(o))
p.write_text('\\n'.join(out) + '\\n', encoding='utf-8')
print('expired')
PY2"

# 3) CONFIRM (should 403 CONFIRMATION_FAILED + reason=token_expired)
resp="$(curl -s -i --http1.1 --max-time 5 -X POST "$BASE/v1/brain/command" \
  -H "Content-Type: application/json" \
  -d "{\"command\":\"echo\",\"client_id\":\"test-client\",\"payload\":{\"text\":\"expire-me\"},\"confirm_token\":\"$etoken\"}")"

status=$(echo "$resp" | head -n 1 | awk '{print $2}')
body=$(echo "$resp" | awk 'BEGIN{RS="\r\n\r\n"} NR==2{print}')

if [ "$status" != "403" ]; then
  echo "FAIL: expected 403, got $status (expire test)"
  echo "$resp" | head -n 60
  exit 1
fi

BODY="$body" python3 - <<'PY3'
import json, os
j = json.loads(os.environ["BODY"])
assert j["ok"] is False
assert j["error_version"] == 1
assert j["error"]["code"] == "CONFIRMATION_FAILED"
assert j["error"]["details"].get("reason") == "token_expired"
print("OK: token_expired invariant frozen")
PY3




echo "== Validation error (unknown payload field for registered command) =="
resp=$(curl -s -i -X POST "$BASE/v1/brain/command" \
  -H "Content-Type: application/json" \
  -d '{"command":"health","client_id":"test-client","payload":{"hacker":true}}')

status=$(echo "$resp" | head -n 1 | awk '{print $2}')
body=$(echo "$resp" | awk 'BEGIN{RS="\r\n\r\n"} NR==2{print}')

if [ "$status" != "400" ]; then
  echo "FAIL: expected 400, got $status"
  echo "$resp" | head -n 30
  exit 1
fi

BODY="$body" python3 - <<'PY'
import json,os
j = json.loads(os.environ["BODY"])
assert j["ok"] is False
assert j["error"]["code"] == "KERNEL_VALIDATION_ERROR"
print("OK: KERNEL_VALIDATION_ERROR")
PY


# --- Rate limit test (client_id-based) ---
RATE_CLIENT="golden-rate-$(date +%s)"
PAYLOAD='{"command":"__does_not_exist__","client_id":"'"${RATE_CLIENT}"'"}'

# Hit max+1 times (default max=30)
for i in $(seq 1 31); do
  curl -sS --http1.1 --max-time 5 \
    -H "Content-Type: application/json" \
    -X POST "${BASE}/v1/brain/command" \
    -d "${PAYLOAD}" > /dev/null
done

run_case "Rate limited" "429" "RATE_LIMITED" "${PAYLOAD}"

echo "== Positive confirm path (echo) =="

# 1) PROPOSE
propose_raw="$(curl -s --http1.1 --max-time 5 -X POST "$BASE/v1/brain/command" \
  -H "Content-Type: application/json" \
  -d '{"command":"echo","client_id":"test-client","payload":{"text":"hello"}}')"

# Extract token (expects: "token":"CONFIRM-xxxxxxxx")
token="$(echo "$propose_raw" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')"

if [ -z "$token" ]; then
  echo "FAIL: missing token in propose response"
  echo "$propose_raw"
  exit 1
fi

# 2) CONFIRM
confirm_raw="$(curl -s --http1.1 --max-time 5 -X POST "$BASE/v1/brain/command" \
  -H "Content-Type: application/json" \
  -d "{\"command\":\"echo\",\"client_id\":\"test-client\",\"payload\":{\"text\":\"hello\"},\"confirm_token\":\"$token\"}")"

echo "$confirm_raw" | grep -q '"status":"CONFIRMED"' || { echo "FAIL: expected CONFIRMED"; echo "$confirm_raw"; exit 1; }
echo "$confirm_raw" | grep -q '"echo":"hello"' || { echo "FAIL: expected echo hello"; echo "$confirm_raw"; exit 1; }

echo "OK: CONFIRM echo happy path"


echo "PASS: golden error contract stable + rate limit"

echo "== Permit-gated MEMORY_APPEND (DEV OFF should fail) =="

BASE_DEV_OFF="http://127.0.0.1:8011"
export HBAR_IDENTITY_SECRET="dev-secret-please-change"

ASSERTION="$(python3 - <<'PY'
import os, time, json, hmac, hashlib, base64
def b64url(x): return base64.urlsafe_b64encode(x).decode().rstrip("=")
secret=os.environ["HBAR_IDENTITY_SECRET"].encode()
now=int(time.time())
header=b64url(json.dumps({"alg":"HS256","typ":"HBAR_ASSERTION","v":1}).encode())
claims=b64url(json.dumps({
  "iss":"hbar-brain","sub":"root","aud":"golden-tests",
  "strain_id":"test","trust_tier":"root",
  "iat":now,"exp":now+900,"v":1
}).encode())
msg=f"{header}.{claims}".encode()
sig=b64url(hmac.new(secret,msg,hashlib.sha256).digest())
print(f"{header}.{claims}.{sig}")
PY
)"

# issue permit on DEV ON kernel (8010) so issuance is available, then use it against DEV OFF confirm
PTOKEN="$(curl -sS "http://127.0.0.1:8010/v1/brain/command" \
  -H "Content-Type: application/json" \
  -H "X-HBAR-Assertion: $ASSERTION" \
  -d '{"command":"permit issue MEMORY_WRITE 900 golden","client_id":"golden-tests"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["token"])')"

PERMIT="$(curl -sS "http://127.0.0.1:8010/v1/brain/command" \
  -H "Content-Type: application/json" \
  -H "X-HBAR-Assertion: $ASSERTION" \
    -d '{"command":"permit issue MEMORY_WRITE 900 golden","client_id":"golden-tests","confirm_token":"'"$PTOKEN"'"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["result"]["permit"])' \
  | tr -d '\n')"

# PROPOSE memory append on DEV OFF
MTOKEN="$(curl -sS "$BASE_DEV_OFF/v1/brain/command" \
  -H "Content-Type: application/json" \
  -d '{"command":"memory append","client_id":"golden-tests","payload":{"text":"permit-backed append"}}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["token"])')"

# CONFIRM memory append on DEV OFF (should 403 KERNEL_EXECUTION_CLASS_FORBIDDEN)
resp="$(curl -sS -i "$BASE_DEV_OFF/v1/brain/command" \
  -H "Content-Type: application/json" \
  -H "X-HBAR-Assertion: $ASSERTION" \
  -H "X-HBAR-Permit: $PERMIT" \
    -d '{"command":"memory append","client_id":"golden-tests","payload":{"text":"permit-backed append"},"confirm_token":"'"$MTOKEN"'"}')"

status=$(echo "$resp" | head -n 1 | awk '{print $2}')
body=$(echo "$resp" | awk 'BEGIN{RS="\r\n\r\n"} NR==2{print}')

if [ "$status" != "403" ]; then
  echo "FAIL: expected 403, got $status"
  echo "$resp" | head -n 60
  exit 1
fi

BODY="$body" python3 - <<'PY'
import json,os
j = json.loads(os.environ["BODY"])
assert j["ok"] is False
assert j["error"]["code"] == "KERNEL_EXECUTION_CLASS_FORBIDDEN"
print("OK: DEV OFF MEMORY_APPEND blocked")
PY


echo "== Permit-gated MEMORY_APPEND (DEV ON should pass) =="
BASE="http://127.0.0.1:8010"
BASE="$BASE" CLIENT_ID="golden-tests" scripts/golden_permit_memory_append.sh \
  | grep -q '"effect":"memory_append"' \
  || { echo "FAIL: expected effect memory_append"; exit 1; }
echo "OK: DEV ON MEMORY_APPEND allowed with permit + root assertion"
