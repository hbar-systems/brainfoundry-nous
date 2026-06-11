"""
api/tools/task_list.py — read the operator's task list. Tier GREEN (own data).
"""
from __future__ import annotations

from api.tools import GREEN, Tool, ToolResult, register


async def run(include_done: bool = False) -> ToolResult:
    from api import tasks_store
    tasks = tasks_store.list_tasks(include_done=include_done)
    if not tasks:
        return ToolResult(ok=True, content="(no open tasks)", meta={"count": 0})
    lines = []
    for i, t in enumerate(tasks, 1):
        box = "[x]" if t.get("done") else "[ ]"
        due = f" — due {t['due']}" if t.get("due") else ""
        lines.append(f"{i}. {box} {t['text']}{due}")
    return ToolResult(ok=True, content="Tasks:\n" + "\n".join(lines), meta={"count": len(tasks)})


register(Tool(
    name="task_list",
    description="List the operator's open tasks / reminders (set include_done=true to include completed).",
    tier=GREEN,
    input_schema={
        "type": "object",
        "properties": {"include_done": {"type": "boolean", "default": False}},
    },
    run=run,
))
