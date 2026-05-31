#!/usr/bin/env python3
"""Backfill memory-type + provenance onto pre-existing document_embeddings rows.

Pairs with the v0.8.x schema change (vector-db/init.sql + api/memory_type.py):
every chunk now carries a `mem_type` (semantic/reflective/untrusted/ephemeral)
and provenance. New ingests stamp this at write time; this one-shot backfill
tags the chunks that landed BEFORE the change.

Backfill rules (only touches rows where metadata->>'mem_type' IS NULL):
- consolidation summaries (metadata.source LIKE 'consolidation%' or a
  `consolidated_at` key) -> reflective / inferred / source_trust 0.9. These are
  derived beliefs the brain wrote, not directly-observed artifacts.
- everything else -> semantic / observed / source_trust 1.0. Pre-change chunks
  were operator-approved uploads, which are trusted.
- content_hash is then enriched (best-effort) by joining document_name to the
  signed artifact_attestations ledger, restoring the chunk -> attestation link.

NOT REQUIRED for correctness: api/memory_type.trust_prior() treats an untagged
(None) chunk as semantic, so retrieval works without running this. The backfill
just makes the tags explicit (indexable, visible, filterable).

USAGE
  scripts/backfill_memory_type.py <ssh_host> [--dry-run]

DESIGN
- Mirrors scripts/reembed_null_embeddings.py: runs the SQL INSIDE the api
  container via `ssh + docker compose exec`, picking up the container's
  DATABASE_URL. No creds shipped, no model needed (pure SQL).
- Idempotent: a re-run after success updates 0 rows and exits 0.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys


# Runs inside the api container. Reads BACKFILL_DRY_RUN from container env.
# SQL is written as adjacent double-quoted literals (implicit concatenation) so
# no inner triple-quote is needed inside this r-string; SQL's own single quotes
# pass through untouched.
REMOTE_PYTHON = r"""
import os, sys, psycopg2

DRY = os.environ.get("BACKFILL_DRY_RUN") == "1"

conn = psycopg2.connect(os.environ["DATABASE_URL"])
conn.autocommit = False
cur = conn.cursor()

cur.execute("SELECT count(*) FROM document_embeddings WHERE metadata->>'mem_type' IS NULL")
total = cur.fetchone()[0]
print(f"[backfill] untagged rows: {total}", flush=True)
if total == 0:
    print("[backfill] nothing to do", flush=True)
    sys.exit(0)

# How many of those look like consolidation (reflective) vs the rest (semantic).
CONSOLIDATION = (
    " WHERE metadata->>'mem_type' IS NULL"
    "   AND (metadata->>'source' LIKE 'consolidation%' OR metadata ? 'consolidated_at')"
)
cur.execute("SELECT count(*) FROM document_embeddings" + CONSOLIDATION)
reflective_n = cur.fetchone()[0]
semantic_n = total - reflective_n
print(f"[backfill] -> reflective: {reflective_n}   -> semantic: {semantic_n}", flush=True)

if DRY:
    print("[backfill] dry-run: no writes", flush=True)
    sys.exit(0)

# Reflective (derived summaries).
cur.execute(
    "UPDATE document_embeddings"
    " SET metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object("
    "   'mem_type', 'reflective', 'derivation', 'inferred',"
    "   'ingested_by', 'operator', 'source_trust', 0.9)"
    + CONSOLIDATION
)
print(f"[backfill] tagged reflective: {cur.rowcount}", flush=True)

# Semantic (everything else — operator-approved uploads).
cur.execute(
    "UPDATE document_embeddings"
    " SET metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object("
    "   'mem_type', 'semantic', 'derivation', 'observed',"
    "   'ingested_by', 'operator', 'source_trust', 1.0)"
    " WHERE metadata->>'mem_type' IS NULL"
)
print(f"[backfill] tagged semantic: {cur.rowcount}", flush=True)

# Commit the type tags before the (optional) enrichment so a missing
# attestations table can't roll the tagging back.
conn.commit()

# Enrich content_hash from the signed attestation ledger (best-effort join on
# document_name). Skips cleanly if the table is absent on this brain.
try:
    cur.execute(
        "UPDATE document_embeddings de"
        " SET metadata = de.metadata || jsonb_build_object('content_hash', aa.content_hash)"
        " FROM artifact_attestations aa"
        " WHERE de.document_name = aa.document_name"
        "   AND (de.metadata->>'content_hash') IS NULL"
    )
    print(f"[backfill] enriched content_hash from attestations: {cur.rowcount}", flush=True)
except psycopg2.errors.UndefinedTable:
    conn.rollback()
    print("[backfill] artifact_attestations absent — content_hash enrichment skipped", flush=True)

conn.commit()

cur.execute("SELECT count(*) FROM document_embeddings WHERE metadata->>'mem_type' IS NULL")
remaining = cur.fetchone()[0]
print(f"[backfill] complete; untagged rows remaining: {remaining}", flush=True)
sys.exit(0 if remaining == 0 else 1)
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("host", help="SSH host (e.g. hbar.brainfoundry.ai)")
    ap.add_argument("--dry-run", action="store_true", help="report counts, no writes")
    args = ap.parse_args()

    key = os.environ.get("BRAINFOUNDRY_KEY") or os.path.expanduser("~/.ssh/id_ed25519_brainfoundry_automation")

    docker_args = [
        "docker", "compose", "-f", "/home/hbar/brain/docker-compose.yml",
        "exec", "-T",
    ]
    if args.dry_run:
        docker_args += ["-e", "BACKFILL_DRY_RUN=1"]
    docker_args += ["api", "python3", "-c", REMOTE_PYTHON]

    remote_cmd = " ".join(shlex.quote(a) for a in docker_args)
    ssh_cmd = [
        "ssh", "-i", key, "-o", "StrictHostKeyChecking=accept-new",
        f"hbar@{args.host}",
        remote_cmd,
    ]

    print(f"== {args.host} ==", flush=True)
    result = subprocess.run(ssh_cmd)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
