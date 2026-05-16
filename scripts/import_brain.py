#!/usr/bin/env python3
"""scripts/import_brain.py — Track G2: import / restore an exported brain.

Restores a .tar.gz produced by scripts/export_brain.py (G1) onto a brain.

DESTRUCTIVE. Restore REPLACES the target brain's state — knowledge corpus,
chat sessions, memory proposals, and persona are truncated and reloaded from
the archive. It is NOT a merge. Merge-into-existing is a separate future mode.
Explicit confirmation is required before anything is written.

EMBEDDING DIMENSION HANDLING
  The manifest is read first. If the archive's embedding dimension matches the
  target brain -> embeddings are loaded directly. If it differs -> the corpus
  is loaded as content + metadata with NULL embeddings, then re-embedded with
  the TARGET brain's own model via scripts/reembed_null_embeddings.py.
  (scripts/migrate_embedding_dim.sh is the companion tool if a target's own
  schema/model are themselves mismatched — fix that first, then import.)

SECRETS
  The archive carries none. The receiving brain keeps its own .env, API keys,
  and NodeOS secrets — import never reads or writes them.

USAGE  (run on your laptop)
  scripts/import_brain.py <ssh_host> <archive.tar.gz> [--yes]
    <ssh_host>  target brain host
    --yes       skip the interactive destructive-restore confirmation

  SSH as `hbar` with $HOME/.ssh/id_ed25519_brainfoundry_automation
  (override with $BRAINFOUNDRY_KEY).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

BRAIN_DIR = "/home/hbar/brain"
COMPOSE = f"docker compose -f {BRAIN_DIR}/docker-compose.yml"
SELF_IN_CONTAINER = f"{BRAIN_DIR}/scripts/import_brain.py"
ARCHIVE_FORMAT_PREFIX = "brainfoundry-brain-export/"
PG_TABLES = ("document_embeddings", "chat_sessions", "chat_messages")

# Truncate + reload memory_proposals in the NodeOS sqlite db. Piped to
# `python -` inside the nodeos container; reads the jsonl copied in beforehand.
NODEOS_LOAD = r'''
import json, sqlite3, sys
COLS = ("proposal_id","permit_id","memory_type","content","source_refs",
        "status","created_at","decided_at","decided_by","decision_note")
rows = [json.loads(x) for x in open("/tmp/_brainimport_mp.jsonl") if x.strip()]
con = sqlite3.connect("/data/nodeos.db")
try:
    con.execute("DELETE FROM memory_proposals")
    con.executemany(
        f"INSERT INTO memory_proposals ({','.join(COLS)}) "
        f"VALUES ({','.join('?' * len(COLS))})",
        [[r.get(c) for c in COLS] for r in rows])
    con.commit()
    sys.stderr.write(f"[worker] loaded {len(rows)} memory_proposals\n")
except sqlite3.OperationalError as e:
    sys.stderr.write(f"[worker] memory_proposals skipped: {e}\n")
'''


# ============================================================================
# Worker mode — runs INSIDE the api container.
# ============================================================================
def _connect():
    import psycopg2
    return psycopg2.connect(os.environ["DATABASE_URL"])


def worker_probe() -> int:
    """Print the target brain's embedding dimension + current row counts."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT atttypmod FROM pg_attribute "
                    "WHERE attrelid='document_embeddings'::regclass AND attname='embedding'")
        row = cur.fetchone()
        dim = row[0] if row else None
        counts = {}
        for table in PG_TABLES:
            cur.execute(f"SELECT count(*) FROM {table}")
            counts[table] = cur.fetchone()[0]
        print(json.dumps({"embedding_dim": dim, "counts": counts}))
        return 0
    finally:
        conn.close()


