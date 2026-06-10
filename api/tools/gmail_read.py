"""
api/tools/gmail_read.py — read the operator's recent Gmail (metadata + snippet).

Tier YELLOW (external read). READ-ONLY: there is no send/reply/forward path —
that would be RED-tier and is intentionally absent (THREAT_MODEL). Email content
is the canonical untrusted surface (an email body is written by a stranger and
may contain prompt-injection), so output is wrapped as untrusted reference data.
"""
from __future__ import annotations

from typing import Any, Dict

from api.tools import YELLOW, Tool, ToolResult, register
from api.security import untrusted as _untrusted


async def run(query: str = "", max_results: int = 10) -> ToolResult:
    from api.integrations import google
    if not google.is_configured():
        return ToolResult(ok=False, error="Gmail is not set up on this brain "
                          "(no OAuth client configured).")
    if not google.is_connected():
        return ToolResult(ok=False, error="Gmail is not connected. Connect it in "
                          "Settings → Integrations first.")
    try:
        msgs = await google.list_messages(query=query, max_results=max_results)
    except Exception as e:
        return ToolResult(ok=False, error=f"gmail_read failed: {e}")

    if not msgs:
        return ToolResult(ok=True, content="(no matching messages)", meta={"count": 0})

    lines = []
    for i, m in enumerate(msgs, 1):
        flag = " [unread]" if m.get("unread") else ""
        lines.append(f"{i}.{flag} From: {m['from']}\n   Subject: {m['subject']}\n"
                     f"   {m['date']}\n   {m['snippet']}")
    label = f"gmail (query: {query})" if query else "gmail (recent)"
    body = "Recent email messages:\n" + "\n".join(lines)
    content = _untrusted.untrusted_context_block(label, body)
    return ToolResult(ok=True, content=content,
                      provenance=[{"source": "gmail_read", "tool": "gmail_read",
                                   "trust": "untrusted"}],
                      meta={"count": len(msgs)})


register(Tool(
    name="gmail_read",
    description=("Read the operator's recent Gmail messages (sender, subject, "
                 "date, snippet). Optional Gmail search query (e.g. "
                 "'is:unread', 'from:boss', 'newer_than:2d'). Read-only."),
    tier=YELLOW,
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Optional Gmail search query."},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
        },
    },
    run=run,
))
