#!/usr/bin/env python3
import argparse, json, os, re, sqlite3, sys
from datetime import datetime

import requests
try:
    import yaml
except Exception:
    print("Missing dependency: pyyaml. Run: pip install pyyaml", file=sys.stderr); sys.exit(1)

try:
    from tabulate import tabulate
except Exception:
    print("Missing dependency: tabulate. Run: pip install tabulate", file=sys.stderr); sys.exit(1)

API = os.getenv("API_URL", os.getenv("API_BASE", "http://127.0.0.1:8010"))
DB_PATH = os.getenv("SEMANTIC_DB_PATH", "extensions/brain/semantic.db")
API_KEY = os.getenv("BRAIN_API_KEY", "")

def load_rules(path):
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    rules = data.get("rules", [])
    # compile regexes (case-insensitive); plain words become simple substrings
    for r in rules:
        any_kw = r.get("if", {}).get("any", []) or []
        r["_any_rx"] = [re.compile(k, re.I) for k in any_kw]
        excl_kw = r.get("if", {}).get("exclude", []) or []
        r["_exclude_rx"] = [re.compile(k, re.I) for k in excl_kw]
    return rules

def api_search(query, limit):
    hdrs = {"Content-Type": "application/json"}
    if API_KEY:
        hdrs["X-Api-Key"] = API_KEY
    r = requests.post(f"{API}/documents/search",
                      headers=hdrs,
                      data=json.dumps({"query": query, "limit": limit}))
    r.raise_for_status()
    return r.json().get("results", [])

# --- SQLite helpers ---------------------------------------------------------
def db_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)

def get_tag_id(cx, name):
    cx.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
    cur = cx.execute("SELECT id FROM tags WHERE name = ?", (name,))
    return cur.fetchone()[0]

def get_entity_id(cx, name, etype, description=None, metadata=None):
    cx.execute(
        "INSERT OR IGNORE INTO entities(name, type, description, metadata) VALUES (?, ?, ?, ?)",
        (name, etype, description or "", json.dumps(metadata or {}))
    )
    cur = cx.execute("SELECT id FROM entities WHERE name = ?", (name,))
    return cur.fetchone()[0]

def link_entity_tag(cx, entity_id, tag_id):
    cx.execute("INSERT OR IGNORE INTO entity_tags(entity_id, tag_id) VALUES (?, ?)", (entity_id, tag_id))

def link_doc_entity(cx, doc_name, entity_id, relevance=1.0, context="rule"):
    # avoid duplicates
    cur = cx.execute(
        "SELECT 1 FROM document_entities WHERE document_name=? AND entity_id=?",
        (doc_name, entity_id)
    )
    if cur.fetchone() is None:
        cx.execute(
            "INSERT INTO document_entities(document_name, entity_id, relevance, context) VALUES (?, ?, ?, ?)",
            (doc_name, entity_id, relevance, context)
        )

def matches_rule(r, text):
    if not r["_any_rx"]:
        return False
    if not any(rx.search(text) for rx in r["_any_rx"]):
        return False
    if r["_exclude_rx"] and any(rx.search(text) for rx in r["_exclude_rx"]):
        return False
    return True

def apply_rules(rules, limit=25, dry_run=False, verbose=False):
    cx = db_conn()
    try:
        total_links, rule_hits = 0, {}
        for r in rules:
            hits = []
            # Use each keyword separately to broaden recall
            keywords = r.get("if", {}).get("any", []) or []
            seen_docs = set()
            for kw in keywords:
                for res in api_search(kw, limit):
                    doc = res.get("document_name") or ""
                    content = res.get("content") or ""
                    blob = f"{doc}\n{content}"
                    if doc and doc not in seen_docs and matches_rule(r, blob):
                        hits.append(doc)
                        seen_docs.add(doc)
            rule_hits[r["id"]] = sorted(hits)
            if verbose:
                print(f"[rule:{r['id']}] matched {len(hits)} docs")

            if dry_run or not hits:
                continue

            # materialize tags/entities + links
            add_tags = r.get("add_tags", []) or []
            add_entities = r.get("add_entities", []) or []

            # ensure entities exist; attach rule tags to those entities too
            ent_ids = []
            for ent in add_entities:
                eid = get_entity_id(cx,
                                    ent.get("name"),
                                    ent.get("type","concept"),
                                    ent.get("description",""),
                                    ent.get("metadata"))
                ent_ids.append(eid)

            tag_ids = [get_tag_id(cx, t) for t in add_tags]
            for eid in ent_ids:
                for tid in tag_ids:
                    link_entity_tag(cx, eid, tid)

            # for each matched doc, link all entities; if no entities were specified,
            # we still want the tags present at least via a lightweight "rule/<id>" entity
            if not ent_ids and add_tags:
                e_name = f"rule/{r['id']}"
                eid = get_entity_id(cx, e_name, "rule", f"Auto entity for rule {r['id']}")
                for tid in tag_ids:
                    link_entity_tag(cx, eid, tid)
                ent_ids = [eid]

            for doc in hits:
                for eid in ent_ids:
                    link_doc_entity(cx, doc, eid, 1.0, f"rule:{r['id']}")
                    total_links += 1

        if not dry_run:
            cx.commit()
        return {"links_created": total_links, "rule_hits": rule_hits}
    finally:
        cx.close()

def main():
    # ap = argparse.ArgumentParser(description="Apply tag/entity rules to documents.")
    # ap.add_argument("--rules", default="extensions/brain/tag_rules.yaml")
    ap = argparse.ArgumentParser(description="Apply tag rules to documents.")
    ap.add_argument("--rules", default="extensions/brain/tag_rules.yaml")
    ap.add_argument("--path", default=".")
    ap.add_argument("--dry-run", action="store_true", help="Preview matches; do not write to DB")
    ap.add_argument("--only", help="Run a single rule by name (exact match)")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--summary", action="store_true", help="Dry-run all rules and print hit counts")
    ap.add_argument("--explain", action="store_true", help="Show why each document matched (requires --dry-run or --summary)")
    args = ap.parse_args()

    rules = load_rules(args.rules)
    if args.only:
        rules = [r for r in rules if r.get("id") == args.only or r.get("name") == args.only]
    
    if args.explain and not args.dry_run and not args.summary:
        print("--explain requires --dry-run or --summary"); sys.exit(2)
    
    out = apply_rules(rules, limit=args.limit, dry_run=args.dry_run, verbose=args.verbose)
    
    if args.summary:
        res = apply_rules(rules, limit=args.limit, dry_run=True, verbose=False)
        hits = res.get("rule_hits", {})
        # Create pretty table output
        rows = [(rule_id, len(docs)) for rule_id, docs in sorted(hits.items(), key=lambda x: (-len(x[1]), x[0]))]
        print(tabulate(rows, headers=["rule_id", "matched_docs"], tablefmt="github"))
        sys.exit(0)
    else:
        print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
