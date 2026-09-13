"""
api/export.py — one-command export of a brain (unreleased 0.10.0, 2026-09-13).

The sovereignty primitive, runnable ON the brain with no laptop script and no
SSH: one command (or one button in Settings) produces a single .tar.gz that
holds everything the owner accumulated and that is not in git:

  manifest.json                    format, brain id + version, embedding model
                                   and dimension, row counts, what is included
  db/document_embeddings.jsonl     the memory: every chunk with its embedding
  db/chat_sessions.jsonl           chat sessions
  db/chat_messages.jsonl           chat messages
  persona/brain_persona.local.md   the personalized identity (if configured)
  md/*.md                          every governance .md in the runtime volume
  config/brain_identity.yaml       non-secret identity config
  apps/installed.json              the installed-apps registry (id, repo, commit
                                   sha, permissions, packs record). The app
                                   clones themselves are re-fetched on restore
                                   from repo + commit_sha; they are not bundled.
  peers/peers.json                 introduced federation peers

Layout and manifest are a superset of the brainfoundry-brain-export/v1 format
that scripts/export_brain.py produces, so scripts/import_brain.py restores the
db/ and persona/ parts unchanged. Restore of the rest is documented in
docs/EXPORT.md.

DELIBERATELY EXCLUDED, so the archive is safe to hand to anyone:
  .env, API keys, the settings sidecar (settings.json holds operator secrets,
  encrypted with BRAIN_IDENTITY_SECRET), NodeOS secrets, the brain private key,
  audit logs (tool_audit, federation_audit, autonomy) and quarantine state.
  NodeOS memory_proposals live in the nodeos container's sqlite and are not
  reachable from here; scripts/export_brain.py still collects them over SSH.

Three entry points, one function:
  - POST /export            build an archive under /app/runtime/exports/
  - GET  /export/{name}     download it;  GET /export lists;  DELETE removes
  - python -m api.export    same build from a shell inside the api container
    (scripts/export.sh wraps it:  docker compose exec -T api python -m api.export --stdout > brain.tar.gz)
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Callable, Iterable, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

ARCHIVE_FORMAT = "brainfoundry-brain-export/v1"
RUNTIME_DIR = Path(os.getenv("BRAIN_RUNTIME_DIR") or "/app/runtime")
EXPORTS_DIR = RUNTIME_DIR / "exports"
APP_DIR = Path(__file__).parent
BRAIN_APPS_DIR = Path(os.environ.get("BRAIN_APPS_DIR", "/app/brain-apps"))
PEERS_PATH = Path("data/peers.json")
PG_TABLES = ("document_embeddings", "chat_sessions", "chat_messages")

# Same SELECTs as scripts/export_brain.py worker_dump_pg, so the two archives
# are row-for-row compatible.
_SELECTS = {
    "document_embeddings":
        ("SELECT document_name, content, metadata, embedding::text, created_at::text "
         "FROM document_embeddings ORDER BY id",
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

# Files that must NEVER land in an archive, whatever directory is walked.
_NEVER = {"settings.json", ".env", "tool_audit.jsonl", "federation_audit.jsonl",
          "autonomy.jsonl", "quarantine_audit.jsonl", "tool_approvals.json"}
_NAME_RE = re.compile(r"^brain-export-[A-Za-z0-9._-]+\.tar\.gz$")


# ── data sources (injectable so tests need no database) ─────────────────────

def _pg_rows(table: str) -> Iterable[dict]:
    """Yield one dict per row of `table` from DATABASE_URL."""
    import psycopg2
    sql, cols = _SELECTS[table]
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        cur = conn.cursor()
        cur.execute(sql)
        for row in cur:
            yield dict(zip(cols, row))
    finally:
        conn.close()


def _pg_probe() -> dict:
    """Embedding dimension of the vector column (atttypmod of vector(N) is N)."""
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        cur = conn.cursor()
        cur.execute("SELECT atttypmod FROM pg_attribute "
                    "WHERE attrelid='document_embeddings'::regclass AND attname='embedding'")
        row = cur.fetchone()
        return {"embedding_dim": row[0] if row else None}
    finally:
        conn.close()


def _brain_version() -> str:
    for p in (Path("/app/VERSION"), APP_DIR.parent / "VERSION"):
        try:
            return p.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return "unknown"


def _persona_path() -> Optional[Path]:
    for p in (RUNTIME_DIR / "brain_persona.local.md", APP_DIR / "brain_persona.local.md"):
        if p.is_file():
            return p
    return None


# ── the build ────────────────────────────────────────────────────────────────

def build_export(out_dir: Path, *, rows: Optional[Callable[[str], Iterable[dict]]] = None,
                 probe: Optional[Callable[[], dict]] = None, name: Optional[str] = None) -> Path:
    """Build one archive under out_dir and return its path. Pure function of
    its data sources; the router and the CLI both call it. Data sources
    resolve at call time so tests can stub the module attributes."""
    rows = rows or _pg_rows
    probe = probe or _pg_probe
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    brain_id = os.environ.get("BRAIN_ID", "") or "brain"
    safe_id = re.sub(r"[^a-z0-9._-]", "-", brain_id.lower()) or "brain"
    out_path = out_dir / (name or f"brain-export-{safe_id}-{stamp}.tar.gz")
    if not _NAME_RE.match(out_path.name):
        raise ValueError(f"bad archive name: {out_path.name}")

    with tempfile.TemporaryDirectory(prefix="brain-export-") as tmp:
        stage = Path(tmp)
        for d in ("db", "persona", "md", "config", "apps", "peers"):
            (stage / d).mkdir()

        # 1. memory + chats
        counts = {}
        for table in PG_TABLES:
            n = 0
            with (stage / "db" / f"{table}.jsonl").open("w", encoding="utf-8") as fh:
                for r in rows(table):
                    fh.write(json.dumps(r, default=str) + "\n")
                    n += 1
            counts[table] = n

        # 2. persona + every governance .md in the runtime volume
        persona = _persona_path()
        has_persona = persona is not None
        if persona is not None:
            shutil.copyfile(persona, stage / "persona" / "brain_persona.local.md")
        md_files = []
        if RUNTIME_DIR.is_dir():
            for p in sorted(RUNTIME_DIR.glob("*.md")):
                if p.name in _NEVER:
                    continue
                shutil.copyfile(p, stage / "md" / p.name)
                md_files.append(p.name)

        # 3. non-secret identity config
        ident = APP_DIR / "brain_identity.yaml"
        if ident.is_file():
            shutil.copyfile(ident, stage / "config" / "brain_identity.yaml")

        # 4. installed apps registry (not the clones; repo + commit_sha suffice)
        installed = BRAIN_APPS_DIR / "installed.json"
        apps_count = 0
        if installed.is_file():
            shutil.copyfile(installed, stage / "apps" / "installed.json")
            try:
                apps_count = len(json.loads(installed.read_text()).get("apps", []))
            except Exception:
                apps_count = -1

        # 5. federation peers
        has_peers = PEERS_PATH.is_file()
        if has_peers:
            shutil.copyfile(PEERS_PATH, stage / "peers" / "peers.json")

        # 6. manifest (v1-compatible fields first)
        try:
            dim = probe().get("embedding_dim")
        except Exception:
            dim = None
        manifest = {
            "format": ARCHIVE_FORMAT,
            "exported_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_host": "on-box",
            "source_brain_id": brain_id,
            "brain_version": _brain_version(),
            "embedding": {"model": os.environ.get("EMBEDDING_MODEL_NAME", "BAAI/bge-large-en-v1.5"),
                          "dimension": dim},
            "contents": {"persona": has_persona, "tables": counts, "md": md_files,
                         "apps": apps_count, "peers": has_peers},
            "excludes_secrets": True,
            "excludes": ["env", "settings.json", "private keys", "audit logs",
                         "memory_proposals (nodeos sqlite; use scripts/export_brain.py)"],
            "built_by": "api/export.py",
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        # 7. pack, then guard: nothing forbidden may be inside.
        with tarfile.open(out_path, "w:gz") as tar:
            for item in sorted(stage.iterdir()):
                tar.add(item, arcname=item.name)
    with tarfile.open(out_path, "r:gz") as tar:
        bad = [m.name for m in tar.getmembers() if Path(m.name).name in _NEVER]
    if bad:
        out_path.unlink(missing_ok=True)
        raise RuntimeError(f"export refused: forbidden files in archive: {bad}")
    return out_path


def list_exports(out_dir: Optional[Path] = None) -> list[dict]:
    out_dir = Path(out_dir or EXPORTS_DIR)
    if not out_dir.is_dir():
        return []
    items = []
    for p in sorted(out_dir.glob("brain-export-*.tar.gz"), reverse=True):
        st = p.stat()
        items.append({"name": p.name, "size": st.st_size,
                      "created_at": datetime.datetime.fromtimestamp(st.st_mtime, datetime.timezone.utc)
                      .strftime("%Y-%m-%dT%H:%M:%SZ")})
    return items


def _manifest_of(path: Path) -> dict:
    try:
        with tarfile.open(path, "r:gz") as tar:
            f = tar.extractfile("manifest.json")
            return json.loads(f.read().decode("utf-8")) if f else {}
    except Exception:
        return {}


# ── router (mounted by api.main with the operator api_key dependency) ───────

router = APIRouter(prefix="/export", tags=["export"])


@router.get("")
def export_list() -> dict:
    return {"exports": list_exports(), "dir": str(EXPORTS_DIR)}


@router.post("")
def export_build() -> dict:
    try:
        path = build_export(EXPORTS_DIR)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "export_failed", "message": str(e)[:400]})
    m = _manifest_of(path)
    return {"name": path.name, "size": path.stat().st_size, "download": f"/export/{path.name}",
            "contents": m.get("contents", {}), "excludes_secrets": True}


def _resolve(name: str) -> Path:
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail={"error": "bad_name"})
    p = EXPORTS_DIR / name
    if not p.is_file():
        raise HTTPException(status_code=404, detail={"error": "export_not_found", "name": name})
    return p


@router.get("/{name}")
def export_download(name: str):
    p = _resolve(name)
    return FileResponse(str(p), media_type="application/gzip", filename=p.name)


@router.delete("/{name}")
def export_delete(name: str) -> dict:
    p = _resolve(name)
    p.unlink()
    return {"name": name, "deleted": True}


# ── CLI: python -m api.export [--out DIR | --stdout] ────────────────────────

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Export this brain to one .tar.gz (no secrets).")
    ap.add_argument("--out", default=str(EXPORTS_DIR), help="directory for the archive")
    ap.add_argument("--stdout", action="store_true", help="write the archive bytes to stdout instead")
    args = ap.parse_args(argv)
    if args.stdout:
        with tempfile.TemporaryDirectory(prefix="brain-export-cli-") as tmp:
            path = build_export(Path(tmp))
            with path.open("rb") as fh:
                shutil.copyfileobj(fh, sys.stdout.buffer)
            sys.stderr.write(f"export: {path.name} ({path.stat().st_size} bytes) -> stdout\n")
        return 0
    path = build_export(Path(args.out))
    m = _manifest_of(path)
    print(f"export: {path} ({path.stat().st_size} bytes)")
    print(f"  rows: {m.get('contents', {}).get('tables')}  persona: {m.get('contents', {}).get('persona')}"
          f"  apps: {m.get('contents', {}).get('apps')}  secrets: excluded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
