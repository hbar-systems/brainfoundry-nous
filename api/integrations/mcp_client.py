"""
api/integrations/mcp_client.py — a minimal MCP client (remote HTTP servers).

Connects to a remote Model Context Protocol server over the Streamable-HTTP
transport: POST JSON-RPC to one endpoint; the server replies with either
application/json or a text/event-stream carrying the response. We do the
initialize handshake, discover tools (tools/list), and call them (tools/call).

Trust posture: an MCP server is an external capability the OPERATOR explicitly
connected. Its tools are surfaced to the agentic brain (named
mcp__<server>__<tool>) and its OUTPUT is wrapped untrusted (a server response may
carry injection). The fail-closed gate keeps mcp__* names admin-only for the
*registry* tools; these connected-server calls are routed here directly and are
gated by "is this server connected + enabled", not by the model's say-so alone.
See THREAT_MODEL — connecting a server is a deliberate capability grant.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import httpx

from api import settings_store
from api.security import untrusted as _untrusted

PROTOCOL_VERSION = "2025-06-18"
_sessions: Dict[str, str] = {}   # server name -> Mcp-Session-Id (in-memory)
_id = 0


def _next_id() -> int:
    global _id
    _id += 1
    return _id


def _server(name: str) -> Optional[Dict[str, Any]]:
    for s in settings_store.get_mcp_servers():
        if s.get("name") == name:
            return s
    return None


def _headers(server: Dict[str, Any]) -> Dict[str, str]:
    h = {"Content-Type": "application/json",
         "Accept": "application/json, text/event-stream"}
    sid = _sessions.get(server["name"])
    if sid:
        h["Mcp-Session-Id"] = sid
    if server.get("auth"):
        h["Authorization"] = server["auth"]
    return h


def _extract_result(resp: httpx.Response, req_id: Optional[int]) -> Dict[str, Any]:
    ct = (resp.headers.get("content-type", "") or "").lower()
    if "text/event-stream" in ct:
        # Parse SSE data: lines; return the JSON-RPC message matching req_id.
        last = None
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                try:
                    msg = json.loads(line[5:].strip())
                except Exception:
                    continue
                if req_id is not None and msg.get("id") == req_id:
                    return msg
                last = msg
        return last or {}
    try:
        return resp.json()
    except Exception:
        return {}


async def _rpc(server: Dict[str, Any], method: str, params: Optional[Dict] = None,
               notification: bool = False) -> Tuple[Dict[str, Any], httpx.Response]:
    body: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    req_id = None
    if not notification:
        req_id = _next_id()
        body["id"] = req_id
    if params is not None:
        body["params"] = params
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=45)) as http:
        r = await http.post(server["url"], json=body, headers=_headers(server))
        r.raise_for_status()
        sid = r.headers.get("mcp-session-id")
        if sid:
            _sessions[server["name"]] = sid
        if notification:
            return {}, r
        return _extract_result(r, req_id), r


async def _ensure_session(server: Dict[str, Any]) -> None:
    if _sessions.get(server["name"]):
        return
    init, _ = await _rpc(server, "initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "brainfoundry", "version": "0.1"},
    })
    if init.get("error"):
        raise RuntimeError(init["error"].get("message", "initialize failed"))
    try:
        await _rpc(server, "notifications/initialized", {}, notification=True)
    except Exception:
        pass


async def connect(name: str, url: str, auth: str = "") -> Dict[str, Any]:
    """Initialize + discover tools; persist the server with its tool list."""
    name = (name or "").strip() or "mcp"
    server = {"name": name, "url": url.strip(), "auth": (auth or "").strip(), "enabled": True}
    _sessions.pop(name, None)
    await _ensure_session(server)
    listed, _ = await _rpc(server, "tools/list", {})
    if listed.get("error"):
        raise RuntimeError(listed["error"].get("message", "tools/list failed"))
    tools = (listed.get("result") or {}).get("tools", [])
    server["tools"] = [{"name": t.get("name"), "description": t.get("description", ""),
                        "input_schema": t.get("inputSchema") or {"type": "object", "properties": {}}}
                       for t in tools if t.get("name")]
    settings_store.upsert_mcp_server(server)
    return {"ok": True, "name": name, "tool_count": len(server["tools"]),
            "tools": [t["name"] for t in server["tools"]]}


def disconnect(name: str) -> None:
    _sessions.pop(name, None)
    settings_store.remove_mcp_server(name)


def status() -> Dict[str, Any]:
    servers = settings_store.get_mcp_servers()
    return {"servers": [{"name": s.get("name"), "url": s.get("url"),
                         "enabled": s.get("enabled", True),
                         "tools": [t.get("name") for t in s.get("tools", [])]}
                        for s in servers]}


def agentic_tool_specs() -> List[Dict[str, Any]]:
    """All enabled MCP tools as agentic specs, named mcp__<server>__<tool>."""
    specs = []
    for s in settings_store.get_mcp_servers():
        if not s.get("enabled", True):
            continue
        for t in s.get("tools", []):
            specs.append({
                "name": f"mcp__{s['name']}__{t['name']}",
                "description": f"[{s['name']}] {t.get('description', '')}",
                "input_schema": t.get("input_schema") or {"type": "object", "properties": {}},
            })
    return specs


def _split(full_name: str) -> Tuple[str, str]:
    rest = full_name[len("mcp__"):]
    server, _, tool = rest.partition("__")
    return server, tool


async def call(full_name: str, args: Dict[str, Any]):
    """Call an mcp__<server>__<tool>. Returns an api.tools.ToolResult."""
    from api.tools import ToolResult
    server_name, tool = _split(full_name)
    server = _server(server_name)
    if not server or not server.get("enabled", True):
        return ToolResult(ok=False, error=f"MCP server '{server_name}' is not connected.")
    try:
        await _ensure_session(server)
        res, _ = await _rpc(server, "tools/call", {"name": tool, "arguments": args or {}})
    except Exception as e:
        _sessions.pop(server_name, None)   # drop stale session; next call re-inits
        return ToolResult(ok=False, error=f"MCP call failed: {e}")
    if res.get("error"):
        return ToolResult(ok=False, error=res["error"].get("message", "tool error"))
    result = res.get("result") or {}
    parts = []
    for block in result.get("content", []):
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
        else:
            parts.append(json.dumps(block))
    text = "\n".join(p for p in parts if p) or "(no content)"
    wrapped = _untrusted.untrusted_context_block(f"mcp:{server_name}/{tool}", text)
    return ToolResult(ok=True, content=wrapped,
                      provenance=[{"source": f"mcp:{server_name}", "tool": full_name,
                                   "trust": "untrusted"}],
                      meta={"server": server_name, "tool": tool})
