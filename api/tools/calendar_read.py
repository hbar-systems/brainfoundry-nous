"""
api/tools/calendar_read.py — read the operator's upcoming Google Calendar events.

Tier YELLOW (external read, gated by the same operator authorization as web).
Calendar events are externally-authored (an invite title/description can carry a
prompt-injection), so the output is wrapped as untrusted reference data.
"""
from __future__ import annotations

from typing import Any, Dict

from api.tools import YELLOW, Tool, ToolResult, register
from api.security import untrusted as _untrusted


async def run(max_results: int = 10) -> ToolResult:
    from api.integrations import google
    if not google.is_configured():
        return ToolResult(ok=False, error="Google Calendar is not set up on this brain "
                          "(no OAuth client configured).")
    if not google.is_connected():
        return ToolResult(ok=False, error="Google Calendar is not connected. Connect it "
                          "in Settings → Integrations first.")
    try:
        events = await google.list_events(max_results=max_results)
    except Exception as e:
        return ToolResult(ok=False, error=f"calendar_read failed: {e}")

    if not events:
        return ToolResult(ok=True, content="(no upcoming events on the primary calendar)",
                          meta={"count": 0})

    lines = []
    for i, ev in enumerate(events, 1):
        who = f" with {', '.join(ev['attendees'][:5])}" if ev.get("attendees") else ""
        where = f" @ {ev['location']}" if ev.get("location") else ""
        lines.append(f"{i}. {ev['start']} — {ev['summary']}{where}{who}")
    body = "Upcoming calendar events:\n" + "\n".join(lines)
    content = _untrusted.untrusted_context_block("google-calendar (primary)", body)
    return ToolResult(ok=True, content=content,
                      provenance=[{"source": "calendar_read", "tool": "calendar_read",
                                   "trust": "untrusted"}],
                      meta={"count": len(events)})


register(Tool(
    name="calendar_read",
    description=("Read the operator's upcoming Google Calendar events (primary "
                 "calendar, soonest first). Use for questions about their "
                 "schedule, meetings, or availability."),
    tier=YELLOW,
    input_schema={
        "type": "object",
        "properties": {
            "max_results": {"type": "integer", "minimum": 1, "maximum": 25, "default": 10},
        },
    },
    run=run,
))
