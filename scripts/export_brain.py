#!/usr/bin/env python3
"""scripts/export_brain.py — Track G1: whole-brain export.

The sovereignty primitive: produce a single .tar.gz you can back up, relocate,
restore, or hand to anyone. Pair with scripts/import_brain.py (G2).

WHAT THE ARCHIVE CONTAINS
  manifest.json                       — format, embedding model + dimension,
                                        brain version, timestamp, row counts
  persona/brain_persona.local.md      — the personalized identity (Track J1
                                        moved identity into this file)
  db/document_embeddings.jsonl        — the knowledge corpus + embeddings
  db/chat_sessions.jsonl              — chat sessions
  db/chat_messages.jsonl              — chat messages
  db/memory_proposals.jsonl           — NodeOS memory proposals
  config/brain_identity.yaml          — non-secret identity config

WHAT IS DELIBERATELY EXCLUDED — the archive is safe to hand to anyone:
  no .env, no API keys, no NodeOS signing/HMAC secrets, no brain private key.
  Only non-secret content + config is collected.

USAGE  (run on your laptop)
  scripts/export_brain.py <ssh_host> [--out PATH]
    <ssh_host>  brain host, e.g. nous.brainfoundry.ai or 62.238.4.20
    --out       archive path (default: ./brain-export-<host>-<UTC>.tar.gz)

  SSH as `hbar` with $HOME/.ssh/id_ed25519_brainfoundry_automation
  (override with $BRAINFOUNDRY_KEY). Matches scripts/reembed_null_embeddings.py.

DESIGN
  Orchestrator (default) runs on the laptop and SSHes to the brain. The actual
  DB reads run INSIDE the containers via `docker compose exec`: postgres tables
  through the api container's psycopg2, memory_proposals through the nodeos
  container's sqlite3. The brain repo is bind-mounted into the api container,
  so this same file is re-invoked there in --dump-pg / --probe worker mode.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

BRAIN_DIR = "/home/hbar/brain"
COMPOSE = f"docker compose -f {BRAIN_DIR}/docker-compose.yml"
SELF_IN_CONTAINER = f"{BRAIN_DIR}/scripts/export_brain.py"
ARCHIVE_FORMAT = "brainfoundry-brain-export/v1"
PG_TABLES = ("document_embeddings", "chat_sessions", "chat_messages")

# Dumps memory_proposals from the NodeOS sqlite db. Piped to `python -` inside
# the nodeos container (stdin = this program, stdout = the jsonl).
NODEOS_DUMP = r'''
import json, sqlite3, sys
con = sqlite3.connect("/data/nodeos.db")
con.row_factory = sqlite3.Row
cols = ("proposal_id","permit_id","memory_type","content","source_refs",
        "status","created_at","decided_at","decided_by","decision_note")
try:
    rows = con.execute(f"SELECT {','.join(cols)} FROM memory_proposals").fetchall()
except sqlite3.OperationalError:
    rows = []
for r in rows:
    sys.stdout.write(json.dumps({k: r[k] for k in cols}) + "\n")
sys.stderr.write(f"[worker] dumped {len(rows)} memory_proposals\n")
'''


# ============================================================================
# Worker mode — runs INSIDE the api container (invoked by the orchestrator).
# ============================================================================
def worker_dump_pg(table: str) -> int:
    """Stream one postgres table to stdout as JSON-lines. One object per row."""
    import psycopg2

    selects = {
        "document_embeddings":
            ("SELECT document_name, content, metadata, embedding::text, "
             "created_at::text FROM document_embeddings ORDER BY id",
             ("document_name", "content", "metadata", "embedding", "created_at")),
        "chat_sessions":
            ("SELECT session_id::text, model_name, title, created_at::text "
             "FROM chat_sessions ORDER BY id",
             ("session_id", "model_name", "title", "created_at")),
        "chat_messages":
            ("SELECT session_id::text, role, content, created_at::text "
             "FROM chat_messages ORDER BY id",
             ("session_id", "role", "content", "created_at")),
    }
    if table not in selects:
        sys.stderr.write(f"unknown table: {table}\n")
        return 2
    sql, cols = selects[table]
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        cur = conn.cursor()
        cur.execute(sql)
        n = 0
        for row in cur:
            # metadata (jsonb) arrives as a dict; embedding::text as a string.
            sys.stdout.write(json.dumps(dict(zip(cols, row)), default=str) + "\n")
            n += 1
        sys.stdout.flush()
        sys.stderr.write(f"[worker] dumped {n} rows from {table}\n")
        return 0
    finally:
        conn.close()


def worker_probe() -> int:
    """Print the brain's embedding dimension, model, id, version as JSON."""
    import psycopg2

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        cur = conn.cursor()
        # atttypmod of a vector(N) column is N.
        cur.execute("SELECT atttypmod FROM pg_attribute "
                    "WHERE attrelid='document_embeddings'::regclass AND attname='embedding'")
        row = cur.fetchone()
        dim = row[0] if row else None
    finally:
        conn.close()
    try:
        version = Path("/app/VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        version = "unknown"
    print(json.dumps({
        "embedding_dim": dim,
        "embedding_model": os.environ.get("EMBEDDING_MODEL_NAME", "BAAI/bge-large-en-v1.5"),
        "brain_id": os.environ.get("BRAIN_ID", ""),
        "brain_version": version,
    }))
    return 0


# ============================================================================
# Orchestrator mode — runs on the laptop.
# ============================================================================
def ssh_base(host: str) -> list:
    key = os.environ.get("BRAINFOUNDRY_KEY",
                         str(Path.home() / ".ssh" / "id_ed25519_brainfoundry_automation"))
    return ["ssh", "-i", key, "-o", "StrictHostKeyChecking=accept-new", f"hbar@{host}"]


def ssh_run(host: str, remote_cmd: str, stdin: str | None = None,
            outfile: Path | None = None) -> str:
    """Run a command on the brain host. Capture stdout to `outfile` or return it.

    When no `stdin` is supplied, stdin is /dev/null — otherwise the ssh
    subprocess would inherit and consume this process's own stdin.
    """
    cmd = ssh_base(host) + [remote_cmd]
    kw: dict = {"stderr": subprocess.PIPE}
    if stdin is not None:
        kw["input"] = stdin.encode()
    else:
        kw["stdin"] = subprocess.DEVNULL
    if outfile is not None:
        with open(outfile, "wb") as fh:
            proc = subprocess.run(cmd, stdout=fh, **kw)
        out = b""
    else:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, **kw)
        out = proc.stdout
    if proc.returncode != 0:
        raise RuntimeError(f"remote command failed ({proc.returncode}): "
                           f"{proc.stderr.decode(errors='replace').strip()}")
    return out.decode(errors="replace")


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, "rb") as fh:
        return sum(1 for line in fh if line.strip())


