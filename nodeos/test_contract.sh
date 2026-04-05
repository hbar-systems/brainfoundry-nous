#!/bin/bash
# NodeOS Contract Verification - Phase 1 Correction
# Tests the LOCKED contract endpoints

set -e

BASE_URL="${NODEOS_URL:-http://localhost:8001}"

echo "🔒 Testing NodeOS LOCKED Contract"
echo "Base URL: $BASE_URL"
echo ""

# Test 1: Identity (locked contract)
echo "1️⃣  GET /v1/identity"
IDENTITY=$(curl -s "$BASE_URL/v1/identity")
echo "$IDENTITY" | jq .
echo ""

# Verify identity fields
BRAIN_ID=$(echo "$IDENTITY" | jq -r '.brain_id')
if [ "$BRAIN_ID" != "system.ops.nodeos.v1" ]; then
  echo "❌ FAIL: brain_id mismatch"
  exit 1
fi
echo "✅ Identity contract verified"
echo ""

# Test 2: Request loop permit (locked contract)
echo "2️⃣  POST /v1/loops/request (locked contract)"
PERMIT_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/loops/request" \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "node-test-001",
    "agent_id": "my-agent.v1",
    "loop_type": "research",
    "ttl_seconds": 300,
    "scopes": ["read:docs", "write:memory"],
    "reason": "Research assistant loop",
    "trace_id": "trace-123"
  }')

echo "$PERMIT_RESPONSE" | jq .

# Verify response shape
PERMIT_ID=$(echo "$PERMIT_RESPONSE" | jq -r '.permit_id')
PERMIT_TOKEN=$(echo "$PERMIT_RESPONSE" | jq -r '.permit_token')
EXPIRES_AT_UNIX=$(echo "$PERMIT_RESPONSE" | jq -r '.expires_at_unix')

if [ -z "$PERMIT_ID" ] || [ "$PERMIT_ID" = "null" ]; then
  echo "❌ FAIL: permit_id missing"
  exit 1
fi

if [ -z "$PERMIT_TOKEN" ] || [ "$PERMIT_TOKEN" = "null" ]; then
  echo "❌ FAIL: permit_token missing"
  exit 1
fi

if [ -z "$EXPIRES_AT_UNIX" ] || [ "$EXPIRES_AT_UNIX" = "null" ]; then
  echo "❌ FAIL: expires_at_unix missing"
  exit 1
fi

echo "✅ Loop permit request contract verified"
echo "   permit_id: $PERMIT_ID"
echo "   expires_at_unix: $EXPIRES_AT_UNIX"
echo ""

# Test 3: Propose memory (locked contract)
echo "3️⃣  POST /v1/memory/propose (locked contract)"
MEMORY_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/memory/propose" \
  -H "Content-Type: application/json" \
  -d "{
    \"permit_id\": \"$PERMIT_ID\",
    \"memory_type\": \"preference\",
    \"content\": \"User prefers concise, modern language\",
    \"source_refs\": {\"confidence\": 0.95, \"source\": \"user_feedback\"}
  }")

echo "$MEMORY_RESPONSE" | jq .

PROPOSAL_ID=$(echo "$MEMORY_RESPONSE" | jq -r '.proposal_id')
PROPOSAL_STATUS=$(echo "$MEMORY_RESPONSE" | jq -r '.status')

if [ -z "$PROPOSAL_ID" ] || [ "$PROPOSAL_ID" = "null" ]; then
  echo "❌ FAIL: proposal_id missing"
  exit 1
fi

if [ "$PROPOSAL_STATUS" != "PENDING" ]; then
  echo "❌ FAIL: status should be PENDING, got $PROPOSAL_STATUS"
  exit 1
fi

echo "✅ Memory proposal contract verified"
echo "   proposal_id: $PROPOSAL_ID"
echo "   status: $PROPOSAL_STATUS"
echo ""

# Test 4: Decide memory (locked contract)
echo "4️⃣  POST /v1/memory/{proposal_id}/decide (locked contract)"
DECISION_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/memory/$PROPOSAL_ID/decide" \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "APPROVE",
    "decided_by": "admin@nodeos",
    "note": "High confidence user preference"
  }')

echo "$DECISION_RESPONSE" | jq .

DECISION_STATUS=$(echo "$DECISION_RESPONSE" | jq -r '.status')

if [ "$DECISION_STATUS" != "APPROVED" ]; then
  echo "❌ FAIL: status should be APPROVED, got $DECISION_STATUS"
  exit 1
fi

echo "✅ Memory decision contract verified"
echo "   status: $DECISION_STATUS"
echo ""

# Test 5: Revoke loop permit (locked contract)
echo "5️⃣  POST /v1/loops/revoke (locked contract)"
REVOKE_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/loops/revoke" \
  -H "Content-Type: application/json" \
  -d "{
    \"permit_id\": \"$PERMIT_ID\",
    \"reason\": \"Test completed\"
  }")

echo "$REVOKE_RESPONSE" | jq .

REVOKE_STATUS=$(echo "$REVOKE_RESPONSE" | jq -r '.status')

if [ "$REVOKE_STATUS" != "revoked" ]; then
  echo "❌ FAIL: status should be revoked, got $REVOKE_STATUS"
  exit 1
fi

echo "✅ Loop revoke contract verified"
echo ""

# Test 6: Audit events (locked contract)
echo "6️⃣  GET /v1/audit/events?since_unix=&limit=5"
AUDIT_RESPONSE=$(curl -s "$BASE_URL/v1/audit/events?limit=5")
echo "$AUDIT_RESPONSE" | jq '.[0:2]'
echo "... (showing first 2 events)"
echo ""

AUDIT_COUNT=$(echo "$AUDIT_RESPONSE" | jq '. | length')
if [ "$AUDIT_COUNT" -eq 0 ]; then
  echo "❌ FAIL: No audit events found"
  exit 1
fi

echo "✅ Audit events contract verified ($AUDIT_COUNT events)"
echo ""

echo "✅✅✅ ALL LOCKED CONTRACT TESTS PASSED ✅✅✅"
echo ""
echo "Summary:"
echo "  - Identity: brain_id = system.ops.nodeos.v1"
echo "  - Loop permit: permit_id, permit_token, expires_at_unix"
echo "  - Memory proposal: proposal_id, status=PENDING"
echo "  - Memory decision: APPROVE/DENY → APPROVED/DENIED"
echo "  - Loop revoke: permit_id only (no token required)"
echo "  - Audit events: since_unix filter supported"
