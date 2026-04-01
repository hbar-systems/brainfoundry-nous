# api/kernel/handlers.py
from __future__ import annotations

from typing import Any, Callable, Dict


Handler = Callable[..., Dict[str, Any]]

def handle_health(*, ctx: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    health_check = ctx["health_check"]
    return health_check()

def handle_echo(*, ctx: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"echo": payload.get("text")}

def handle_whoami(*, ctx: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "brain": "hbar-brain",
        "version": ctx.get("kernel_version"),
        "host": ctx.get("host"),
    }

def handle_permit_issue(ctx: dict, payload: dict) -> dict:
    """
    Issue a signed permit token (read-only command, but gated by root assertion in main dispatch).
    Expects ctx to include: identity_secret, operator_id, client_id
    Expects payload to include: typ, ttl, reason
    """
    from api.identity.core import issue_permit
    from api.identity.permits import normalize_permit_type

    permit_typ = (payload or {}).get("typ")
    ttl = int((payload or {}).get("ttl") or 900)
    reason = (payload or {}).get("reason") or "issued"

    permit_typ_norm = normalize_permit_type(permit_typ)
    if not permit_typ_norm:
        return {"ok": False, "error": "permit.typ_invalid", "details": {"typ": permit_typ}}

    token = issue_permit(
        secret=ctx["identity_secret"],
        operator_id=ctx["operator_id"],
        client_id=ctx["client_id"],
        permit_type=permit_typ_norm,
        ttl_seconds=ttl,
        reason=reason,
        constraints={},
    )
    return {"permit": token, "typ": permit_typ_norm, "ttl_seconds": ttl}



def handle_status(*, ctx: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    requests = ctx["requests"]
    nodeos_url = ctx.get("nodeos_url")
    ollama_url = ctx.get("ollama_url")
    database_url = ctx.get("database_url")
    get_db_connection = ctx.get("get_db_connection")

    error = None

    # Get API health
    api_status = {"status": "ok"}

    # Check NodeOS health
    nodeos_status: Any = "unknown"
    if nodeos_url:
        try:
            resp = requests.get(f"{nodeos_url}/health", timeout=2)
            if resp.status_code == 200:
                nodeos_status = resp.json()
        except Exception as e:
            error = str(e)

    # Check Ollama health
    ollama_status: Any = "unknown"
    if ollama_url:
        try:
            resp = requests.get(f"{ollama_url}/api/tags", timeout=2)
            if resp.status_code == 200:
                ollama_status = {"status": "healthy", "models": len(resp.json().get("models", []))}
        except Exception as e:
            if not error:
                error = str(e)

    # Check DB health
    db_status: Dict[str, Any] = {"status": "unknown"}
    if database_url and get_db_connection:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            db_status = {"status": "healthy"}
        except Exception as e:
            db_status = {"status": "error", "detail": str(e)[:100]}
    else:
        db_status = {"status": "error", "detail": "DATABASE_URL not configured"}

    result: Dict[str, Any] = {
        "api": api_status,
        "nodeos": nodeos_status,
        "ollama": ollama_status,
        "database": db_status,
    }

    if error:
        result["warning"] = error

    return result



def handle_help(*, ctx: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "available_commands": [
            {"command": "health", "description": "Check system health status"},
            {"command": "whoami", "description": "Display brain identity and version"},
            {"command": "status", "description": "Show detailed service status"},
            {"command": "help", "description": "List available read-only commands"},
            {"command": "version", "description": "Display server version information"},
            {"command": "audit tail N", "description": "Show last N audit entries (default 50, max 1000)"}
        ],
        "usage": "All commands require PROPOSE/CONFIRM workflow. Send command to get token, then resend with confirm_token.",
        "effect": "read_only"
    }


def handle_version(*, ctx: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "server_version": ctx.get("kernel_version"),
        "canon_version": "v1",
        "api_title": "hbar-brain authority endpoint",
        "python_version": ctx.get("python_version"),
        "git_commit": ctx.get("git_commit"),
        "build_time": ctx.get("build_time"),
    }


def handle_audit_tail(*, ctx: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    audit_file = ctx["audit_file"]
    json_mod = ctx["json"]
    n = ctx["n"]

    audit_entries = []
    available_total = 0

    if audit_file.exists():
        try:
            with open(audit_file, "r") as f:
                lines = f.readlines()
                available_total = len(lines)

                for line in reversed(lines[-n:]):
                    try:
                        entry = json_mod.loads(line.strip())
                        audit_entries.append(entry)
                    except Exception:
                        continue
        except Exception as e:
            return {
                "error": f"Failed to read audit log: {str(e)}",
                "entries": [],
                "count": 0,
                "requested": n,
                "order": "reverse_chronological",
                "available_total": available_total,
            }

    return {
        "entries": audit_entries,
        "count": len(audit_entries),
        "requested": n,
        "order": "reverse_chronological",
        "available_total": available_total,
    }



def handle_memory_append(ctx: dict, payload: dict) -> dict:
    """
    DEV-safe memory append placeholder.
    Appends an event to a local jsonl file (no DB yet).
    """
    import json
    from pathlib import Path
    from datetime import datetime, timezone

    text = (payload or {}).get("text")
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "error": "payload.text_required"}

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "client_id": ctx.get("client_id"),
        "operator_id": ctx.get("operator_id"),
        "strain_id": ctx.get("strain_id"),
        "text": text,
    }

    out = Path("data")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "memory_append.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

    return {"appended": True, "bytes": len(text.encode("utf-8"))}






READ_ONLY_HANDLERS: Dict[str, Handler] = {
    "health": handle_health,
    "whoami": handle_whoami,
    "status": handle_status,
    "help": handle_help,
    "version": handle_version,
    "audit tail": handle_audit_tail,
    "echo": handle_echo,
    "permit issue": handle_permit_issue,
}


MEMORY_APPEND_HANDLERS = {
    "memory append": handle_memory_append,
}
