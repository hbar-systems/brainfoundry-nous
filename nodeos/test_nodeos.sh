#!/bin/bash
# NodeOS Authority Service - Test Script
# Tests all endpoints with curl

set -e

BASE_URL="${NODEOS_URL:-http://localhost:8011}"
AGENT_ID="test-agent-$(date +%s)"

echo "🧪 Testing NodeOS Authority Service"
echo "Base URL: $BASE_URL"
echo "Agent ID: $AGENT_ID"
echo ""

# Test 1: Identity
echo "1️⃣  Testing GET /v1/identity"
curl -s "$BASE_URL/v1/identity" | jq .
echo ""

# Test 2: Health Check
echo "2️⃣  Testing GET /health"
curl -s "$BASE_URL/health" | jq .
echo ""

# Test 3: Request Loop Permit
echo "3️⃣  Testing POST /v1/loops/request"
PERMIT_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/loops/request" \
  -H "Content-Type: application/json" \
  -d "{
    \"agent_id\": \"$AGENT_ID\",
    \"purpose\": \"Test loop execution\",
    \"max_iterations\": 5,
    \"duration_minutes\": 10
  }")

echo "$PERMIT_RESPONSE" | jq .
PERMIT_TOKEN=$(echo "$PERMIT_RESPONSE" | jq -r '.permit_token')
PERMIT_ID=$(echo "$PERMIT_RESPONSE" | jq -r '.permit_id')
echo "Permit Token: $PERMIT_TOKEN"
echo ""

# Test 4: Check Permit Status
echo "4️⃣  Testing GET /v1/loops/status/{permit_id}"
curl -s "$BASE_URL/v1/loops/status/$PERMIT_ID" | jq .
echo ""

# Test 5: Propose Memory
echo "5️⃣  Testing POST /v1/memory/propose"
MEMORY_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/memory/propose" \
  -H "Content-Type: application/json" \
  -d "{
    \"agent_id\": \"$AGENT_ID\",
    \"memory_type\": \"fact\",
    \"content\": \"Test memory content from automated test\",
    \"metadata\": {\"source\": \"test_script\", \"confidence\": 0.99}
  }")

echo "$MEMORY_RESPONSE" | jq .
PROPOSAL_ID=$(echo "$MEMORY_RESPONSE" | jq -r '.proposal_id')
echo ""

# Test 6: List Memory Proposals
echo "6️⃣  Testing GET /v1/memory/proposals"
curl -s "$BASE_URL/v1/memory/proposals?status=PENDING&limit=5" | jq .
echo ""

# Test 7: Approve Memory Proposal
echo "7️⃣  Testing POST /v1/memory/{proposal_id}/decide (APPROVED)"
curl -s -X POST "$BASE_URL/v1/memory/$PROPOSAL_ID/decide" \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "APPROVED",
    "reason": "Test approval from automated test"
  }' | jq .
echo ""

# Test 8: View Audit Events
echo "8️⃣  Testing GET /v1/audit/events"
curl -s "$BASE_URL/v1/audit/events?limit=10" | jq '.[:3]'
echo "... (showing first 3 events)"
echo ""

# Test 9: Filter Audit Events by Agent
echo "9️⃣  Testing GET /v1/audit/events?agent_id=$AGENT_ID"
curl -s "$BASE_URL/v1/audit/events?agent_id=$AGENT_ID&limit=20" | jq .
echo ""

# Test 10: Revoke Loop Permit
echo "🔟 Testing POST /v1/loops/revoke"
curl -s -X POST "$BASE_URL/v1/loops/revoke" \
  -H "Content-Type: application/json" \
  -d "{
    \"permit_token\": \"$PERMIT_TOKEN\",
    \"agent_id\": \"$AGENT_ID\",
    \"reason\": \"Test completed\"
  }" | jq .
echo ""

# Test 11: Verify Permit is Revoked
echo "1️⃣1️⃣  Verifying permit is revoked"
curl -s "$BASE_URL/v1/loops/status/$PERMIT_ID" | jq .
echo ""

echo "✅ All tests completed!"
echo ""
echo "Summary:"
echo "  - Permit ID: $PERMIT_ID"
echo "  - Proposal ID: $PROPOSAL_ID"
echo "  - Agent ID: $AGENT_ID"
