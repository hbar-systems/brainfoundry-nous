

#!/usr/bin/env python3
import argparse, json, os, re, sqlite3, sys
import requests

DB_PATH = os.getenv("SEMANTIC_DB_PATH", "extensions/brain/semantic.db")
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
MODEL   = os.getenv("RAG_MODEL", "llama3.2:1b")

TAG_RX = re.compile(r"\[(?P<body>[^\]]+)\]")

def parse_tags(q: str):
    """
    Accepts:
        [topic:quantum] [project:my-project] [todo]
    Returns normalized tags like: ["topic:quantum","project:my-project","todo"]
    """
    tags = []
    for m in TAG_RX.finditer(q):
        body = m.group("body").strip()
        # allow comma-separated or space-separated within a single [ ... ]
        parts = re.split(r"[,\s]+", body)
        for p in parts:
            p = p.strip()
            if p:
                tags.append(p.lower())
    return tags

def strip_tags(q: str):
    return TAG_RX.sub("", q).strip()

def docs_for_tags(tags):
    # tags table(name TEXT), entity_tags(entity_id, tag_name), document_entities(doc, entity_id)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # Allow both simple tags ("todo") and namespaced ("topic:quantum")
    qmarks = ",".join("?" * len(tags))
    cur.execute(f"""
        SELECT DISTINCT de.document_name
        FROM document_entities de
        JOIN entity_tags et ON et.entity_id = de.entity_id
        JOIN tags t ON t.id = et.tag_id
        WHERE t.name IN ({qmarks})
    """, tags)
    docs = [r["document_name"] for r in cur.fetchall()]
    conn.close()
    return docs

def ask(query: str):
    tags = parse_tags(query)
    bare = strip_tags(query)
    
    if tags:
        docs = docs_for_tags(tags)
        if docs:
            # hit a tag-constrained endpoint you already exposed, or reuse /chat/completions
            payload = {"query": bare, "restrict_docs": docs, "max_tokens": 512}
            r = requests.post(f"{API_BASE}/chat/completions", json=payload, timeout=60)
            r.raise_for_status()
            return r.json()["answer"]
        # if tags present but no docs, say so (or fall back)
        return f"No documents found for tags: {', '.join(tags)}"
    else:
        r = requests.post(f"{API_BASE}/chat/rag", json={"query": bare}, timeout=60)
        r.raise_for_status()
        return r.json()["answer"]

if __name__ == "__main__":
    q = " ".join(sys.argv[1:]).strip()
    print(ask(q))