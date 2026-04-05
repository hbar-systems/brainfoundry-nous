#!/usr/bin/env python3
import argparse, json, os, re, sqlite3, sys
import requests

DB_PATH    = os.getenv("SEMANTIC_DB_PATH", "extensions/brain/semantic.db")
API_BASE   = os.getenv("API_BASE", "http://127.0.0.1:8010")
NODEOS_URL = os.getenv("NODEOS_URL", "http://127.0.0.1:8001")
BRAIN_ID   = os.getenv("BRAIN_ID", "my-brain-01")
MODEL      = os.getenv("DEFAULT_MODEL", os.getenv("RAG_MODEL", "llama3.2:3b"))
API_KEY    = os.getenv("BRAIN_API_KEY", "")
_HEADERS   = {"Content-Type": "application/json", **({"X-Api-Key": API_KEY} if API_KEY else {})}

TAG_RX = re.compile(r"\[(?P<body>[^\]]+)\]")

def _acquire_permit():
    r = requests.post(f"{NODEOS_URL}/v1/loops/request", json={
        "node_id": BRAIN_ID,
        "agent_id": "script/ask",
        "loop_type": "research",
        "ttl_seconds": 300,
        "reason": "ask.py script query",
    }, timeout=5)
    r.raise_for_status()
    return r.json()["permit_id"]

def parse_tags(q: str):
    tags = []
    for m in TAG_RX.finditer(q):
        body = m.group("body").strip()
        parts = re.split(r"[,\s]+", body)
        for p in parts:
            p = p.strip()
            if p:
                tags.append(p.lower())
    return tags

def strip_tags(q: str):
    return TAG_RX.sub("", q).strip()

def docs_for_tags(tags):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
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
        if not docs:
            return f"No documents found for tags: {', '.join(tags)}"

    permit_id = _acquire_permit()
    r = requests.post(f"{API_BASE}/chat/rag",
                      json={"query": bare, "permit_id": permit_id},
                      headers=_HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

if __name__ == "__main__":
    q = " ".join(sys.argv[1:]).strip()
    print(ask(q))
