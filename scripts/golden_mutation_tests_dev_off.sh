#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8011}"
fail() { echo "FAIL: $1"; exit 1; }

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

: "${HBAR_IDENTITY_SECRET:?Set HBAR_IDENTITY_SECRET first}"

ASSERTION="$(mint_valid_assertion "$HBAR_IDENTITY_SECRET" "golden-tests")"
PERMIT="$(mint_valid_permit_memory_write "$HBAR_IDENTITY_SECRET" "golden-tests")"

echo "== PROPOSE (DEV OFF) =="

raw_propose="$(
  curl -sS -i -H "Content-Type: application/json" \
    -d '{"command":"memory append","client_id":"golden-tests","payload":{"text":"dev-off test"}}' \
    "$BASE/v1/brain/command"
)"

status_propose="$(printf "%s" "$raw_propose" | head -n 1 | awk '{print $2}')"
[[ "$status_propose" == "200" ]] || { echo "$raw_propose"; fail "expected 200 propose"; }

token="$(printf "%s" "$raw_propose" | grep -oE '"token":"CONFIRM-[^"]+"' | cut -d'"' -f4)"

echo "== CONFIRM (valid assertion, DEV OFF) -> 403 =="

raw_confirm="$(
  curl -sS -i \
    -H "Content-Type: application/json" \
    -H "X-HBAR-Assertion: $ASSERTION" \
    -H "X-HBAR-Permit: $PERMIT" \
    -d "{
      \"command\":\"memory append\",
      \"client_id\":\"golden-tests\",
      \"payload\":{\"text\":\"dev-off confirm\"},
      \"confirm_token\":\"$token\"
    }" \
    "$BASE/v1/brain/command"
)"

status_confirm="$(printf "%s" "$raw_confirm" | head -n 1 | awk '{print $2}')"

if [[ "$status_confirm" != "403" ]]; then
  echo "$raw_confirm"
  fail "expected 403, got $status_confirm"
fi

echo "PASS: DEV OFF correctly forbids MEMORY_APPEND"
