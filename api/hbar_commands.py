"""
api/hbar_commands.py — Brain custom command handlers

Called by /v1/brain/command for commands specific to the brain layer:
remember, recall, forget, memories, context.*, peers.*, model.*, audit, policy, ingest, think
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import ipaddress
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")


_CLOUD_METADATA_HOSTNAMES = {
    "metadata.google.internal",
    "metadata.goog",
    "169.254.169.254",
    "fd00:ec2::254",
}

def _validate_peer_url(url: str) -> None:
    """Reject non-http(s) URLs and RFC1918/link-local/metadata addresses to prevent SSRF."""
    import socket as _socket
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ValueError("peer endpoint must use http or https")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("peer endpoint has no hostname")
    if host.lower() in _CLOUD_METADATA_HOSTNAMES:
        raise ValueError(f"peer endpoint host {host!r} is a reserved metadata address")
    # Resolve hostname to IP and check for private/internal ranges
    try:
        resolved_ip = _socket.gethostbyname(host)
        addr = ipaddress.ip_address(resolved_ip)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise ValueError(f"peer endpoint resolves to a private/internal address: {resolved_ip}")
    except (OSError, ValueError) as e:
        if "private" in str(e) or "internal" in str(e) or "loopback" in str(e):
            raise ValueError(str(e)) from None
        # DNS resolution failure — let the HTTP client handle it

# ── simple in-process context store (resets on restart — intentional for a template) ──
_context: Dict[str, Any] = {}

# ── peers store: persisted to data/peers.json ─────────────────────────────────
_PEERS_PATH = Path("data/peers.json")

def _load_peers() -> list:
    try:
        return json.loads(_PEERS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

def _save_peers(peers: list) -> None:
    _PEERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PEERS_PATH.write_text(json.dumps(peers, indent=2), encoding="utf-8")

# ── audit log path ─────────────────────────────────────────────────────────────
_AUDIT_PATH = Path("brainfoundry/audit.jsonl")

# ── DB helper ──────────────────────────────────────────────────────────────────
def _db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg2.connect(DATABASE_URL)


async def handle_hbar_command(
    *,
    command: str,
    payload: dict,
    client_id: str,
    ollama_url: str = "",
    model: str = "",
) -> dict:
    """
    Dispatch brain custom commands. Returns a result dict.
    Raises ValueError for bad input; RuntimeError for infrastructure errors.
    """
    cmd = command.strip().lower()

    # ── memory ────────────────────────────────────────────────────────────────
    if cmd == "remember":
        content = (payload.get("content") or "").strip()
        if not content:
            raise ValueError("payload.content is required for remember")
        tags = payload.get("tags") or []
        mem_id = str(uuid.uuid4())
        doc_name = f"memory/{mem_id}"
        meta = {"tags": tags, "client_id": client_id, "source": "remember",
                "created_at": datetime.now(timezone.utc).isoformat()}
        conn = _db()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO document_embeddings (document_name, content, metadata) VALUES (%s, %s, %s)",
                (doc_name, content, json.dumps(meta))
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()
        return {"remembered": True, "id": mem_id, "doc_name": doc_name}

    if cmd == "recall":
        query = (payload.get("query") or "").strip()
        if not query:
            raise ValueError("payload.query is required for recall")
        limit = min(int(payload.get("limit", 5)), 20)
        # Escape ILIKE wildcards so user input can't expand the search unintentionally
        safe_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conn = _db()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT document_name, content, metadata, created_at
                FROM document_embeddings
                WHERE document_name LIKE 'memory/%%'
                  AND content ILIKE %s ESCAPE '\\'
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (f"%{safe_query}%", limit)
            )
            rows = cur.fetchall()
            cur.close()
        finally:
            conn.close()
        return {
            "results": [
                {
                    "id": r[0].replace("memory/", ""),
                    "content": r[1],
                    "metadata": r[2] or {},
                    "created_at": r[3].isoformat() if r[3] else None,
                }
                for r in rows
            ],
            "count": len(rows),
            "query": query,
        }

    if cmd == "forget":
        mem_id = (payload.get("id") or "").strip()
        if not mem_id:
            raise ValueError("payload.id is required for forget")
        doc_name = f"memory/{mem_id}"
        conn = _db()
        try:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM document_embeddings WHERE document_name = %s",
                (doc_name,)
            )
            deleted = cur.rowcount
            conn.commit()
            cur.close()
        finally:
            conn.close()
        return {"forgotten": deleted > 0, "id": mem_id}

    if cmd == "memories":
        limit = min(int(payload.get("limit", 20)), 100)
        tag_filter = payload.get("tag")
        conn = _db()
        try:
            cur = conn.cursor()
            if tag_filter:
                safe_tag = tag_filter.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                cur.execute(
                    """
                    SELECT document_name, content, metadata, created_at
                    FROM document_embeddings
                    WHERE document_name LIKE 'memory/%%'
                      AND metadata::text ILIKE %s ESCAPE '\\'
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (f"%{safe_tag}%", limit)
                )
            else:
                cur.execute(
                    """
                    SELECT document_name, content, metadata, created_at
                    FROM document_embeddings
                    WHERE document_name LIKE 'memory/%%'
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (limit,)
                )
            rows = cur.fetchall()
            cur.close()
        finally:
            conn.close()
        return {
            "memories": [
                {
                    "id": r[0].replace("memory/", ""),
                    "content": r[1],
                    "metadata": r[2] or {},
                    "created_at": r[3].isoformat() if r[3] else None,
                }
                for r in rows
            ],
            "count": len(rows),
        }

    # ── context ───────────────────────────────────────────────────────────────
    if cmd == "context.show":
        return {"context": dict(_context)}

    if cmd == "context.set":
        key = (payload.get("key") or "").strip()
        value = payload.get("value")
        if value is None:
            raise ValueError("payload.value is required for context.set")
        if key:
            _context[key] = value
        elif isinstance(value, dict):
            _context.update(value)
        else:
            raise ValueError("payload.key is required when payload.value is not a dict")
        return {"context": dict(_context), "set": True}

    if cmd == "context.clear":
        key = (payload.get("key") or "").strip()
        if key:
            _context.pop(key, None)
            return {"cleared": key, "context": dict(_context)}
        _context.clear()
        return {"cleared": "all", "context": {}}

    # ── peers ─────────────────────────────────────────────────────────────────
    if cmd == "peers":
        return {"peers": _load_peers()}

    if cmd == "peers.introduce":
        endpoint = (payload.get("endpoint") or "").strip()
        if not endpoint:
            raise ValueError("payload.endpoint is required for peers.introduce")
        _validate_peer_url(endpoint)
        import httpx
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(f"{endpoint.rstrip('/')}/identity")
            resp.raise_for_status()
            identity = resp.json()
        peers = _load_peers()
        brain_id = identity.get("brain_id", endpoint)
        existing_ids = {p["brain_id"] for p in peers}
        if brain_id not in existing_ids:
            peers.append({"brain_id": brain_id, "endpoint": endpoint,
                          "introduced_at": datetime.now(timezone.utc).isoformat()})
            _save_peers(peers)
        return {"introduced": True, "peer": brain_id, "identity": identity}

    if cmd == "peers.ping":
        endpoint = (payload.get("endpoint") or "").strip()
        peer_id = (payload.get("id") or "").strip()
        if not endpoint and peer_id:
            peers = _load_peers()
            match = next((p for p in peers if p["brain_id"] == peer_id), None)
            if match:
                endpoint = match["endpoint"]
        if not endpoint:
            raise ValueError("payload.endpoint or payload.id is required for peers.ping")
        _validate_peer_url(endpoint)
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5) as http:
                resp = await http.get(f"{endpoint.rstrip('/')}/health")
            return {"ok": resp.status_code == 200, "status_code": resp.status_code, "endpoint": endpoint}
        except Exception as e:
            return {"ok": False, "error": str(e), "endpoint": endpoint}

    if cmd == "peers.remove":
        peer_id = (payload.get("id") or "").strip()
        if not peer_id:
            raise ValueError("payload.id is required for peers.remove")
        peers = _load_peers()
        before = len(peers)
        peers = [p for p in peers if p["brain_id"] != peer_id]
        _save_peers(peers)
        return {"removed": len(peers) < before, "id": peer_id}

    if cmd == "introduce":
        brain_id = os.getenv("BRAIN_ID", "brainfoundry-node")
        public_key = os.getenv("BRAIN_PUBLIC_KEY", "")
        return {
            "brain_id": brain_id,
            "display_name": os.getenv("BRAIN_NAME", brain_id),
            "domain": "authority",
            "public_key": public_key,
            "protocol": "brainfoundry/v1",
        }

    # ── model ─────────────────────────────────────────────────────────────────
    if cmd == "model":
        active = os.getenv("OLLAMA_MODEL") or os.getenv("DEFAULT_MODEL") or model or "llama3.2:3b"
        return {"active_model": active}

    if cmd == "model.list":
        from api import providers as _providers
        return {"models": _providers.get_available_models()}

    if cmd == "model.use":
        requested = (payload.get("model") or "").strip()
        if not requested:
            raise ValueError("payload.model is required for model.use")
        # In-process update only — restart container to make permanent.
        os.environ["OLLAMA_MODEL"] = requested
        os.environ["DEFAULT_MODEL"] = requested
        return {"active_model": requested, "note": "in-process only — restart container to make permanent"}

    # ── audit ─────────────────────────────────────────────────────────────────
    if cmd == "audit":
        limit = min(int(payload.get("limit", 50)), 500)
        entries = []
        if _AUDIT_PATH.exists():
            lines = _AUDIT_PATH.read_text(encoding="utf-8").splitlines()
            for line in reversed(lines[-limit:]):
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
        return {"entries": entries, "count": len(entries), "requested": limit,
                "order": "reverse_chronological"}

    if cmd == "audit.clear":
        if _AUDIT_PATH.exists():
            _AUDIT_PATH.write_text("", encoding="utf-8")
        return {"cleared": True}

    # ── policy ────────────────────────────────────────────────────────────────
    if cmd == "policy":
        policy_path = Path(__file__).parent.parent / "docs" / "constitution"
        docs = []
        if policy_path.exists():
            docs = [p.name for p in sorted(policy_path.iterdir()) if p.suffix in (".md", ".txt")]
        return {
            "governance": "brainfoundry-nous v0.6",
            "permit_required": True,
            "propose_confirm": True,
            "execution_classes": ["READ_ONLY", "STATE_MUTATION"],
            "constitution_docs": docs,
        }

    # ── ingest ────────────────────────────────────────────────────────────────
    if cmd == "ingest":
        path = (payload.get("path") or "").strip()
        if not path:
            return {
                "note": "Use POST /documents/upload to ingest files. "
                        "Supply payload.path to specify a file within the allowed input directory.",
                "endpoint": "/documents/upload",
            }
        # Sandbox: only allow paths inside /app/input_samples or /app/prepared_docs
        _allowed_roots = [Path("/app/input_samples"), Path("/app/prepared_docs")]
        target = Path(path).resolve()
        if not any(target.is_relative_to(r) for r in _allowed_roots):
            raise ValueError("ingest path must be within /app/input_samples or /app/prepared_docs")
        if not target.exists():
            raise ValueError(f"path does not exist: {path}")
        return {
            "queued": str(target),
            "note": "Server-side ingestion is not yet implemented. Use POST /documents/upload.",
        }

    # ── think ─────────────────────────────────────────────────────────────────
    if cmd == "think":
        prompt = (payload.get("prompt") or payload.get("text") or "").strip()
        if not prompt:
            raise ValueError("payload.prompt (or payload.text) is required for think")
        active_model = os.getenv("OLLAMA_MODEL") or os.getenv("DEFAULT_MODEL") or model or "llama3.2:3b"
        from api import providers as _providers
        reply = await _providers.complete(
            active_model,
            [{"role": "user", "content": prompt}],
            max_tokens=1024,
        )
        return {"reply": reply, "model": active_model, "prompt": prompt}

    # ── unknown ───────────────────────────────────────────────────────────────
    raise ValueError(f"unknown brain command: {command!r}")
