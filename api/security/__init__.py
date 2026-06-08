"""api/security — the brain's prompt-safety primitives.

One place for the trust-boundary helpers that keep untrusted content (retrieved
documents, web results, future email/notes/tool output) out of the system role
and clearly marked as data, not instructions. See api/security/untrusted.py and
THREAT_MODEL.md at the repo root.
"""
