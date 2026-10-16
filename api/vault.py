"""api/vault.py — the private vault (2026-10-15).

A folder on the host that the Unix users the closed reasoners run as (`hands`,
`cc`: Claude Code, Codex) cannot read: mode 700, owned by the brain's owner,
default /home/<owner>/vault (BRAIN_VAULT_DIR). The api container (root) sees it
as a READ-ONLY bind mount at /vault (BRAIN_VAULT_MOUNT), declared in the
owner's docker-compose.override.yml by scripts/vault-setup.sh. A brain without
a vault has no mount and every function here reports "no vault".

What it does with the files: ingests new or changed ones as memory documents,
named vault/<relative path>, with
  metadata.source  = vault:<relative path>
  metadata.vault   = true
  metadata.privacy = local-only   (forced; api/privacy.py refuses to lower it)
and nothing else. It never copies a vault file anywhere (not to in/, out/, the
world checkout, the runtime volume or an export); the only things written
outside the database are the scan state (relative path, sha256, size, mtime,
chunk count per file: names, never content) in the runtime volume.

The embeddings are computed wherever the brain computes them (the box, or the
embed spoke when one is set): vault text reaches the embedder at ingest.

Pure stdlib plus injected database/chunk/embed callables, so tests need no
Postgres and no model.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from api import privacy as _privacy

TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".text", ".org", ".rst", ".tex",
                   ".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml", ".toml",
                   ".html", ".htm", ".xml", ".log", ".py", ".sh", ".js", ".ts"}
_LOCK = threading.Lock()


def mount() -> Path:
    return Path(os.getenv("BRAIN_VAULT_MOUNT", "/vault"))


def host_dir() -> str:
    """The host path, for display only (the container never writes it)."""
    return os.getenv("BRAIN_VAULT_DIR", "").strip()


def max_bytes() -> int:
    try:
        return max(1024, int(os.getenv("BRAIN_VAULT_MAX_BYTES", str(5 * 1024 * 1024))))
    except ValueError:
        return 5 * 1024 * 1024


def default_layer() -> Optional[str]:
    v = os.getenv("BRAIN_VAULT_LAYER", "").strip()
    return v or None


def scan_minutes() -> float:
    try:
        return float(os.getenv("BRAIN_VAULT_SCAN_MINUTES", "10"))
    except ValueError:
        return 10.0


def _state_path() -> Path:
    return Path(os.getenv("BRAIN_RUNTIME_DIR") or "/app/runtime") / "vault_state.json"


def load_state() -> Dict[str, Any]:
    try:
        d = json.loads(_state_path().read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("files"), dict):
            return d
    except Exception:
        pass
    return {"files": {}, "last_scan": None, "last_result": None}


def _save_state(state: Dict[str, Any]) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(p)


def available() -> bool:
    m = mount()
    return m.is_dir() and os.access(m, os.R_OK | os.X_OK)


def doc_name(rel: str) -> str:
    return _privacy.VAULT_DOC_PREFIX + rel


def list_files() -> List[Dict[str, Any]]:
    """Every ingestible file under the mount: regular files only (symlinks are
    never followed, so a link cannot pull a file from outside the vault or
    push a vault file under another name), no dotfiles or dot-directories,
    text extensions, at most max_bytes()."""
    root = mount()
    out: List[Dict[str, Any]] = []
    if not available():
        return out
    root_real = os.path.realpath(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames
                             if not d.startswith(".") and not os.path.islink(os.path.join(dirpath, d)))
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            full = os.path.join(dirpath, fn)
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            if not os.path.realpath(full).startswith(root_real + os.sep):
                continue
            if Path(fn).suffix.lower() not in TEXT_EXTENSIONS:
                continue
            st = os.stat(full)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            out.append({"rel": rel, "path": full, "size": st.st_size, "mtime": int(st.st_mtime),
                        "too_big": st.st_size > max_bytes()})
    return out


def status() -> Dict[str, Any]:
    st = load_state()
    files = list_files() if available() else []
    return {
        "mounted": available(),
        "path": host_dir() or None,
        "mount": str(mount()),
        "files": len(files),
        "ingested": len(st.get("files") or {}),
        "last_scan": st.get("last_scan"),
        "last_result": st.get("last_result"),
        "scan_minutes": scan_minutes(),
        "layer": default_layer(),
    }


def scan(*, connect: Callable[[], Any], chunker: Callable[[str], List[str]],
         embedder: Callable[[List[str]], List[List[float]]], layer: Optional[str] = None,
         prune: bool = False, force: bool = False) -> Dict[str, Any]:
    """Ingest new or changed vault files; report unchanged, skipped, missing.
    `prune` also removes the memory of files that left the vault. One scan at
    a time (a second caller gets {"busy": true})."""
    if not _LOCK.acquire(blocking=False):
        return {"ok": False, "busy": True}
    try:
        return _scan_locked(connect=connect, chunker=chunker, embedder=embedder,
                            layer=layer if layer is not None else default_layer(),
                            prune=prune, force=force)
    finally:
        _LOCK.release()


def _scan_locked(*, connect, chunker, embedder, layer, prune, force) -> Dict[str, Any]:
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not available():
        return {"ok": False, "mounted": False, "error": "no vault mounted at " + str(mount())}
    from api import memory_type as _memtype
    state = load_state()
    known: Dict[str, Any] = dict(state.get("files") or {})
    result = {"ok": True, "mounted": True, "ingested": [], "unchanged": 0,
              "skipped": [], "missing": [], "pruned": [], "errors": []}
    seen = set()
    for f in list_files():
        rel = f["rel"]
        seen.add(rel)
        if f["too_big"]:
            result["skipped"].append({"file": rel, "reason": f"larger than {max_bytes()} bytes"})
            continue
        try:
            raw = Path(f["path"]).read_bytes()
        except OSError as e:
            result["errors"].append({"file": rel, "error": type(e).__name__})
            continue
        sha = hashlib.sha256(raw).hexdigest()
        prev = known.get(rel) or {}
        if not force and prev.get("sha256") == sha and prev.get("layer") == layer:
            result["unchanged"] += 1
            continue
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            result["skipped"].append({"file": rel, "reason": "empty"})
            continue
        try:
            n = _ingest_one(connect, chunker, embedder, rel, text, sha, layer, _memtype)
        except Exception as e:
            result["errors"].append({"file": rel, "error": str(e)[:200]})
            continue
        known[rel] = {"sha256": sha, "size": f["size"], "mtime": f["mtime"], "chunks": n,
                      "layer": layer, "ingested_at": now}
        result["ingested"].append({"file": rel, "chunks": n})
    for rel in sorted(set(known) - seen):
        if prune:
            try:
                conn = connect()
                try:
                    cur = conn.cursor()
                    cur.execute("DELETE FROM document_embeddings WHERE document_name = %s "
                                "AND metadata->>'source' = %s",
                                (doc_name(rel), _privacy.VAULT_SOURCE_PREFIX + rel))
                    conn.commit()
                    cur.close()
                finally:
                    conn.close()
                known.pop(rel, None)
                result["pruned"].append(rel)
            except Exception as e:
                result["errors"].append({"file": rel, "error": str(e)[:200]})
        else:
            result["missing"].append(rel)
    state["files"] = known
    state["last_scan"] = now
    state["last_result"] = {k: (len(v) if isinstance(v, list) else v) for k, v in result.items()}
    try:
        _save_state(state)
    except Exception as e:
        result["errors"].append({"file": "(state)", "error": str(e)[:200]})
    result["last_scan"] = now
    return result


def _ingest_one(connect, chunker, embedder, rel, text, sha, layer, _memtype) -> int:
    """Replace every chunk of vault/<rel> with the file's current text."""
    chunks = [c for c in chunker(text) if c and c.strip()]
    if not chunks:
        return 0
    embeddings = embedder(chunks)
    try:
        from api import injection_scan as _scan
        risk = (_scan.scan_text(text) or {}).get("risk")
    except Exception:
        risk = None
    source = _privacy.VAULT_SOURCE_PREFIX + rel
    prov = _memtype.provenance(
        mem_type=_memtype.classify_upload(risk), source=source,
        derivation=_memtype.OBSERVED, content_hash=sha, ingested_by="owner-vault",
        injection_risk=risk)
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    name = doc_name(rel)
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM document_embeddings WHERE document_name = %s", (name,))
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            md = {**prov, "chunk_index": i, "ingested_at": now, "vault": True,
                  "source": source, "privacy": _privacy.LOCAL_ONLY}
            if layer:
                md["layer"] = layer
            cur.execute(
                "INSERT INTO document_embeddings (document_name, content, embedding, metadata) "
                "VALUES (%s, %s, %s::vector, %s)",
                (name, chunk, "[" + ",".join(map(str, emb)) + "]", json.dumps(md)))
        conn.commit()
        cur.close()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
    return len(chunks)


# ── periodic scan ───────────────────────────────────────────────────────────

_ticker: Dict[str, Any] = {"thread": None}


def start_ticker(**kw) -> bool:
    """Scan every scan_minutes() while a vault is mounted (0 = manual only).
    Called once from the api startup hook; `kw` is passed to scan()."""
    minutes = scan_minutes()
    if minutes <= 0 or _ticker["thread"] is not None or not available():
        return False

    def _loop():
        import time
        while True:
            try:
                r = scan(**kw)
                if r.get("ingested") or r.get("errors"):
                    print(f"[vault] scan: {len(r.get('ingested') or [])} ingested, "
                          f"{len(r.get('errors') or [])} error(s)", flush=True)
            except Exception as e:
                print(f"[vault] scan failed: {e}", flush=True)
            time.sleep(max(60.0, minutes * 60.0))

    t = threading.Thread(target=_loop, name="vault-scan", daemon=True)
    _ticker["thread"] = t
    t.start()
    return True
