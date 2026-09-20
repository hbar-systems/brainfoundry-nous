#!/usr/bin/env python3
"""cc-permit-hook.py: Claude Code PermissionRequest hook for the CC bridge. Created 2026-09-20.

Claude Code runs this when a tool call would need the person's permission. It posts the call
to the bridge on this box and waits for the person's click on the card in their chat, then
answers allow or deny. Standard library only; the bridge passes CC_PORT, CC_BASE and
CC_ASK_TOKEN in the reasoner's environment. Any failure is a deny.
"""
import json
import os
import sys
import urllib.request


def main() -> None:
    try:
        req = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        req = {}
    port = os.environ.get("CC_PORT", "7682")
    base = os.environ.get("CC_BASE", "/cc").rstrip("/")
    url = f"http://127.0.0.1:{port}{base}/ask"
    body = json.dumps({"tool_name": req.get("tool_name"), "tool_input": req.get("tool_input") or {}}).encode()
    decision = {"behavior": "deny", "message": "the bridge did not answer"}
    try:
        r = urllib.request.Request(url, data=body, method="POST",
                                   headers={"Content-Type": "application/json",
                                            "X-CC-Ask": os.environ.get("CC_ASK_TOKEN", "")})
        with urllib.request.urlopen(r, timeout=int(os.environ.get("CC_PERMIT_TTL", "900")) + 60) as resp:
            decision = json.loads(resp.read().decode() or "{}") or decision
    except Exception as e:  # noqa: BLE001
        decision = {"behavior": "deny", "message": f"the bridge did not answer ({type(e).__name__})"}
    out = {"behavior": decision.get("behavior", "deny")}
    if out["behavior"] == "deny":
        out["message"] = decision.get("message") or "refused"
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": out}}))


if __name__ == "__main__":
    main()
