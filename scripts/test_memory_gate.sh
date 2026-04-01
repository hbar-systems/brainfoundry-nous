#!/bin/bash
# Memory Governance Smoke Test
# Tests that document uploads are denied by default and only succeed after NodeOS approval.
#
# Prerequisites: docker compose -f docker-compose.dev.yml up -d
# Usage: bash scripts/test_memory_gate.sh

set -euo pipefail

API_URL="${API_URL:-http://localhost:8010}"
NODEOS_URL="${NODEOS_URL:-http://localhost:8011}"
TEST_FILE=$(mktemp /tmp/test_doc_XXXXXX.txt)
echo "This is a test document for memory governance verification." > "$TEST_FILE"

PASS=0
FAIL=0

pass() { echo "  ✅ PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  ❌ FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "═══════════════════════════════════════════════════"
echo "  Memory Governance Smoke Test"
echo "  API:    $API_URL"
echo "  NodeOS: $NODEOS_URL"
echo "═══════════════════════════════════════════════════"
echo ""

# ── Test 1: Upload without permit_id → 400 ──────────────────────────
echo "1️⃣  Upload without permit_id (expect 400)"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$API_URL/documents/upload" \
  -F "file=@$TEST_FILE")

if [ "$HTTP_CODE" = "400" ]; then
  pass "No permit_id → 400 (denied)"
else
  fail "Expected 400, got $HTTP_CODE"
fi
echo ""

# ── Test 2: Get a loop permit from NodeOS ────────────────────────────
echo "2️⃣  Requesting loop permit from NodeOS"
PERMIT_RESP=$(curl -s -X POST "$NODEOS_URL/v1/loops/request" \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "test-node",
    "agent_id": "smoke-test",
    "loop_type": "admin",
    "ttl_seconds": 300,
    "scopes": ["write:documents"],
    "reason": "Memory gate smoke test"
  }')

PERMIT_ID=$(echo "$PERMIT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['permit_id'])" 2>/dev/null || echo "")
if [ -z "$PERMIT_ID" ]; then
  fail "Could not obtain permit_id from NodeOS"
  echo "  Response: $PERMIT_RESP"
  echo ""
  echo "Aborting — NodeOS must be running."
  rm -f "$TEST_FILE"
  exit 1
fi
pass "Got permit_id: $PERMIT_ID"
echo ""

# ── Test 3: Upload with permit_id but no proposal_id → 202 PENDING ──
echo "3️⃣  Upload with permit_id, no proposal_id (expect 202 PENDING)"
UPLOAD_RESP=$(curl -s -w "\n%{http_code}" \
  -X POST "$API_URL/documents/upload?permit_id=$PERMIT_ID" \
  -F "file=@$TEST_FILE")

HTTP_CODE=$(echo "$UPLOAD_RESP" | tail -1)
BODY=$(echo "$UPLOAD_RESP" | sed '$d')

if [ "$HTTP_CODE" = "202" ]; then
  pass "Got 202 — proposal submitted, no embeddings written"
else
  fail "Expected 202, got $HTTP_CODE"
  echo "  Body: $BODY"
fi

PROPOSAL_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['proposal_id'])" 2>/dev/null || echo "")
if [ -z "$PROPOSAL_ID" ]; then
  fail "No proposal_id in response"
  echo "  Body: $BODY"
  rm -f "$TEST_FILE"
  exit 1
fi
echo "  proposal_id: $PROPOSAL_ID"
echo ""

# ── Test 4: Upload with PENDING proposal_id → 403 ───────────────────
echo "4️⃣  Upload with PENDING proposal_id (expect 403)"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$API_URL/documents/upload?proposal_id=$PROPOSAL_ID" \
  -F "file=@$TEST_FILE")

if [ "$HTTP_CODE" = "403" ]; then
  pass "PENDING proposal → 403 (denied)"
else
  fail "Expected 403, got $HTTP_CODE"
fi
echo ""

# ── Test 5: Approve the proposal via NodeOS ──────────────────────────
echo "5️⃣  Approving proposal via NodeOS"
DECIDE_RESP=$(curl -s -X POST "$NODEOS_URL/v1/memory/$PROPOSAL_ID/decide" \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "APPROVE",
    "decided_by": "smoke-test-admin",
    "note": "Smoke test approval"
  }')

DECIDE_STATUS=$(echo "$DECIDE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "")
if [ "$DECIDE_STATUS" = "APPROVED" ]; then
  pass "Proposal approved"
else
  fail "Expected APPROVED, got: $DECIDE_STATUS"
  echo "  Response: $DECIDE_RESP"
fi
echo ""

# ── Test 6: Upload with APPROVED proposal_id → 200 success ──────────
echo "6️⃣  Upload with APPROVED proposal_id (expect 200)"
UPLOAD_RESP2=$(curl -s -w "\n%{http_code}" \
  -X POST "$API_URL/documents/upload?proposal_id=$PROPOSAL_ID" \
  -F "file=@$TEST_FILE")

HTTP_CODE=$(echo "$UPLOAD_RESP2" | tail -1)
BODY=$(echo "$UPLOAD_RESP2" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
  pass "APPROVED proposal → 200 (embeddings written)"
  STORED=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('embeddings_stored',0))" 2>/dev/null || echo "0")
  echo "  embeddings_stored: $STORED"
else
  fail "Expected 200, got $HTTP_CODE"
  echo "  Body: $BODY"
fi
echo ""

# ── Test 7: Verify audit trail ───────────────────────────────────────
echo "7️⃣  Checking NodeOS audit trail"
AUDIT_RESP=$(curl -s "$NODEOS_URL/v1/audit/events?limit=5")
AUDIT_COUNT=$(echo "$AUDIT_RESP" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [ "$AUDIT_COUNT" -gt 0 ]; then
  pass "Audit trail has $AUDIT_COUNT events"
else
  fail "No audit events found"
fi
echo ""

# ── Cleanup ──────────────────────────────────────────────────────────
rm -f "$TEST_FILE"

echo "═══════════════════════════════════════════════════"
echo "  Results: $PASS passed, $FAIL failed"
echo "═══════════════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
