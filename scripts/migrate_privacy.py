#!/usr/bin/env python3
"""Migrate an existing brain to the memory privacy gate (2026-10-14).

Pairs with vector-db/init.sql and api/privacy.py: each chunk may carry
`metadata.privacy` = 'open' | 'local-only'. A chunk without the key is open,
so NO ROW IS REWRITTEN; the migration only ensures the partial index
document_embeddings_privacy_idx and reports how many chunks are local-only
(and how many carry an unknown level, which retrieval withholds from closed
reasoners). Since 2026-10-15 it also adds chat_sessions.local_only_at (the
session mark; NULL = unmarked, so again no row is rewritten).

The API startup hook creates the same index on every boot, so a brain that has
been redeployed with this code is already migrated; this script is the explicit,
reportable path and is safe to run any number of times.

USAGE
  scripts/migrate_privacy.py <ssh_host>     run inside the brain's api container
  scripts/migrate_privacy.py --local        run here, against $DATABASE_URL

Deploy the code first (the remote run imports api.privacy from the container).
Mirrors scripts/backfill_memory_type.py: no credentials shipped; the container's
DATABASE_URL is used.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys

REMOTE_PYTHON = (
    "import json, os, psycopg2\n"
    "from api.privacy import migrate\n"
    "conn = psycopg2.connect(os.environ['DATABASE_URL'])\n"
    "print(json.dumps(migrate(conn)), flush=True)\n"
    "conn.close()\n"
)


def run_local() -> int:
    import psycopg2
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from api.privacy import migrate
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        print(json.dumps(migrate(conn)), flush=True)
    finally:
        conn.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("host", nargs="?", help="SSH host (e.g. hbar.brainfoundry.ai)")
    ap.add_argument("--local", action="store_true", help="use $DATABASE_URL here")
    args = ap.parse_args()
    if args.local:
        return run_local()
    if not args.host:
        ap.error("give an ssh host or --local")

    key = os.environ.get("BRAINFOUNDRY_KEY") or os.path.expanduser("~/.ssh/id_ed25519_brainfoundry_automation")
    docker_args = ["docker", "compose", "-f", "/home/hbar/brain/docker-compose.yml",
                   "exec", "-T", "api", "python3", "-c", REMOTE_PYTHON]
    remote_cmd = " ".join(shlex.quote(a) for a in docker_args)
    ssh_cmd = ["ssh", "-i", key, "-o", "StrictHostKeyChecking=accept-new",
               f"hbar@{args.host}", remote_cmd]
    print(f"== {args.host} ==", flush=True)
    return subprocess.run(ssh_cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
