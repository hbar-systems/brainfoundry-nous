"""
api/tools/send_telegram.py — send a Telegram message to the brain's owner.

Tier RED — the FIRST per-call-approved tool, registered to prove the approval
gate (`api/tools/approvals.py`). It is the line crossed: a genuine outbound
"send", not a read. Blast radius is deliberately the smallest a send can have —
it is **owner-only by construction**: it ignores any chat target the model might
supply and always sends to the pinned `owner_chat_id`, so the worst an approved
call can do is deliver a message from the operator to themselves.

No-op-safe: if Telegram isn't connected or no owner is pinned, it returns
ok=False rather than raising — a tool must never crash the chat turn.

This module only *registers* the tool. Whether a call actually runs is decided
upstream in dispatch(): a RED call with no operator-minted, args-matching token
never reaches `run()`.
"""
from __future__ import annotations

from api.tools import RED, Tool, ToolResult, register


async def run(message: str) -> ToolResult:
    from api.integrations import telegram

    text = (message or "").strip()
    if not text:
        return ToolResult(ok=False, error="send_telegram_message needs a non-empty message.")

    chat_id = telegram.owner_chat_id()
    if not chat_id:
        return ToolResult(ok=False, error=(
            "No Telegram owner is pinned. Connect Telegram in Settings and message "
            "the bot once so it can pin you as the owner."))

    try:
        resp = await telegram.send_message(chat_id, text)
    except Exception as e:
        return ToolResult(ok=False, error=f"send_telegram_message failed: {e}")

    if not resp.get("ok"):
        return ToolResult(ok=False, error=f"Telegram rejected the send: {resp.get('description') or resp}")

    return ToolResult(
        ok=True,
        content=f"Sent to the owner's Telegram: {text[:200]}",
        meta={"target": "owner"},
    )


register(Tool(
    name="send_telegram_message",
    description=("Send a short Telegram message to the operator (the brain's owner) — "
                 "e.g. a reminder or heads-up they asked you to send them. It goes ONLY "
                 "to the owner; you cannot choose a recipient. The operator must approve "
                 "the exact message before it is sent."),
    tier=RED,
    input_schema={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "The message text to send to the owner."},
        },
        "required": ["message"],
    },
    run=run,
))
