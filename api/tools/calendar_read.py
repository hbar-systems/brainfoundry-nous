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
    # Prefer the simple ICS calendar (no OAuth); fall back to Google OAuth.
    from api.integrations import calendar_ics, google
    source = None
    if calendar_ics.is_configured():
        source = "ics (" + (calendar_ics.status().get("host") or "") + ")"
        getter = calendar_ics.list_events
    elif google.is_configured() and google.is_connected():
        source = "google-calendar (primary)"
        getter = google.list_events
    else:
        return ToolResult(ok=False, error="No calendar is connected. Add a calendar ICS "
                          "link (or connect Google) in Integrations first.")
    try:
        events = await getter(max_results=max_results)
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
    content = _untrusted.untrusted_context_block(source, body)
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
