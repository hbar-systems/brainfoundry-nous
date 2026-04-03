#!/usr/bin/env python3
"""
Generate an ED25519 keypair for this brain node.

Run once at brain setup, from the repo root:
    python scripts/generate_keypair.py

Output: two lines ready to paste into .env
    BRAIN_PRIVATE_KEY=<base64url>   ← secret, never share
    BRAIN_PUBLIC_KEY=<base64url>    ← public, goes in .env + brain_identity.yaml

The public key is published via GET /identity so other brains can verify
tokens you sign with issue_federation_assertion().
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.identity.core import generate_brain_keypair

private_key, public_key = generate_brain_keypair()

print("# Add these to your .env file")
print(f"BRAIN_PRIVATE_KEY={private_key}")
print(f"BRAIN_PUBLIC_KEY={public_key}")
