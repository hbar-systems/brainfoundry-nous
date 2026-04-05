import argparse, json, os, sqlite3, urllib.request

DB_PATH    = os.getenv("SEMANTIC_DB_PATH", "extensions/brain/semantic.db")
API        = os.getenv("API_URL", "http://127.0.0.1:8010")
NODEOS_URL = os.getenv("NODEOS_URL", "http://127.0.0.1:8001")
BRAIN_ID   = os.getenv("BRAIN_ID", "my-brain-01")
MODEL      = os.getenv("DEFAULT_MODEL", os.getenv("RAG_MODEL", "llama3.2:3b"))
API_KEY    = os.getenv("BRAIN_API_KEY", "")

def _acquire_permit():
    import urllib.error
    req = urllib.request.Request(
        f"{NODEOS_URL}/v1/loops/request",
        data=json.dumps({
            "node_id": BRAIN_ID,
            "agent_id": "script/rag_with_tags",
            "loop_type": "research",
            "ttl_seconds": 300,
            "reason": "rag_with_tags.py script query",
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())["permit_id"]

def post(path, payload):
    hdrs = {"Content-Type": "application/json"}
    if API_KEY:
        hdrs["X-Api-Key"] = API_KEY
    req = urllib.request.Request(
        API + path,
        data=json.dumps(payload).encode(),
        headers=hdrs,
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())

def docs_for_tags(tags):
    cx = sqlite3.connect(DB_PATH)
    q = f"""
    SELECT de.document_name
    FROM document_entities de
    JOIN entity_tags et ON et.entity_id = de.entity_id
    JOIN tags t ON t.id = et.tag_id
    WHERE t.name IN ({",".join(["?"]*len(tags))})
    GROUP BY de.document_name
    HAVING COUNT(DISTINCT t.name)=?
    ORDER BY de.document_name;
    """
    rows = [r[0] for r in cx.execute(q, (*tags, len(tags))).fetchall()]
    cx.close()
    return rows

def main():
    ap = argparse.ArgumentParser(description="Tag-constrained RAG")
    ap.add_argument("--tags", nargs="+", required=True, help="tag names (ALL must match)")
    ap.add_argument("--query", required=True)
    ap.add_argument("--limit", type=int, default=24)
    args = ap.parse_args()

    names = docs_for_tags(args.tags)
    if not names:
        print(json.dumps({"answer":"","used_docs":[],"note":"no docs match tags"}))
        return

    # retrieve chunks for the user query
    search = post("/documents/search", {"query": args.query, "limit": args.limit})
    chunks = [r for r in search.get("results", []) if r.get("document_name") in set(names)]
    # build compact context
    ctx = "\n\n".join(r["content"] for r in chunks)[:6000]

    # ask the model using only this context
    permit_id = _acquire_permit()
    body = {
        "model": MODEL,
        "permit_id": permit_id,
        "messages": [
            {"role":"system","content":"Answer using ONLY the provided context. If context is insufficient, say so."},
            {"role":"user","content": f"Context:\n{ctx}\n\nQuestion: {args.query}"}
        ]
    }
    resp = post("/chat/completions", body)
    msg = resp.get("choices",[{}])[0].get("message",{}).get("content","")
    print(json.dumps({
        "answer": msg,
        "used_docs": sorted({r["document_name"] for r in chunks}),
        "chunks": len(chunks)
    }, ensure_ascii=False))
if __name__ == "__main__":
    main()