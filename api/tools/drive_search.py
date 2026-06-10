"""
api/tools/drive_search.py — search the operator's Google Drive (read-only).

Tier YELLOW (external read). Returns file metadata (name, kind, modified, owner,
link) for files matching a name/content query. Read-only — no write/delete path.
File names and owner names are externally-authored, so output is wrapped as
untrusted reference data.
"""
from __future__ import annotations

from typing import Any, Dict

from api.tools import YELLOW, Tool, ToolResult, register
from api.security import untrusted as _untrusted


async def run(query: str = "", max_results: int = 10) -> ToolResult:
    from api.integrations import google
    if not google.is_configured():
        return ToolResult(ok=False, error="Google Drive is not set up on this brain "
                          "(no OAuth client configured).")
    if not google.is_connected():
        return ToolResult(ok=False, error="Google Drive is not connected. Connect Google "
                          "in Settings → Integrations first.")
    try:
        files = await google.list_files(query=query, max_results=max_results)
    except Exception as e:
        return ToolResult(ok=False, error=f"drive_search failed: {e}")

    if not files:
        return ToolResult(ok=True, content="(no matching files in Drive)", meta={"count": 0})

    lines = []
    for i, f in enumerate(files, 1):
        owner = f" · {f['owner']}" if f.get("owner") else ""
        lines.append(f"{i}. {f['name']} [{f['kind']}]{owner}\n   modified {f['modified']}\n   {f['link']}")
    label = f"google-drive (query: {query})" if query else "google-drive (recent)"
    body = "Drive files:\n" + "\n".join(lines)
    content = _untrusted.untrusted_context_block(label, body)
    return ToolResult(ok=True, content=content,
                      provenance=[{"source": "drive_search", "tool": "drive_search",
                                   "trust": "untrusted"}],
                      meta={"count": len(files)})


register(Tool(
    name="drive_search",
    description=("Search the operator's Google Drive for files by name or content. "
                 "Returns file name, type, owner, last-modified, and link. Use for "
                 "'find my deck about X', 'what files do I have on Y'. Read-only."),
    tier=YELLOW,
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Name or full-text search query."},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 25, "default": 10},
        },
    },
    run=run,
))
