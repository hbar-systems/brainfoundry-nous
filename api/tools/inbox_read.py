"""
api/tools/inbox_read.py — read the operator's email inbox over IMAP.

Tier YELLOW (external read). Provider-agnostic: works with any IMAP mailbox the
operator connected (Gmail, Outlook, Fastmail, self-hosted) via host + app
password — no OAuth. Read-only.

Named inbox_read (not email_read) on purpose: the fail-closed tool gate
default-denies the email_/mail_ families (send/mutation), so a read tool must not
collide with that namespace. Email bodies are the canonical untrusted surface,
so output is wrapped as untrusted reference data.
"""
from __future__ import annotations

from typing import Any, Dict

from api.tools import YELLOW, Tool, ToolResult, register
from api.security import untrusted as _untrusted


async def run(query: str = "", max_results: int = 10, unread_only: bool = False) -> ToolResult:
    from api.integrations import email_imap
    if not email_imap.is_configured():
        return ToolResult(ok=False, error="No email account is connected. Add one in "
                          "Integrations (host + email + app password) first.")
    try:
        msgs = await email_imap.list_messages(query=query, max_results=max_results,
                                              unread_only=unread_only)
    except Exception as e:
        return ToolResult(ok=False, error=f"inbox_read failed: {e}")

    if not msgs:
        return ToolResult(ok=True, content="(no matching messages in the inbox)", meta={"count": 0})

    lines = []
    for i, m in enumerate(msgs, 1):
        flag = " [unread]" if m.get("unread") else ""
        lines.append(f"{i}.{flag} From: {m['from']}\n   Subject: {m['subject']}\n   {m['date']}")
    scope = "unread email" if unread_only else "recent email"
    label = f"inbox ({scope}" + (f", query: {query})" if query else ")")
    body = f"{scope.capitalize()}:\n" + "\n".join(lines)
    content = _untrusted.untrusted_context_block(label, body)
    return ToolResult(ok=True, content=content,
                      provenance=[{"source": "inbox_read", "tool": "inbox_read",
                                   "trust": "untrusted"}],
                      meta={"count": len(msgs)})


register(Tool(
    name="inbox_read",
    description=("Read the operator's email inbox (sender, subject, date, read/"
                 "unread). Set unread_only=true for just unread; optional text "
                 "query to search. Works with any connected IMAP mailbox. "
                 "Read-only."),
    tier=YELLOW,
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Optional text search."},
            "unread_only": {"type": "boolean", "default": False},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 25, "default": 10},
        },
    },
    run=run,
))
