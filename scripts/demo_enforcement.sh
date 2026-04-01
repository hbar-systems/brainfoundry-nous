#!/bin/bash
# hbar-brain enforcement demo: refuse -> grant -> act -> revoke -> blocked + audit
# Requires: stack running via docker-compose.dev.yml with patches 1-3 applied.
# Usage: bash scripts/demo_enforcement.sh

set -e

API="${API_URL:-http://127.0.0.1:8010}"
NODEOS="${NODEOS_URL:-http://127.0.0.1:8011}"

echo "=== STEP 1: REFUSE (no permit) ==="
HTTP_CODE=$(curl -s -o /tmp/demo_step1.json -w "%{http_code}" -X POST "$API/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"hello"}]}')

if [ "$HTTP_CODE" != "403" ]; then
  echo "FAIL: expected 403, got $HTTP_CODE"
  cat /tmp/demo_step1.json
  exit 1
fi
echo "PASS: inference refused without permit (HTTP $HTTP_CODE)"
cat /tmp/demo_step1.json | python3 -m json.tool 2>/dev/null || cat /tmp/demo_step1.json
echo ""

echo "=== STEP 2: GRANT (request loop permit) ==="
PERMIT=$(curl -s -X POST "$NODEOS/v1/loops/request" \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "hbar.brain.v1",
    "agent_id": "operator",
    "loop_type": "chat",
    "ttl_seconds": 300,
    "scopes": ["chat:completions", "memory:write"],
    "reason": "Daily conversation session"
  }')

PERMIT_ID=$(echo "$PERMIT" | python3 -c "import sys,json; print(json.load(sys.stdin)['permit_id'])")
echo "PASS: permit granted: $PERMIT_ID"
echo "$PERMIT" | python3 -m json.tool
echo ""

echo "=== STEP 3: ACT (chat with valid permit) ==="
RESPONSE=$(curl -s -X POST "$API/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"permit_id\": \"$PERMIT_ID\",
    \"messages\":[{\"role\":\"user\",\"content\":\"What are you?\"}]
  }")

CONTENT=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['choices'][0]['message']['content'][:200])" 2>/dev/null)
if [ -z "$CONTENT" ]; then
  echo "FAIL: no response content"
  echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
  exit 1
fi
echo "PASS: inference succeeded"
echo "Response: $CONTENT"
echo ""

echo "=== STEP 4: REVOKE ==="
REVOKE=$(curl -s -X POST "$NODEOS/v1/loops/revoke" \
  -H "Content-Type: application/json" \
  -d "{\"permit_id\": \"$PERMIT_ID\", \"reason\": \"Demo revocation\"}")
echo "$REVOKE" | python3 -m json.tool
echo "PASS: permit revoked"
echo ""

echo "=== STEP 5: BLOCKED (revoked permit rejected) ==="
HTTP_CODE=$(curl -s -o /tmp/demo_step5.json -w "%{http_code}" -X POST "$API/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"permit_id\": \"$PERMIT_ID\",
    \"messages\":[{\"role\":\"user\",\"content\":\"Can you still hear me?\"}]
  }")

if [ "$HTTP_CODE" != "403" ]; then
  echo "FAIL: expected 403, got $HTTP_CODE"
  cat /tmp/demo_step5.json
  exit 1
fi
echo "PASS: inference blocked after revocation (HTTP $HTTP_CODE)"
cat /tmp/demo_step5.json | python3 -m json.tool 2>/dev/null || cat /tmp/demo_step5.json
echo ""

echo "=== AUDIT EXPORT ==="
curl -s "$NODEOS/v1/audit/events?limit=10" | python3 -m json.tool
echo ""
echo "=== ALL 5 STEPS PASSED ==="
