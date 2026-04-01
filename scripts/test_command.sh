#!/bin/bash

# Test script for the v0.3 read-only commands

API_URL="http://localhost:8010"

echo "Testing health command - PROPOSE"
HEALTH_RESPONSE=$(curl -s -X POST "$API_URL/v1/brain/command" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "health",
    "client_id": "test-script"
  }')

echo "$HEALTH_RESPONSE"
HEALTH_TOKEN=$(echo "$HEALTH_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo -e "\nTesting health command - CONFIRM"
curl -s -X POST "$API_URL/v1/brain/command" \
  -H "Content-Type: application/json" \
  -d "{
    \"command\": \"health\",
    \"confirm_token\": \"$HEALTH_TOKEN\",
    \"client_id\": \"test-script\"
  }"

echo -e "\n\nTesting status command - PROPOSE"
STATUS_RESPONSE=$(curl -s -X POST "$API_URL/v1/brain/command" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "status",
    "client_id": "test-script"
  }')

echo "$STATUS_RESPONSE"
STATUS_TOKEN=$(echo "$STATUS_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo -e "\nTesting status command - CONFIRM"
curl -s -X POST "$API_URL/v1/brain/command" \
  -H "Content-Type: application/json" \
  -d "{
    \"command\": \"status\",
    \"confirm_token\": \"$STATUS_TOKEN\",
    \"client_id\": \"test-script\"
  }"

echo -e "\n\nTesting whoami command - PROPOSE"
WHOAMI_RESPONSE=$(curl -s -X POST "$API_URL/v1/brain/command" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "whoami",
    "client_id": "test-script"
  }')

echo "$WHOAMI_RESPONSE"
WHOAMI_TOKEN=$(echo "$WHOAMI_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo -e "\nTesting whoami command - CONFIRM"
curl -s -X POST "$API_URL/v1/brain/command" \
  -H "Content-Type: application/json" \
  -d "{
    \"command\": \"whoami\",
    \"confirm_token\": \"$WHOAMI_TOKEN\",
    \"client_id\": \"test-script\"
  }"

echo -e "\n\nTesting non-whitelisted command - PROPOSE"
UNKNOWN_RESPONSE=$(curl -s -X POST "$API_URL/v1/brain/command" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "list users",
    "client_id": "test-script"
  }')

echo "$UNKNOWN_RESPONSE"
UNKNOWN_TOKEN=$(echo "$UNKNOWN_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

echo -e "\nTesting non-whitelisted command - CONFIRM"
curl -s -X POST "$API_URL/v1/brain/command" \
  -H "Content-Type: application/json" \
  -d "{
    \"command\": \"list users\",
    \"confirm_token\": \"$UNKNOWN_TOKEN\",
    \"client_id\": \"test-script\"
  }"

echo -e "\n"
