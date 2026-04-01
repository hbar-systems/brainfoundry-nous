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
  [[ -n "$m" ]] || { echo ""; return 0; }
  printf "%s" "$m" | sed -E "s/.*\"$key\"[[:space:]]*:[[:space:]]*\"([^\"]*)\".*/\1/"
}

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }
hmac_sha256_b64url() { local secret="$1"; openssl dgst -sha256 -mac HMAC -macopt "key:${secret}" -binary | b64url; }

mint_valid_assertion() {
  local secret="$1" client_id="$2"
  local now exp iat header claims header_b64 claims_b64 signing_input sig
  now="$(date +%s)"; iat="$now"; exp="$((now + 900))"
  header='{"alg":"HS256","typ":"HBAR_ASSERTION","v":1}'
  claims="$(printf '{"iss":"hbar-brain","sub":"root","aud":"%s","strain_id":"test","trust_tier":"root","iat":%s,"exp":%s,"v":1}' "$client_id" "$iat" "$exp")"
  header_b64="$(printf "%s" "$header" | b64url)"
  claims_b64="$(printf "%s" "$claims" | b64url)"
  signing_input="${header_b64}.${claims_b64}"
  sig="$(printf "%s" "$signing_input" | hmac_sha256_b64url "$secret")"
  printf "%s.%s" "$signing_input" "$sig"
}



mint_valid_permit_memory_write() {
  local secret="$1" client_id="$2"
  local now exp iat header claims header_b64 claims_b64 signing_input sig
  now="$(date +%s)"; iat="$now"; exp="$((now + 900))"
  header='{"alg":"HS256","typ":"HBAR_PERMIT","v":1}'
  claims="$(printf '{"iss":"hbar-brain","sub":"root","aud":"%s","iat":%s,"exp":%s,"reason":"golden","constraints":{},"typ":"MEMORY_WRITE","v":1}' \
    "$client_id" "$iat" "$exp")"
  header_b64="$(printf "%s" "$header" | b64url)"
  claims_b64="$(printf "%s" "$claims" | b64url)"
  signing_input="${header_b64}.${claims_b64}"
  sig="$(printf "%s" "$signing_input" | hmac_sha256_b64url "$secret")"
  printf "%s.%s" "$signing_input" "$sig"
}


: "${HBAR_IDENTITY_SECRET:?HBAR_IDENTITY_SECRET must be set}"
ASSERTION="$(mint_valid_assertion "$HBAR_IDENTITY_SECRET" "golden-tests")"
PERMIT="$(mint_valid_permit_memory_write "$HBAR_IDENTITY_SECRET" "golden-tests")"


echo "== PROPOSE success (MEMORY_APPEND) =="

raw_propose="$(
  curl -sS -i -H "Content-Type: application/json" \
    -d '{"command":"memory append","client_id":"golden-tests","payload":{"text":"golden propose dev-on"}}' \
    "$BASE/v1/brain/command"
)"
status_propose="$(printf "%s" "$raw_propose" | head -n 1 | awk '{print $2}')"
body_propose="$(split_body "$raw_propose")"
[[ "$status_propose" == "200" ]] || { echo "$raw_propose"; fail "expected 200, got $status_propose"; }

tok="$(extract_json_string_field "$body_propose" "token")"
[[ "$tok" == CONFIRM-* ]] || { echo "$body_propose"; fail "expected CONFIRM-* token, got '$tok'"; }

echo "OK: token $tok"

echo "== CONFIRM with valid assertion (DEV ON) -> 200 =="

raw_confirm="$(
  curl -sS -i \
    -H "Content-Type: application/json" \
    -H "X-HBAR-Assertion: $ASSERTION" \
    -H "X-HBAR-Permit: $PERMIT" \
    -d "{
      \"command\":\"memory append\",
      \"client_id\":\"golden-tests\",
      \"payload\":{\"text\":\"golden confirm dev-on\"},
      \"confirm_token\":\"$tok\"
    }" \
    "$BASE/v1/brain/command"
)"

status_confirm="$(printf "%s" "$raw_confirm" | head -n 1 | awk '{print $2}')"
body_confirm="$(split_body "$raw_confirm")"

[[ "$status_confirm" == "200" ]] || { echo "$raw_confirm"; fail "expected 200, got $status_confirm"; }

st="$(extract_json_string_field "$body_confirm" "status")"
eff="$(extract_json_string_field "$body_confirm" "effect")"
[[ "$st" == "CONFIRMED" ]] || { echo "$body_confirm"; fail "expected status=CONFIRMED, got '$st'"; }
[[ "$eff" == "memory_append" ]] || { echo "$body_confirm"; fail "expected effect=memory_append, got '$eff'"; }

echo "OK: confirmed + effect memory_append"
echo "PASS: golden mutation DEV ON"
