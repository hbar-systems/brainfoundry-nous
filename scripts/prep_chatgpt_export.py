#!/usr/bin/env python3
"""Kept for the old command line; the work is in scripts/import_chats.py (2026-10-13).

The previous version read only a dict-shaped conversations.json (the official
export is a top-level array), merged every chat into one file and cut it at
200,000 characters. Now: one markdown document per conversation, main branch
only, role-labelled and dated, nothing cut. See docs/IMPORT.md.

usage: prep_chatgpt_export.py <export.zip | dir | conversations.json> [out_dir]
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import import_chats  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    import_chats.main(["prep", sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "prepared_docs"])