def orchestrate(host: str, out_path: Path) -> int:
    print(f"export_brain: source brain = {host}")

    # Preflight — the brain repo + compose stack must be present.
    ssh_run(host, f"test -d {BRAIN_DIR} && test -f {BRAIN_DIR}/docker-compose.yml")

    with tempfile.TemporaryDirectory(prefix="brain-export-") as tmp:
        stage = Path(tmp)
        (stage / "db").mkdir()
        (stage / "persona").mkdir()
        (stage / "config").mkdir()

        # 1. Probe — embedding dimension/model, brain id + version.
        print("  probing embedding dimension + brain identity...")
        probe = json.loads(ssh_run(
            host, f"cd {BRAIN_DIR} && {COMPOSE} exec -T api python {SELF_IN_CONTAINER} --probe"))
        dim = probe.get("embedding_dim")
        print(f"    embedding: {probe.get('embedding_model')} (dim {dim}) | "
              f"brain {probe.get('brain_id') or '?'} v{probe.get('brain_version')}")

        # 2. Postgres tables — via the api container's psycopg2.
        counts = {}
        for table in PG_TABLES:
            print(f"  dumping {table}...")
            dest = stage / "db" / f"{table}.jsonl"
            ssh_run(host,
                    f"cd {BRAIN_DIR} && {COMPOSE} exec -T api "
                    f"python {SELF_IN_CONTAINER} --dump-pg {table}",
                    outfile=dest)
            counts[table] = count_lines(dest)
            print(f"    {counts[table]} rows")

        # 3. memory_proposals — via the nodeos container's sqlite3.
        print("  dumping memory_proposals...")
        dest = stage / "db" / "memory_proposals.jsonl"
        ssh_run(host, f"cd {BRAIN_DIR} && {COMPOSE} exec -T nodeos python -",
                stdin=NODEOS_DUMP, outfile=dest)
        counts["memory_proposals"] = count_lines(dest)
        print(f"    {counts['memory_proposals']} rows")

        # 4. Personalized identity (Track J1: brain_persona.local.md).
        persona_remote = f"{BRAIN_DIR}/api/brain_persona.local.md"
        has_persona = ssh_run(
            host, f"test -f {persona_remote} && echo yes || echo no").strip() == "yes"
        if has_persona:
            print("  collecting persona (brain_persona.local.md)...")
            ssh_run(host, f"cat {persona_remote}",
                    outfile=stage / "persona" / "brain_persona.local.md")
        else:
            print("  no brain_persona.local.md — brain is unconfigured; "
                  "persona omitted")

        # 5. Non-secret config.
        ident_remote = f"{BRAIN_DIR}/api/brain_identity.yaml"
        if ssh_run(host, f"test -f {ident_remote} && echo yes || echo no").strip() == "yes":
            ssh_run(host, f"cat {ident_remote}",
                    outfile=stage / "config" / "brain_identity.yaml")

        # 6. Manifest — read first so import can decide load-direct vs re-embed.
        manifest = {
            "format": ARCHIVE_FORMAT,
            "exported_at": datetime.datetime.now(datetime.timezone.utc)
                                   .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_host": host,
            "source_brain_id": probe.get("brain_id") or "",
            "brain_version": probe.get("brain_version"),
            "embedding": {"model": probe.get("embedding_model"), "dimension": dim},
            "contents": {"persona": has_persona, "tables": counts},
            "excludes_secrets": True,
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        # 7. Pack.
        out_path = out_path.expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(out_path, "w:gz") as tar:
            for item in sorted(stage.iterdir()):
                tar.add(item, arcname=item.name)

    size_mb = out_path.stat().st_size / 1e6
    print(f"\nexport_brain: done -> {out_path}  ({size_mb:.2f} MB)")
    print(f"  rows: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    print(f"  persona: {'included' if has_persona else 'none'}  |  "
          f"embedding dim: {dim}  |  secrets: excluded")
    print(f"  restore with:  scripts/import_brain.py <target_host> {out_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Track G1 — whole-brain export.")
    ap.add_argument("host", nargs="?", help="brain ssh host (orchestrator mode)")
    ap.add_argument("--out", help="archive output path")
    # worker-mode flags — used only when re-invoked inside a container.
    ap.add_argument("--dump-pg", metavar="TABLE", help=argparse.SUPPRESS)
    ap.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.dump_pg:
        return worker_dump_pg(args.dump_pg)
    if args.probe:
        return worker_probe()

    if not args.host:
        ap.error("the brain ssh host is required")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out) if args.out else Path.cwd() / f"brain-export-{args.host}-{stamp}.tar.gz"
    try:
        return orchestrate(args.host, out)
    except Exception as e:  # noqa: BLE001 — surface a clean one-line failure
        print(f"export_brain: FAILED — {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
