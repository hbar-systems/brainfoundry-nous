#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $0 <export_dir> [label]"; exit 1
fi

export_dir="$1"
label="${2:-$(date +%Y-%m-%d)}"
out_dir="prepared_docs/chatgpt_${label}"

# 1) prep to text files
python3 scripts/prep_chatgpt_export.py "$export_dir" "$out_dir"

# 2) kill macOS ghost files
find "$out_dir" -type f -name '._*' -delete || true
find "$out_dir" -name '.DS_Store' -delete || true

# 3) ingest
python3 scripts/ingest_folder.py "$out_dir"

# 4) link docs to a source/<label> entity
python3 - <<PY
from extensions.brain.semantic_db import SemanticDB
import os, json
src = "source/chatgpt_${label}"
db = SemanticDB()
eid = db.upsert_entity(name=src, type="source", description=f"ChatGPT export {label}")
for fn in os.listdir("$out_dir"):
    if fn.startswith("._") or fn.startswith("."): 
        continue
    db.link_document(fn, eid, relevance=1.0, context="chatgpt_import")
print(f"Linked {src} to files in $out_dir")
PY

echo "✅ Import complete for $export_dir → $out_dir (entity: source/chatgpt_${label})"


# Make it executable:
# chmod +x scripts/import_chatgpt.sh