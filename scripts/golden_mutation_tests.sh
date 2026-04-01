#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8010}"

fail() { echo "FAIL: $1"; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "missing dependency: $1"; }

need curl; need awk; need head; need sed; need grep; need openssl; need date; need tr

split_body() {
  awk 'BEGIN{in_body=0}
       in_body{print}
       /^[[:space:]]*$/{in_body=1}' <<<"$1"
}

extract_json_string_field() {
  local body="$1"
  local key="$2"
  local m
  m="$(printf "%s" "$body" | grep -oE "\"$key\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" | head -n1 || true)"
  if [[ -z "$m" ]]; then
    echo ""
    return 0
  fi
  printf "%s" "$m" | sed -E "s/.*\"$key\"[[:space:]]*:[[:space:]]*\"([^\"]*)\".*/\1/"
}

b64url() {
  openssl base64 -A | tr '+/' '-_' | tr -d '='
}

hmac_sha256_b64url() {
  local secret="$1"
  openssl dgst -sha256 -mac HMAC -macopt "key:${secret}" -binary | b64url
}

mint_assertion() {
  # usage: mint_assertion <secret> <client_id> <exp_epoch> <trust_tier>
  local secret="$1"
  local client_id="$2"
  local exp="$3"
  local trust_tier="$4"
  local now iat header claims header_b64 claims_b64 signing_input sig

  now="$(date +%s)"
  iat="$now"

  header='{"alg":"HS256","typ":"HBAR_ASSERTION","v":1}'
  claims="$(printf '{"iss":"hbar-brain","sub":"root","aud":"%s","strain_id":"test","trust_tier":"%s","iat":%s,"exp":%s,"v":1}' \
    "$client_id" "$trust_tier" "$iat" "$exp")"

  header_b64="$(printf "%s" "$header" | b64url)"
  claims_b64="$(printf "%s" "$claims" | b64url)"
  signing_input="${header_b64}.${claims_b64}"
  sig="$(printf "%s" "$signing_input" | hmac_sha256_b64url "$secret")"
  printf "%s.%s" "$signing_input" "$sig"
}

mint_expired_assertion() {
  local secret="$1"
  local client_id="$2"
  local now exp
  now="$(date +%s)"
  exp="$((now - 60))"
  mint_assertion "$secret" "$client_id" "$exp" "root"
}

mint_valid_assertion() {
  local secret="$1"
  local client_id="$2"
  local now exp
  now="$(date +%s)"
  exp="$((now + 900))"
  mint_assertion "$secret" "$client_id" "$exp" "root"
}

echo "== PROPOSE success (MEMORY_APPEND) =="

raw_propose="$(
  curl -sS -i \
    -H "Content-Type: application/json" \
    -d '{
      "command":"memory append",
      "client_id":"golden-tests",
      "payload":{"text":"golden propose success"}
    }' \
    "$BASE/v1/brain/command"
)"

status_propose="$(printf "%s" "$raw_propose" | head -n 1 | awk '{print $2}')"
body_propose="$(split_body "$raw_propose")"

if [[ "$status_propose" != "200" ]]; then
  echo "$raw_propose"
  fail "expected 200, got $status_propose"
fi

st="$(extract_json_string_field "$body_propose" "status")"
tok="$(extract_json_string_field "$body_propose" "token")"
[[ "$st" == "PROPOSED" ]] || { echo "$body_propose"; fail "expected status=PROPOSED, got '$st'"; }
[[ "$tok" == CONFIRM-* ]] || { echo "$body_propose"; fail "expected token starting with CONFIRM-, got '$tok'"; }

echo "OK: PROPOSED + token present: $tok"

echo "== CONFIRM without assertion -> 401 =="

raw_confirm_401="$(
  curl -sS -i \
    -H "Content-Type: application/json" \
    -d "{
      \"command\":\"memory append\",
      \"client_id\":\"golden-tests\",
      \"payload\":{\"text\":\"golden confirm no assertion\"},
      \"confirm_token\":\"$tok\"
    }" \
    "$BASE/v1/brain/command"
)"

status_confirm_401="$(printf "%s" "$raw_confirm_401" | head -n 1 | awk '{print $2}')"
if [[ "$status_confirm_401" != "401" ]]; then
  echo "$raw_confirm_401"
  fail "expected 401, got $status_confirm_401"
fi
echo "OK: got 401 as expected"

echo "== CONFIRM with expired assertion -> 403 =="

: "${HBAR_IDENTITY_SECRET:?HBAR_IDENTITY_SECRET must be set in env for this golden test}"

expired="$(mint_expired_assertion "$HBAR_IDENTITY_SECRET" "golden-tests")"

raw_confirm_403="$(
  curl -sS -i \
    -H "Content-Type: application/json" \
    -H "X-HBAR-Assertion: $expired" \
    -d "{
      \"command\":\"memory append\",
      \"client_id\":\"golden-tests\",
      \"payload\":{\"text\":\"golden confirm expired assertion\"},
      \"confirm_token\":\"$tok\"
    }" \
    "$BASE/v1/brain/command"
)"

status_confirm_403="$(printf "%s" "$raw_confirm_403" | head -n 1 | awk '{print $2}')"
body_confirm_403="$(split_body "$raw_confirm_403")"

if [[ "$status_confirm_403" != "403" ]]; then
  echo "$raw_confirm_403"
  fail "expected 403, got $status_confirm_403"
fi

msg="$(extract_json_string_field "$body_confirm_403" "message")"
[[ "$msg" == "Invalid assertion" ]] || { echo "$body_confirm_403"; fail "expected message='Invalid assertion', got '$msg'"; }
echo "OK: got 403 Invalid assertion (expired) as expected"

echo "== CONFIRM with valid assertion but DEV flag OFF -> 403 =="

valid="$(mint_valid_assertion "$HBAR_IDENTITY_SECRET" "golden-tests")"

raw_confirm_dev_off="$(
  curl -sS -i \
    -H "Content-Type: application/json" \
    -H "X-HBAR-Assertion: $valid" \
    -d "{
      \"command\":\"memory append\",
      \"client_id\":\"golden-tests\",
      \"payload\":{\"text\":\"golden confirm valid assertion dev off\"},
      \"confirm_token\":\"$tok\"
    }" \
    "$BASE/v1/brain/command"
)"

status_dev_off="$(printf "%s" "$raw_confirm_dev_off" | head -n 1 | awk '{print $2}')"
body_dev_off="$(split_body "$raw_confirm_dev_off")"

if [[ "$status_dev_off" != "403" ]]; then
  echo "$raw_confirm_dev_off"
  fail "expected 403, got $status_dev_off"
fi

code="$(extract_json_string_field "$body_dev_off" "code")"
msg2="$(extract_json_string_field "$body_dev_off" "message")"

[[ "$code" == "KERNEL_EXECUTION_CLASS_FORBIDDEN" ]] || { echo "$body_dev_off"; fail "expected code=KERNEL_EXECUTION_CLASS_FORBIDDEN, got '$code'"; }
[[ "$msg2" == "MEMORY_APPEND not permitted in this build." ]] || { echo "$body_dev_off"; fail "expected dev-off message, got '$msg2'"; }

echo "OK: got 403 forbidden (DEV flag off) as expected"
echo "PASS: golden mutation (propose + 401 + expired 403 + dev-off 403)"
