"""
hbar_commands.py — Custom command handlers for hbar-brain
Drop into api/ directory. Import in main.py.

Usage in main.py brain_command handler:
    from api.hbar_commands import handle_hbar_command
    ...
    result = await handle_hbar_command(normalized_command, request, db, ollama_url, model)
    if result is not None:
        return ok(result)
"""

import os
import json
import time
import sqlite3
import hashlib
import datetime
import httpx
from typing import Any, Optional

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.datetime.utcnow().isoformat()

def _semantic_db_path() -> str:
    return os.getenv("SEMANTIC_DB_PATH", "/app/extensions/brain/semantic.db")

def _get_semantic_db():
    path = _semantic_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

def _ensure_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id        TEXT PRIMARY KEY,
            content   TEXT NOT NULL,
            tags      TEXT DEFAULT '',
            created   TEXT NOT NULL,
            updated   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS context_store (
            key       TEXT PRIMARY KEY,
            value     TEXT NOT NULL,
            updated   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS peers (
            id        TEXT PRIMARY KEY,
            endpoint  TEXT NOT NULL,
            pubkey    TEXT DEFAULT '',
            did       TEXT DEFAULT '',
            caps      TEXT DEFAULT '[]',
            introduced TEXT NOT NULL,
            last_seen  TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            command   TEXT NOT NULL,
            client_id TEXT,
            effect    TEXT,
            result    TEXT,
            ts        TEXT NOT NULL
        );
    """)
    conn.commit()

# ── Main dispatcher ───────────────────────────────────────────────────────────

async def handle_hbar_command(
    command: str,
    payload: dict,
    client_id: str,
    ollama_url: str,
    model: str,
) -> Optional[dict]:
    """
    Returns a result dict if command is handled, None if unknown.
    """
    conn = _get_semantic_db()
    _ensure_tables(conn)

    try:
        # ── Memory ────────────────────────────────────────────────────────────
        if command == "remember":
            return _remember(conn, payload)

        elif command == "recall":
            return await _recall(conn, payload, ollama_url, model)

        elif command == "forget":
            return _forget(conn, payload)

        elif command == "memories":
            return _list_memories(conn, payload)

        # ── Context ───────────────────────────────────────────────────────────
        elif command == "context":
            return _context(conn, payload)

        elif command == "context.set":
            return _context_set(conn, payload)

        elif command == "context.show":
            return _context_show(conn)

        elif command == "context.clear":
            return _context_clear(conn, payload)

        # ── Federation ────────────────────────────────────────────────────────
        elif command == "peers":
            return _peers_list(conn)

        elif command == "peers.introduce":
            return await _peers_introduce(conn, payload)

        elif command == "peers.ping":
            return await _peers_ping(conn, payload)

        elif command == "peers.remove":
            return _peers_remove(conn, payload)

        elif command == "introduce":
            return _self_manifest()

        # ── Model ─────────────────────────────────────────────────────────────
        elif command == "model":
            return await _model_current(ollama_url, model)

        elif command == "model.list":
            return await _model_list(ollama_url)

        elif command == "model.use":
            return _model_use(payload)

        # ── Audit / Governance ────────────────────────────────────────────────
        elif command == "audit":
            return _audit(conn, payload)

        elif command == "audit.clear":
            return _audit_clear(conn)

        elif command == "policy":
            return _policy_show()

        # ── Ingest ────────────────────────────────────────────────────────────
        elif command == "ingest":
            return _ingest_status(payload)

        # ── Think (natural language → brain) ──────────────────────────────────
        elif command == "think" or command.startswith("think "):
            return await _think(conn, payload, ollama_url, model)

        else:
            return None  # unknown — fall through to main.py handler

    finally:
        conn.close()


# ── Memory ────────────────────────────────────────────────────────────────────

def _remember(conn, payload: dict) -> dict:
    content = payload.get("content") or payload.get("text", "")
    tags    = payload.get("tags", "")
    source  = payload.get("source", "owner")
    trust   = payload.get("trust", "high") if source == "owner" else "low"
    if not content:
        return {"error": "content required"}
    uid = hashlib.sha256(f"{content}{_ts()}".encode()).hexdigest()[:16]
    now = _ts()
    conn.execute(
        "INSERT OR REPLACE INTO memories (id, content, tags, source, trust, created, updated) VALUES (?,?,?,?,?,?,?)",
        (uid, content, tags if isinstance(tags, str) else ",".join(tags), source, trust, now, now)
    )
    conn.commit()
    return {"stored": uid, "content": content, "tags": tags, "source": source, "trust": trust, "ts": now}

def _forget(conn, payload: dict) -> dict:
    uid = payload.get("id")
    if not uid:
        return {"error": "id required"}
    conn.execute("DELETE FROM memories WHERE id=?", (uid,))
    conn.commit()
    return {"forgotten": uid}

def _list_memories(conn, payload: dict) -> dict:
    tag    = payload.get("tag")
    limit  = int(payload.get("limit", 20))
    if tag:
        rows = conn.execute(
            "SELECT * FROM memories WHERE tags LIKE ? ORDER BY updated DESC LIMIT ?",
            (f"%{tag}%", limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM memories ORDER BY updated DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"memories": [dict(r) for r in rows], "count": len(rows)}

async def _recall(conn, payload: dict, ollama_url: str, model: str) -> dict:
    query = payload.get("query") or payload.get("q", "")
    if not query:
        return {"error": "query required"}
    # Simple keyword search across memories
    trust_filter = payload.get("trust", "high")
    if trust_filter == "any":
        rows = conn.execute(
            "SELECT * FROM memories WHERE content LIKE ? ORDER BY updated DESC LIMIT 10",
            (f"%{query}%",)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM memories WHERE content LIKE ? AND trust=? ORDER BY updated DESC LIMIT 10",
            (f"%{query}%", trust_filter)
        ).fetchall()
    memories = [dict(r) for r in rows]
    if not memories:
        return {"query": query, "found": 0, "memories": []}
    # Optionally synthesize with ollama
    synthesize = payload.get("synthesize", False)
    if synthesize and memories:
        context = "\n".join([m["content"] for m in memories])
        synthesis = await _ollama_complete(
            ollama_url, model,
            f"Based on these memories:\n{context}\n\nAnswer: {query}"
        )
        return {"query": query, "found": len(memories), "synthesis": synthesis, "memories": memories}
    return {"query": query, "found": len(memories), "memories": memories}


# ── Context ───────────────────────────────────────────────────────────────────

def _context(conn, payload: dict) -> dict:
    action = payload.get("action", "show")
    if action == "set":
        return _context_set(conn, payload)
    elif action == "clear":
        return _context_clear(conn, payload)
    return _context_show(conn)

def _context_set(conn, payload: dict) -> dict:
    key   = payload.get("key", "active")
    value = payload.get("value") or payload.get("text", "")
    if not value:
        return {"error": "value required"}
    now = _ts()
    conn.execute(
        "INSERT OR REPLACE INTO context_store (key, value, updated) VALUES (?,?,?)",
        (key, value, now)
    )
    conn.commit()
    return {"set": key, "value": value, "ts": now}

def _context_show(conn) -> dict:
    rows = conn.execute("SELECT * FROM context_store ORDER BY updated DESC").fetchall()
    return {"context": {r["key"]: r["value"] for r in rows}}

def _context_clear(conn, payload: dict) -> dict:
    key = payload.get("key")
    if key:
        conn.execute("DELETE FROM context_store WHERE key=?", (key,))
        conn.commit()
        return {"cleared": key}
    conn.execute("DELETE FROM context_store")
    conn.commit()
    return {"cleared": "all"}


# ── Federation ────────────────────────────────────────────────────────────────

def _peers_list(conn) -> dict:
    rows = conn.execute("SELECT * FROM peers ORDER BY introduced DESC").fetchall()
    return {"peers": [dict(r) for r in rows], "count": len(rows)}

async def _peers_introduce(conn, payload: dict) -> dict:
    endpoint = payload.get("endpoint", "").rstrip("/")
    if not endpoint:
        return {"error": "endpoint required"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{endpoint}/v1/brain/introduce")
            if resp.status_code != 200:
                return {"error": f"remote returned {resp.status_code}"}
            manifest = resp.json()
    except Exception as e:
        return {"error": f"could not reach {endpoint}: {e}"}

    peer_id = manifest.get("id", hashlib.sha256(endpoint.encode()).hexdigest()[:12])
    now = _ts()
    conn.execute("""
        INSERT OR REPLACE INTO peers (id, endpoint, pubkey, did, caps, introduced, last_seen)
        VALUES (?,?,?,?,?,?,?)
    """, (
        peer_id,
        endpoint,
        manifest.get("pubkey", ""),
        manifest.get("did", ""),
        json.dumps(manifest.get("caps", [])),
        now, now
    ))
    conn.commit()
    return {"introduced": peer_id, "endpoint": endpoint, "manifest": manifest, "ts": now}

async def _peers_ping(conn, payload: dict) -> dict:
    peer_id  = payload.get("id")
    endpoint = payload.get("endpoint")
    if peer_id and not endpoint:
        row = conn.execute("SELECT endpoint FROM peers WHERE id=?", (peer_id,)).fetchone()
        if not row:
            return {"error": f"peer {peer_id} not found"}
        endpoint = row["endpoint"]
    if not endpoint:
        return {"error": "id or endpoint required"}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            start = time.time()
            resp  = await client.get(f"{endpoint.rstrip('/')}/health")
            ms    = round((time.time() - start) * 1000)
            now   = _ts()
            conn.execute("UPDATE peers SET last_seen=? WHERE endpoint=?", (now, endpoint))
            conn.commit()
            return {"endpoint": endpoint, "status": resp.status_code, "ms": ms, "ts": now}
    except Exception as e:
        return {"endpoint": endpoint, "error": str(e)}

def _peers_remove(conn, payload: dict) -> dict:
    peer_id = payload.get("id")
    if not peer_id:
        return {"error": "id required"}
    conn.execute("DELETE FROM peers WHERE id=?", (peer_id,))
    conn.commit()
    return {"removed": peer_id}

def _self_manifest() -> dict:
    """Return this brain's public manifest for federation introduction."""
    return {
        "id":       os.getenv("HBAR_BRAIN_ID", "hbar-brain"),
        "did":      os.getenv("HBAR_BRAIN_DID", ""),
        "pubkey":   os.getenv("HBAR_BRAIN_PUBKEY", ""),
        "caps":     ["tool:health", "tool:recall", "tool:chat", "governance:propose-confirm"],
        "version":  "0.5.0",
        "protocol": "BrainFoundryOS",
        "ts":       _ts(),
    }


# ── Model ─────────────────────────────────────────────────────────────────────

async def _model_current(ollama_url: str, model: str) -> dict:
    return {"current": model, "ollama": ollama_url}

async def _model_list(ollama_url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{ollama_url}/api/tags")
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            return {"models": models, "count": len(models)}
    except Exception as e:
        return {"error": str(e)}

def _model_use(payload: dict) -> dict:
    model = payload.get("model", "")
    if not model:
        return {"error": "model name required"}
    # Note: live switching requires env var update + container restart
    # This returns the instruction for now; full live switching is phase 2
    return {
        "requested": model,
        "instruction": f"Set OLLAMA_MODEL={model} in .env and restart the api container",
        "note": "Live model switching without restart coming in phase 2"
    }


# ── Audit ─────────────────────────────────────────────────────────────────────

def _audit(conn, payload: dict) -> dict:
    limit = int(payload.get("limit", 10))
    rows  = conn.execute(
        "SELECT * FROM audit_log ORDER BY ts DESC LIMIT ?", (limit,)
    ).fetchall()
    return {"entries": [dict(r) for r in rows], "count": len(rows)}

def _audit_clear(conn) -> dict:
    conn.execute("DELETE FROM audit_log")
    conn.commit()
    return {"cleared": True, "ts": _ts()}

def write_audit(conn, command: str, client_id: str, effect: str, result: dict):
    """Call this from main.py to write audit entries."""
    try:
        conn.execute(
            "INSERT INTO audit_log (command, client_id, effect, result, ts) VALUES (?,?,?,?,?)",
            (command, client_id, effect, json.dumps(result)[:500], _ts())
        )
        conn.commit()
    except Exception:
        pass


# ── Policy ────────────────────────────────────────────────────────────────────

def _policy_show() -> dict:
    return {
        "mode":              "propose-confirm",
        "confirm_threshold": os.getenv("HBAR_GOVERNANCE_THRESHOLD", "owner"),
        "effect_classes": {
            "read_only":   "auto-confirm eligible",
            "mutating":    "requires explicit confirm",
            "destructive": "requires explicit confirm + delay",
        },
        "protocol": "BrainFoundryOS",
    }


# ── Ingest ────────────────────────────────────────────────────────────────────

def _ingest_status(payload: dict) -> dict:
    path = payload.get("path", "")
    return {
        "status": "queued",
        "path":   path,
        "note":   "Full CLI ingest (hbar ingest ./docs/) coming in phase 2. Use console UI for now.",
        "console": os.getenv("HBAR_CONSOLE_URL", "https://console.brain.hbar.systems"),
    }


# ── Think (natural language) ──────────────────────────────────────────────────

async def _think(conn, payload: dict, ollama_url: str, model: str) -> dict:
    prompt = payload.get("prompt") or payload.get("text", "")
    if not prompt:
        return {"error": "prompt required"}

    # Pull recent context
    ctx_rows = conn.execute(
        "SELECT key, value FROM context_store ORDER BY updated DESC LIMIT 5"
    ).fetchall()
    context_block = "\n".join([f"{r['key']}: {r['value']}" for r in ctx_rows])

    # Pull recent memories
    mem_rows = conn.execute(
        "SELECT content FROM memories WHERE trust=\'high\' ORDER BY updated DESC LIMIT 5"
    ).fetchall()
    memory_block = "\n".join([r["content"] for r in mem_rows])

    system = f"""You are hbar-brain, a governed intelligence node running BrainFoundryOS.

Active context:
{context_block or 'none'}

Recent memory:
{memory_block or 'none'}

Respond concisely and precisely. You are infrastructure, not a chatbot."""

    response = await _ollama_complete(ollama_url, model, prompt, system)
    return {"prompt": prompt, "response": response, "model": model}


# ── Ollama helper ─────────────────────────────────────────────────────────────

async def _ollama_complete(ollama_url: str, model: str, prompt: str, system: str = "") -> str:
    try:
        payload = {"model": model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{ollama_url}/api/generate", json=payload)
            return resp.json().get("response", "")
    except Exception as e:
        return f"[ollama error: {e}]"
