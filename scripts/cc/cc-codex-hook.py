#!/usr/bin/env python3
"""cc-codex-hook.py: the Codex seat's PreToolUse hook (2026-11-03, CC_CODEX_WRITE=1).

Codex runs this before every shell command, patch and MCP call. It asks the bridge on this box
the same /ask the Claude seat's permission hook asks (one card per call, one per file of a patch),
waits for the person's click, and lets the call through only on allow. Codex lets a call through
when a hook exits non-zero or runs past its timeout (measured on 0.162.1), so this script never
does either: every path ends in a printed deny, and the wait gives up 30 s after the permit
expires, 90 s inside Codex's timeout. Standard library only.
"""
import json
import os
import sys
import urllib.request


def deny(why: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": why or "refused"}}))
    sys.stdout.flush()


def main() -> None:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import cc_codex_gate
    payload = json.loads(sys.stdin.read() or "{}")
    port = os.environ.get("CC_PORT", "7682")
    base = os.environ.get("CC_BASE", "/cc").rstrip("/")
    ttl = int(os.environ.get("CC_PERMIT_TTL", "900"))
    for tool, inp in cc_codex_gate.asks(payload if isinstance(payload, dict) else {}):
        body = json.dumps({"tool_name": tool, "tool_input": inp, "session_id": payload.get("session_id"),
                           "seat": "codex"}).encode()
        r = urllib.request.Request(f"http://127.0.0.1:{port}{base}/ask", data=body, method="POST",
                                   headers={"Content-Type": "application/json",
                                            "X-CC-Ask": os.environ.get("CC_ASK_TOKEN", "")})
        try:
            with urllib.request.urlopen(r, timeout=ttl + 30) as resp:
                d = json.loads(resp.read().decode() or "{}")
        except Exception as e:  # noqa: BLE001
            return deny(f"the bridge did not answer ({type(e).__name__}); nothing ran")
        if not isinstance(d, dict) or d.get("behavior") != "allow":
            return deny(str((d or {}).get("message") or "refused") if isinstance(d, dict) else "refused")
    # allowed: print nothing, exit 0, and Codex runs the call


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:  # noqa: BLE001  (a crash would let the call through)
        deny(f"the card hook failed ({type(e).__name__}); nothing ran")
    sys.exit(0)
