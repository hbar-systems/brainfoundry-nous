"""cc-post-hook.py: Claude Code PostToolUse hook for the CC bridge. Created 2026-10-01.

Claude Code creates the files it writes closed (mode 600). After the two-user split the bridge
is another user, so the Files pane could not read what the reasoner had just made (hbar,
2026-10-01: PermissionError on out/2026-10-01/tuzy-links.txt). This runs as the hands after
every Write, Edit, MultiEdit or NotebookEdit and opens that one file to its group (0664), so
the bridge reads it and the person sees it. Standard library only. Any failure is silent:
a hook must never break a turn.
"""
import json
import os
import sys


def main() -> None:
    try:
        req = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return
    inp = req.get("tool_input") or {}
    path = inp.get("file_path") or inp.get("notebook_path") or ""
    if not path:
        return
    try:
        st = os.stat(path)
        if st.st_mode & 0o060 != 0o060:
            os.chmod(path, (st.st_mode & 0o777) | 0o064)
    except OSError:
        pass


if __name__ == "__main__":
    main()
