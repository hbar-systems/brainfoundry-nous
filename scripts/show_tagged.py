#!/usr/bin/env python3
import argparse, os, sqlite3
from tabulate import tabulate

DB_PATH = os.getenv("SEMANTIC_DB_PATH", "extensions/brain/semantic.db")

def main():
    ap = argparse.ArgumentParser(description="Show docs that match ALL given tags.")
    ap.add_argument("--tags", nargs="*", help="Filter by tags")
    ap.add_argument("--list", action="store_true", help="List all tags with doc counts")
    ap.add_argument("--top", type=int, help="Show top N tags by document count")
    args = ap.parse_args()

    if args.list or args.top:
        cx = sqlite3.connect(DB_PATH)
        rows = cx.execute("""
            SELECT t.name, COUNT(DISTINCT de.document_name)
            FROM tags t
            JOIN entity_tags et ON et.tag_id = t.id
            JOIN document_entities de ON de.entity_id = et.entity_id
            GROUP BY t.name
            ORDER BY COUNT(DISTINCT de.document_name) DESC, t.name
        """).fetchall()
        cx.close()
        
        if args.top:
            rows = rows[:args.top]
        
        print(tabulate(rows, headers=["tag", "doc_count"], tablefmt="github"))
        return

    if not args.tags:
        print("Specify --tags, --list, or --top N")
        return

    cx = sqlite3.connect(DB_PATH)
    try:
        q = """
        SELECT de.document_name
        FROM document_entities de
        JOIN entity_tags et ON de.entity_id = et.entity_id
        JOIN tags t ON et.tag_id = t.id
        WHERE t.name IN ({place})
        GROUP BY de.document_name
        HAVING COUNT(DISTINCT t.name) = ?
        ORDER BY de.document_name;
        """.replace("{place}", ",".join(["?"]*len(args.tags)))
        rows = cx.execute(q, (*args.tags, len(args.tags))).fetchall()
        for (doc,) in rows:
            print(doc)
    finally:
        cx.close()

if __name__ == "__main__":
    main()
