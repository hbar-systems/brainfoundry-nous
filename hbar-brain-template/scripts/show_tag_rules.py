#!/usr/bin/env python3
# scripts/show_tag_rules.py
import sys, yaml
from tabulate import tabulate

rules_path = sys.argv[1] if len(sys.argv) > 1 else "extensions/brain/tag_rules.yaml"
with open(rules_path, "r") as f:
    data = yaml.safe_load(f)

rows = []
for rule in data.get("rules", []):
    rid = rule.get("id", "")
    kws = ", ".join(rule.get("if", {}).get("any", [])[:5])
    rxs = ", ".join(rule.get("if", {}).get("exclude", [])[:3])
    rows.append((rid, rule.get("label",""), kws, rxs))

print(tabulate(rows, headers=["rule_id","label","keywords(≤5)","regex(≤3)"], tablefmt="github"))
