#!/usr/bin/env python3
"""Re-embed document_embeddings rows whose embedding is NULL.

Pairs with scripts/migrate_embedding_dim.sh. After --force ALTERs a non-empty
brain from vector(384) to vector(1024), the existing rows survive with their
content + metadata intact but the embedding column is NULL until refilled.
This script walks those rows, embeds them with the brain's running model,
and UPDATEs each row in batches.

USAGE
  scripts/reembed_null_embeddings.py <ssh_host> [--batch-size N] [--dry-run]

DESIGN
- Runs the embedding loop INSIDE the api container via `ssh + docker compose
  exec`, so it picks up the brain's actual EMBEDDING_MODEL_NAME and existing
  DATABASE_URL from the container env. No model duplication, no creds shipped.
- Idempotent: a re-run after success processes 0 rows and exits 0.
- Batches default to 32 to match the SentenceTransformer internal default
  and the BATCH constant in _stream_ingest_path_b.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys


# Runs inside the api container. Reads REEMBED_BATCH_SIZE / REEMBED_DRY_RUN
# from container env (injected via `docker compose exec -e`).
REMOTE_PYTHON = r"""
import os, sys, psycopg2

BATCH = int(os.environ.get("REEMBED_BATCH_SIZE", "32"))
DRY   = os.environ.get("REEMBED_DRY_RUN") == "1"

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

cur.execute("SELECT count(*) FROM document_embeddings WHERE embedding IS NULL")
total = cur.fetchone()[0]
print(f"[reembed] NULL-embedding rows: {total}", flush=True)

if total == 0:
    print("[reembed] nothing to do", flush=True)
    sys.exit(0)

if DRY:
    cur.execute("SELECT id, document_name, length(content) AS chars FROM document_embeddings WHERE embedding IS NULL ORDER BY id")
    for row_id, doc, chars in cur.fetchall():
        print(f"  id={row_id} doc={doc} content_chars={chars}", flush=True)
    print(f"[reembed] dry-run: would process {total} rows in batches of {BATCH}", flush=True)
    sys.exit(0)

print("[reembed] loading embedding model...", flush=True)
from api.embeddings.model import get_model
model = get_model()
print(f"[reembed] model loaded; processing in batches of {BATCH}", flush=True)

done = 0
while True:
    cur.execute(
        "SELECT id, content FROM document_embeddings WHERE embedding IS NULL ORDER BY id LIMIT %s",
        (BATCH,),
    )
    rows = cur.fetchall()
    if not rows:
        break
    ids = [r[0] for r in rows]
    contents = [r[1] for r in rows]
    embeddings = model.encode(contents)
    for row_id, emb in zip(ids, embeddings):
        emb_str = "[" + ",".join(map(str, emb)) + "]"
        cur.execute(
            "UPDATE document_embeddings SET embedding = %s::vector WHERE id = %s",
            (emb_str, row_id),
        )
    conn.commit()
    done += len(rows)
    print(f"[reembed] {done}/{total}", flush=True)

cur.execute("SELECT count(*) FROM document_embeddings WHERE embedding IS NULL")
remaining = cur.fetchone()[0]
print(f"[reembed] complete; NULL rows remaining: {remaining}", flush=True)
sys.exit(0 if remaining == 0 else 1)
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("host", help="SSH host (e.g. nous.brainfoundry.ai)")
    ap.add_argument("--batch-size", type=int, default=32, help="rows per encode batch (default 32)")
    ap.add_argument("--dry-run", action="store_true", help="report what would be re-embedded, no writes")
    args = ap.parse_args()

    key = os.environ.get("BRAINFOUNDRY_KEY") or os.path.expanduser("~/.ssh/id_ed25519_brainfoundry_automation")

    docker_args = [
        "docker", "compose", "-f", "/home/hbar/brain/docker-compose.yml",
        "exec", "-T",
        "-e", f"REEMBED_BATCH_SIZE={args.batch_size}",
    ]
    if args.dry_run:
        docker_args += ["-e", "REEMBED_DRY_RUN=1"]
    docker_args += ["api", "python3", "-c", REMOTE_PYTHON]

    # Quote the docker command for ssh transport.
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
