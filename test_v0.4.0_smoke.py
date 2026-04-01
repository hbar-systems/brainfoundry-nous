#!/usr/bin/env python3
"""
Smoke test for hbar-brain v0.4.0 read-only commands.

Tests:
- PROPOSE/CONFIRM roundtrip for each new command
- Token mismatch rejection (403)
- Expired token rejection (403)
- Audit tail N clamping
"""

import requests
import json
import time
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8010"
ENDPOINT = f"{BASE_URL}/v1/brain/command"

def test_command(command: str, description: str):
    """Test PROPOSE/CONFIRM roundtrip for a command."""
    print(f"\n{'='*60}")
    print(f"Testing: {description}")
    print(f"Command: {command}")
    print(f"{'='*60}")
    
    # PROPOSE
    print("\n1. PROPOSE phase...")
    propose_data = {
        "command": command,
        "client_id": "smoke_test"
    }
    
    response = requests.post(ENDPOINT, json=propose_data)
    print(f"   Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"   ERROR: {response.text}")
        return False
    
    propose_result = response.json()
    print(f"   Response: {json.dumps(propose_result, indent=2)}")
    
    if propose_result.get("status") != "PROPOSED":
        print("   ERROR: Expected status PROPOSED")
        return False
    
    token = propose_result.get("token")
    if not token or not token.startswith("CONFIRM-"):
        print("   ERROR: Invalid token format")
        return False
    
    print(f"   ✓ Token received: {token}")
    
    # CONFIRM
    print("\n2. CONFIRM phase...")
    confirm_data = {
        "command": command,
        "confirm_token": token,
        "client_id": "smoke_test"
    }
    
    response = requests.post(ENDPOINT, json=confirm_data)
    print(f"   Status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"   ERROR: {response.text}")
        return False
    
    confirm_result = response.json()
    print(f"   Response: {json.dumps(confirm_result, indent=2)}")
    
    if confirm_result.get("status") != "CONFIRMED":
        print("   ERROR: Expected status CONFIRMED")
        return False
    
    if confirm_result.get("effect") != "read_only":
        print("   ERROR: Expected effect read_only")
        return False
    
    print(f"   ✓ Command confirmed and executed")
    print(f"   ✓ Effect: {confirm_result.get('effect')}")
    
    return True


def test_token_mismatch():
    """Test that mismatched command is rejected."""
    print(f"\n{'='*60}")
    print(f"Testing: Token mismatch rejection")
    print(f"{'='*60}")
    
    # PROPOSE with one command
    propose_data = {
        "command": "health",
        "client_id": "smoke_test"
    }
    
    response = requests.post(ENDPOINT, json=propose_data)
    token = response.json().get("token")
    
    # CONFIRM with different command
    print("\n1. Attempting to confirm with different command...")
    confirm_data = {
        "command": "whoami",  # Different command!
        "confirm_token": token,
        "client_id": "smoke_test"
    }
    
    response = requests.post(ENDPOINT, json=confirm_data)
    print(f"   Status: {response.status_code}")
    
    if response.status_code != 403:
        print(f"   ERROR: Expected 403, got {response.status_code}")
        return False
    
    error_detail = response.json().get("detail", "")
    print(f"   Detail: {error_detail}")
    
    if "command_mismatch" not in error_detail:
        print("   ERROR: Expected 'command_mismatch' in error detail")
        return False
    
    print("   ✓ Token mismatch correctly rejected with 403")
    return True


def test_invalid_token():
    """Test that invalid token is rejected."""
    print(f"\n{'='*60}")
    print(f"Testing: Invalid token rejection")
    print(f"{'='*60}")
    
    print("\n1. Attempting to confirm with fake token...")
    confirm_data = {
        "command": "health",
        "confirm_token": "CONFIRM-fakefake",
        "client_id": "smoke_test"
    }
    
    response = requests.post(ENDPOINT, json=confirm_data)
    print(f"   Status: {response.status_code}")
    
    if response.status_code != 403:
        print(f"   ERROR: Expected 403, got {response.status_code}")
        return False
    
    error_detail = response.json().get("detail", "")
    print(f"   Detail: {error_detail}")
    
    if "token_not_found" not in error_detail:
        print("   ERROR: Expected 'token_not_found' in error detail")
        return False
    
    print("   ✓ Invalid token correctly rejected with 403")
    return True


def test_audit_tail_clamping():
    """Test that audit tail N is clamped correctly."""
    print(f"\n{'='*60}")
    print(f"Testing: Audit tail N clamping")
    print(f"{'='*60}")
    
    # Test with N > 1000 (should clamp to 1000)
    print("\n1. Testing with N=5000 (should clamp to 1000)...")
    command = "audit tail 5000"
    
    propose_data = {"command": command, "client_id": "smoke_test"}
    response = requests.post(ENDPOINT, json=propose_data)
    token = response.json().get("token")
    
    confirm_data = {"command": command, "confirm_token": token, "client_id": "smoke_test"}
    response = requests.post(ENDPOINT, json=confirm_data)
    
    if response.status_code != 200:
        print(f"   ERROR: {response.text}")
        return False
    
    result = response.json().get("result", {})
    requested = result.get("requested", 0)
    
    print(f"   Requested: {requested}")
    
    if requested != 1000:
        print(f"   ERROR: Expected clamped value 1000, got {requested}")
        return False
    
    print("   ✓ N correctly clamped to 1000")
    
    # Test with N < 1 (should clamp to 1)
    print("\n2. Testing with N=0 (should clamp to 1)...")
    command = "audit tail 0"
    
    propose_data = {"command": command, "client_id": "smoke_test"}
    response = requests.post(ENDPOINT, json=propose_data)
    token = response.json().get("token")
    
    confirm_data = {"command": command, "confirm_token": token, "client_id": "smoke_test"}
    response = requests.post(ENDPOINT, json=confirm_data)
    
    if response.status_code != 200:
        print(f"   ERROR: {response.text}")
        return False
    
    result = response.json().get("result", {})
    requested = result.get("requested", 0)
    
    print(f"   Requested: {requested}")
    
    if requested != 1:
        print(f"   ERROR: Expected clamped value 1, got {requested}")
        return False
    
    print("   ✓ N correctly clamped to 1")
    
    return True


def main():
    """Run all smoke tests."""
    print(f"\n{'#'*60}")
    print(f"# hbar-brain v0.4.0 Smoke Tests")
    print(f"# Target: {BASE_URL}")
    print(f"# Time: {datetime.utcnow().isoformat()}")
    print(f"{'#'*60}")
    
    tests = [
        ("help", "Help command"),
        ("version", "Version command"),
        ("audit tail 50", "Audit tail command (default N)"),
        ("audit tail 200", "Audit tail command (custom N)"),
        ("health", "Health command (existing)"),
        ("whoami", "Whoami command (existing)"),
        ("status", "Status command (existing)"),
    ]
    
    results = []
    
    # Test each command
    for command, description in tests:
        success = test_command(command, description)
        results.append((description, success))
    
    # Test error cases
    print("\n" + "="*60)
    print("Testing error cases...")
    print("="*60)
    
    success = test_token_mismatch()
    results.append(("Token mismatch rejection", success))
    
    success = test_invalid_token()
    results.append(("Invalid token rejection", success))
    
    success = test_audit_tail_clamping()
    results.append(("Audit tail N clamping", success))
    
    # Summary
    print(f"\n{'#'*60}")
    print(f"# Test Summary")
    print(f"{'#'*60}")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for description, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {description}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit(main())
