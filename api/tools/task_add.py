"""
api/tools/task_add.py — add a task / reminder to the brain's own list.

Tier GREEN: it writes only to the brain's own task store (not an external system,
not destructive), so it's allowed in agentic mode — "remind me to call the
clinic tomorrow" becomes a task. If a due time is given as ISO 8601, the reminder
loop pings Telegram when it comes up.
"""
from __future__ import annotations

from api.tools import GREEN, Tool, ToolResult, register


async def run(text: str, due: str = "") -> ToolResult:
    from api import tasks_store
    try:
        task = tasks_store.add(text, due=(due or None))
    except Exception as e:
        return ToolResult(ok=False, error=f"task_add failed: {e}")
    when = f" (due {task['due']})" if task.get("due") else ""
    return ToolResult(ok=True, content=f"Added task: {task['text']}{when}", meta={"task": task})


register(Tool(
    name="task_add",
    description=("Add a task or reminder to the operator's task list. Use when "
                 "they say 'remind me to …' or 'add a task …'. Optional `due` as "
                 "ISO 8601 (e.g. 2026-06-12T15:00:00Z) — compute it from today's "
                 "date when they say 'tomorrow'/'in 2 hours'."),
    tier=GREEN,
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "What to do."},
            "due": {"type": "string", "description": "Optional ISO 8601 due time."},
        },
        "required": ["text"],
    },
    run=run,
))
