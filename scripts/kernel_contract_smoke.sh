#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   KERNEL_BASE_URL=http://localhost:8010 ./scripts/kernel_contract_smoke.sh
#
# Optional:
#   KERNEL_API_KEY=... (sent as X-API-Key)

BASE_URL="${KERNEL_BASE_URL:-http://localhost:8010}"

hdr=(-H "Content-Type: application/json")
if [[ -n "${KERNEL_API_KEY:-}" ]]; then
  hdr+=(-H "X-API-Key: ${KERNEL_API_KEY}")
fi

echo "== kernel contract smoke =="
echo "BASE_URL=${BASE_URL}"
echo

# 1) PROPOSE must return ok:true and data.status=PROPOSED and data.token exists
resp="$(curl -sS -X POST "${BASE_URL}/v1/brain/command" "${hdr[@]}" -d '{"command":"health"}')"
echo "$resp" | python3 -c 'import json,sys; j=json.load(sys.stdin); assert j.get("ok") is True, j; d=j.get("data") or {}; assert d.get("status")=="PROPOSED", j; assert isinstance(d.get("token"), str) and d["token"].startswith("CONFIRM-"), j; print("PASS: propose envelope")'

token="$(echo "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["token"])')"

# 2) CONFIRM read_only must return ok:true and data.status=CONFIRMED and effect=read_only
resp2="$(curl -sS -X POST "${BASE_URL}/v1/brain/command" "${hdr[@]}" -d "{\"command\":\"health\",\"confirm_token\":\"${token}\"}")"
echo "$resp2" | python3 -c 'import json,sys; j=json.load(sys.stdin); assert j.get("ok") is True, j; d=j.get("data") or {}; assert d.get("status")=="CONFIRMED", j; assert d.get("effect")=="read_only", j; print("PASS: confirm read_only envelope")'

# 3) Confirmation failure must be ok:false with canonical error.code=CONFIRMATION_FAILED (403)
bad="$(curl -sS -o /tmp/kernel_bad.json -w "%{http_code}" -X POST "${BASE_URL}/v1/brain/command" "${hdr[@]}" -d '{"command":"health","confirm_token":"CONFIRM-NOTREAL"}')"
test "$bad" = "403"
cat /tmp/kernel_bad.json | python3 -c 'import json,sys; j=json.load(sys.stdin); assert j.get("ok") is False, j; e=j.get("error") or {}; assert e.get("code")=="CONFIRMATION_FAILED", j; print("PASS: confirmation_failed canonical error")'

echo
echo "ALL PASSED"
