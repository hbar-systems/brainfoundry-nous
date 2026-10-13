#!/usr/bin/env bash
# ChatGPT or Claude export -> prepared documents -> a selection -> proposals through the gate.
# The last step, approve, is the person's own yes and is never run from here (docs/IMPORT.md, 2026-10-13).
# The previous version posted to /documents/upload without a permit, which a current brain refuses.
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $0 <export.zip|dir> [label] [select filters, e.g. --since 2025-01-01 --exclude strike.txt]"; exit 1
fi

src="$1"; shift
label="${1:-$(date +%Y-%m-%d)}"; [ $# -gt 0 ] && shift
out_dir="prepared_docs/import_${label}"

python3 scripts/import_chats.py prep "$src" "$out_dir"
python3 scripts/import_chats.py select "$out_dir" "$@"
python3 scripts/import_chats.py propose "$out_dir"

echo "Proposed. Read $out_dir/manifest.tsv; the person approves with the id printed above:"
echo "  python3 scripts/import_chats.py approve $out_dir --yes <manifest_id>"