def worker_prepare() -> int:
    """Truncate the postgres tables a restore replaces."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("TRUNCATE document_embeddings, chat_messages, chat_sessions "
                    "RESTART IDENTITY")
        conn.commit()
        sys.stderr.write("[worker] truncated document_embeddings, "
                         "chat_messages, chat_sessions\n")
        return 0
    finally:
        conn.close()


def worker_load_pg(table: str, embedding_mode: str) -> int:
    """Load one postgres table from JSON-lines on stdin into an (already
    truncated) table. Commits in batches."""
    inserts = {
        "chat_sessions": (
            "INSERT INTO chat_sessions (session_id, model_name, title, created_at) "
            "VALUES (%s::uuid, %s, %s, %s::timestamp)",
            lambda r: (r["session_id"], r["model_name"], r.get("title"), r.get("created_at"))),
        "chat_messages": (
            "INSERT INTO chat_messages (session_id, role, content, created_at) "
            "VALUES (%s::uuid, %s, %s, %s::timestamp)",
            lambda r: (r["session_id"], r["role"], r["content"], r.get("created_at"))),
    }
    if table == "document_embeddings":
        if embedding_mode == "direct":
            sql = ("INSERT INTO document_embeddings "
                   "(document_name, content, metadata, embedding, created_at) "
                   "VALUES (%s, %s, %s::jsonb, %s::vector, %s::timestamp)")
            params = lambda r: (
                r["document_name"], r["content"],
                json.dumps(r["metadata"]) if r.get("metadata") is not None else None,
                r.get("embedding"), r.get("created_at"))
        else:  # null — load content only; embeddings get re-embedded afterwards
            sql = ("INSERT INTO document_embeddings "
                   "(document_name, content, metadata, created_at) "
                   "VALUES (%s, %s, %s::jsonb, %s::timestamp)")
            params = lambda r: (
                r["document_name"], r["content"],
                json.dumps(r["metadata"]) if r.get("metadata") is not None else None,
                r.get("created_at"))
    elif table in inserts:
        sql, params = inserts[table]
    else:
        sys.stderr.write(f"unknown table: {table}\n")
        return 2

    conn = _connect()
    try:
        cur = conn.cursor()
        n = 0
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            cur.execute(sql, params(json.loads(line)))
            n += 1
            if n % 500 == 0:
                conn.commit()
        conn.commit()
        sys.stderr.write(f"[worker] loaded {n} rows into {table} "
                         f"(mode={embedding_mode})\n")
        return 0
    finally:
        conn.close()


# ============================================================================
# Orchestrator mode — runs on the laptop.
# ============================================================================
def ssh_base(host: str) -> list:
    key = os.environ.get("BRAINFOUNDRY_KEY",
                         str(Path.home() / ".ssh" / "id_ed25519_brainfoundry_automation"))
    return ["ssh", "-i", key, "-o", "StrictHostKeyChecking=accept-new", f"hbar@{host}"]


def scp_base() -> list:
    key = os.environ.get("BRAINFOUNDRY_KEY",
                         str(Path.home() / ".ssh" / "id_ed25519_brainfoundry_automation"))
    return ["scp", "-i", key, "-o", "StrictHostKeyChecking=accept-new"]


def ssh_run(host: str, remote_cmd: str, stdin_bytes: bytes | None = None,
            stdin_file: Path | None = None) -> str:
    """Run a command on the brain host; return stdout. Raises on failure.

    When no stdin data is supplied, stdin is /dev/null — otherwise the ssh
    subprocess would inherit and consume this process's own stdin (which would
    eat the destructive-restore confirmation typed at the prompt).
    """
    cmd = ssh_base(host) + [remote_cmd]
    if stdin_file is not None:
        with open(stdin_file, "rb") as fh:
            proc = subprocess.run(cmd, stdin=fh, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
    elif stdin_bytes is not None:
        proc = subprocess.run(cmd, input=stdin_bytes, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
    else:
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(f"remote command failed ({proc.returncode}): "
                           f"{proc.stderr.decode(errors='replace').strip()}")
    # worker progress is on stderr — surface it.
    err = proc.stderr.decode(errors="replace").strip()
    if err:
        for ln in err.splitlines():
            if ln.startswith("[worker]"):
                print(f"    {ln}")
    return proc.stdout.decode(errors="replace")


def restore(host: str, archive: Path, assume_yes: bool) -> int:
    archive = archive.expanduser().resolve()
    if not archive.is_file():
        raise RuntimeError(f"archive not found: {archive}")

    with tempfile.TemporaryDirectory(prefix="brain-import-") as tmp:
        stage = Path(tmp)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(stage)

        manifest_path = stage / "manifest.json"
        if not manifest_path.is_file():
            raise RuntimeError("archive has no manifest.json — not a brain export")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not str(manifest.get("format", "")).startswith(ARCHIVE_FORMAT_PREFIX):
            raise RuntimeError(f"unrecognized archive format: {manifest.get('format')}")

        src_dim = (manifest.get("embedding") or {}).get("dimension")
        src_counts = (manifest.get("contents") or {}).get("tables", {})
        has_persona = (manifest.get("contents") or {}).get("persona", False)
        print("import_brain: archive manifest")
        print(f"  source brain : {manifest.get('source_brain_id') or '?'} "
              f"(v{manifest.get('brain_version')}, exported {manifest.get('exported_at')})")
        print(f"  embedding    : {(manifest.get('embedding') or {}).get('model')} "
              f"(dim {src_dim})")
        print(f"  rows         : " + ", ".join(f"{k}={v}" for k, v in src_counts.items()))
        print(f"  persona      : {'included' if has_persona else 'none'}")

        # Preflight + probe the target.
        ssh_run(host, f"test -d {BRAIN_DIR} && test -f {BRAIN_DIR}/docker-compose.yml")
        probe = json.loads(ssh_run(
            host, f"cd {BRAIN_DIR} && {COMPOSE} exec -T api "
                  f"python {SELF_IN_CONTAINER} --probe"))
        tgt_dim = probe.get("embedding_dim")
        tgt_counts = probe.get("counts", {})
        mode = "direct" if src_dim == tgt_dim else "null"
        print(f"\nimport_brain: target = {host}")
        print(f"  target embedding dim : {tgt_dim}")
        print(f"  target current rows  : "
              + ", ".join(f"{k}={v}" for k, v in tgt_counts.items()))
        if mode == "direct":
            print(f"  dimension match -> embeddings load directly")
        else:
            print(f"  dimension MISMATCH ({src_dim} -> {tgt_dim}) -> corpus loads "
                  f"with NULL embeddings, then re-embeds with the target's model")

        # Destructive confirmation.
        print("\n*** DESTRUCTIVE RESTORE ***")
        print(f"This REPLACES {host}'s knowledge corpus, chat sessions, and "
              f"memory proposals")
        print(f"with the archive's contents. The current data above is "
              f"discarded and cannot be recovered.")
        if not assume_yes:
            answer = input(f"Type the target host ({host}) to proceed, "
                           f"anything else to abort: ").strip()
            if answer != host:
                print("import_brain: aborted — no changes made.")
                return 1
        else:
            print("--yes given — proceeding without prompt.")

        # 1. Truncate the postgres tables.
        print("\n  truncating target tables...")
        ssh_run(host, f"cd {BRAIN_DIR} && {COMPOSE} exec -T api "
                      f"python {SELF_IN_CONTAINER} --prepare")

        # 2. Load postgres tables — sessions before messages (FK order).
        for table in ("chat_sessions", "chat_messages", "document_embeddings"):
            src = stage / "db" / f"{table}.jsonl"
            if not src.is_file():
                print(f"  {table}: not in archive — skipped")
                continue
            print(f"  loading {table}...")
            extra = f" --embedding-mode {mode}" if table == "document_embeddings" else ""
            ssh_run(host,
                    f"cd {BRAIN_DIR} && {COMPOSE} exec -T api "
                    f"python {SELF_IN_CONTAINER} --load-pg {table}{extra}",
                    stdin_file=src)

        # 3. memory_proposals -> NodeOS sqlite. The repo is not bind-mounted
        #    into the nodeos container, so copy the jsonl in (scp to host, then
        #    `docker compose cp` into the container) and load it with a snippet.
        mp = stage / "db" / "memory_proposals.jsonl"
        if mp.is_file():
            print("  loading memory_proposals...")
            subprocess.run(
                scp_base() + [str(mp), f"hbar@{host}:/tmp/_brainimport_mp.jsonl"],
                check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            ssh_run(host, f"cd {BRAIN_DIR} && {COMPOSE} cp "
                          f"/tmp/_brainimport_mp.jsonl nodeos:/tmp/_brainimport_mp.jsonl")
            ssh_run(host, f"cd {BRAIN_DIR} && {COMPOSE} exec -T nodeos python -",
                    stdin_bytes=NODEOS_LOAD.encode())
            ssh_run(host, "rm -f /tmp/_brainimport_mp.jsonl")
            ssh_run(host, f"cd {BRAIN_DIR} && {COMPOSE} exec -T nodeos "
                          f"rm -f /tmp/_brainimport_mp.jsonl")

        # 4. Persona (Track J1 identity). Only overwrite if the archive has one.
        persona_file = stage / "persona" / "brain_persona.local.md"
        if persona_file.is_file():
            print("  restoring persona (brain_persona.local.md)...")
            data = persona_file.read_bytes()
            ssh_run(host, f"cat > {BRAIN_DIR}/api/brain_persona.local.md",
                    stdin_bytes=data)
            ssh_run(host, f"cd {BRAIN_DIR} && {COMPOSE} exec -T api "
                          f"sh -c 'cat > /app/api/brain_persona.local.md'",
                    stdin_bytes=data)
        elif has_persona:
            print("  WARNING: manifest says persona included but file missing — skipped")
        else:
            print("  archive has no persona — target's existing persona left as-is")

        # 5. Re-embed if the dimensions differed.
        if mode == "null":
            print("\n  re-embedding the corpus with the target's model "
                  "(scripts/reembed_null_embeddings.py)...")
            reembed = Path(__file__).resolve().parent / "reembed_null_embeddings.py"
            subprocess.run([sys.executable, str(reembed), host], check=True,
                           stdin=subprocess.DEVNULL)

        # 6. Restart the api so the restored persona reloads.
        print("  restarting api container...")
        ssh_run(host, f"cd {BRAIN_DIR} && {COMPOSE} restart api")

    print(f"\nimport_brain: done — {host} restored from {archive.name}")
    print(f"  verify:  ssh hbar@{host} \"cd {BRAIN_DIR} && {COMPOSE} "
          f"exec -T api python {SELF_IN_CONTAINER} --probe\"")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Track G2 — import / restore a brain.")
    ap.add_argument("host", nargs="?", help="target brain ssh host")
    ap.add_argument("archive", nargs="?", help="brain export .tar.gz")
    ap.add_argument("--yes", action="store_true",
                    help="skip the destructive-restore confirmation prompt")
    # worker-mode flags — used only when re-invoked inside a container.
    ap.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--prepare", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--load-pg", metavar="TABLE", help=argparse.SUPPRESS)
    ap.add_argument("--embedding-mode", choices=("direct", "null"), default="direct",
                    help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.probe:
        return worker_probe()
    if args.prepare:
        return worker_prepare()
    if args.load_pg:
        return worker_load_pg(args.load_pg, args.embedding_mode)

    if not args.host or not args.archive:
        ap.error("both <ssh_host> and <archive.tar.gz> are required")
    try:
        return restore(args.host, Path(args.archive), args.yes)
    except Exception as e:  # noqa: BLE001
        print(f"import_brain: FAILED — {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
