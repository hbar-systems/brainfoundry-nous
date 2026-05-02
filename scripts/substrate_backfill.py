#!/usr/bin/env python3
"""Substrate-floor backfill — generate attestations for pre-existing RAG corpus.

Per Q2 in ops/prompts/2026-05-01_brainfoundry-substrate-floor.md, the yury,
hbar, and e2e brains have artifacts ingested before the attestation ledger
existed. This script scans `document_embeddings`, groups chunks by
`document_name`, reconstructs each document, and writes one attestation per
document with `backfilled = true`.

Caveats — please read before running:

1. Reconstructed text is not byte-identical to the original ingested
   artifact (chunk_text uses 50-word overlap, joins with spaces, may strip
   whitespace differently). The `backfilled` flag exists to preserve the
   auditability of this gap. Going forward, attestations are written at
   ingestion time and use the original byte-exact hash.

2. `source_type` defaults: documents whose name starts with `chat-` are
   labelled `conversation`, all others `document`. Operator can adjust the
   mapping with --source-map.

3. `first_person_attestation` defaults to `authored_by_owner` per Q1
   recommendation (option a, owner-trust marking). Operators that ingested
   scraped material should pass --label-derived <pattern> to mark those
   document_names as `derived` instead. Patterns are SQL LIKE-style
   (e.g. `wikipedia-%`).

4. `timestamp_ingested` is set to the MIN(created_at) over each document's
   chunks — the actual ingestion time, not now.

5. The brain must have BRAIN_PRIVATE_KEY available (same env as the running
   server) so attestations can be signed.

DRY-RUN by default. Pass --commit to actually write rows. ALWAYS run dry-run
first against the target brain and review the summary.

Usage:

    python scripts/substrate_backfill.py                           # dry run
    python scripts/substrate_backfill.py --commit                  # write
    python scripts/substrate_backfill.py --label-derived 'scrape-%' --commit
    python scripts/substrate_backfill.py --limit 5                 # preview 5

Recommended sequencing (per the implementation prompt §sequencing.8):
    1. yury-brain  — observe results (counts, sample hashes, log lines)
    2. hbar-brain  — if yury was clean
    3. e2e-brain   — last
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

# Allow `python scripts/substrate_backfill.py` from repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402

from api import substrate  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Substrate-floor backfill")
    p.add_argument("--commit", action="store_true",
                   help="write rows. without it: dry-run, prints summary only.")
    p.add_argument("--limit", type=int, default=0,
                   help="limit to N documents (0 = all). Useful for preview.")
    p.add_argument("--label-derived", action="append", default=[],
                   metavar="PATTERN",
                   help="document_name LIKE-pattern to label as derived "
                        "(can pass multiple).")
    p.add_argument("--source-map", action="append", default=[],
                   metavar="PATTERN=TYPE",
                   help="document_name LIKE-pattern to source_type override "
                        "(e.g. 'chat-%%=conversation').")
    return p.parse_args()


def classify_source(name: str, mapping: List[Tuple[str, str]]) -> str:
    for pattern, src_type in mapping:
        if _like_match(name, pattern):
            return src_type
    if name.startswith("chat-"):
        return "conversation"
    return "document"


def _like_match(name: str, pattern: str) -> bool:
    """Minimal LIKE matcher — supports % only. % at end means prefix match."""
    if pattern.endswith("%") and not pattern.startswith("%"):
        return name.startswith(pattern[:-1])
    if pattern.startswith("%") and pattern.endswith("%"):
        return pattern[1:-1] in name
    if pattern.startswith("%"):
        return name.endswith(pattern[1:])
    return name == pattern


def main() -> int:
    args = parse_args()

    db = os.getenv("DATABASE_URL")
    if not db:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2

    if not os.getenv("BRAIN_PRIVATE_KEY"):
        print("BRAIN_PRIVATE_KEY not set — cannot sign attestations", file=sys.stderr)
        return 2

    derived_patterns: List[str] = args.label_derived
    source_map: List[Tuple[str, str]] = []
    for entry in args.source_map:
        if "=" not in entry:
            print(f"--source-map entry must be PATTERN=TYPE: {entry}", file=sys.stderr)
            return 2
        pattern, src_type = entry.split("=", 1)
        source_map.append((pattern, src_type))

    conn = psycopg2.connect(db)
    conn.autocommit = False

    # Ensure target table exists before we try to write.
    substrate.init_tables(conn=conn)
    conn.commit()

    docs: Dict[str, Dict] = defaultdict(lambda: {
        "chunks": [],
        "earliest": None,
    })

    with conn.cursor() as cur:
        cur.execute(
            """SELECT document_name, content, created_at, metadata
               FROM document_embeddings
               ORDER BY document_name, id"""
        )
        rows = cur.fetchall()

    for name, content, created_at, _meta in rows:
        if not name:
            continue
        d = docs[name]
        d["chunks"].append(content or "")
        if d["earliest"] is None or (created_at and created_at < d["earliest"]):
            d["earliest"] = created_at

    items = list(docs.items())
    if args.limit > 0:
        items = items[: args.limit]

    summary = {"total": 0, "would_write": 0, "skipped_existing": 0, "by_source": defaultdict(int)}

    # Pre-flight: which content_hashes already exist in the ledger?
    existing: set[str] = set()
    with conn.cursor() as cur:
        try:
            cur.execute("SELECT content_hash FROM artifact_attestations")
            existing = {r[0] for r in cur.fetchall()}
        except psycopg2.errors.UndefinedTable:
            conn.rollback()

    print(f"# Backfill plan ({'COMMIT' if args.commit else 'DRY-RUN'})")
    print(f"# documents found: {len(docs)}, will process: {len(items)}")
    print()

    for name, d in items:
        summary["total"] += 1
        # Deterministic reconstruction — chunks already ordered by id (insert order).
        reconstructed = "\n".join(d["chunks"])
        content_hash = substrate.content_hash_of(reconstructed)
        byte_size = len(reconstructed.encode("utf-8"))

        is_derived = any(_like_match(name, p) for p in derived_patterns)
        first_person = "derived" if is_derived else "authored_by_owner"
        source_type = classify_source(name, source_map)

        ts_iso = d["earliest"].isoformat() if d["earliest"] else None

        if content_hash in existing:
            summary["skipped_existing"] += 1
            print(f"  SKIP existing  {name}  ({content_hash[:23]}…)")
            continue

        summary["would_write"] += 1
        summary["by_source"][source_type] += 1
        print(
            f"  WRITE          {name}  "
            f"src={source_type}  fp={first_person}  bytes={byte_size}  "
            f"ts={ts_iso}  {content_hash[:23]}…"
        )

        if args.commit:
            substrate.record_attestation(
                content_hash=content_hash,
                source_type=source_type,
                byte_size=byte_size,
                first_person_attestation=first_person,
                document_name=name,
                backfilled=True,
                timestamp_ingested=ts_iso,
                conn=conn,
            )

    if args.commit:
        conn.commit()
    conn.close()

    print()
    print("# Summary")
    print(f"#   total processed:   {summary['total']}")
    print(f"#   would write:       {summary['would_write']}")
    print(f"#   skipped (existing):{summary['skipped_existing']}")
    print(f"#   by source_type:    {dict(summary['by_source'])}")
    print()
    if not args.commit:
        print("# DRY-RUN — nothing written. Re-run with --commit to apply.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
