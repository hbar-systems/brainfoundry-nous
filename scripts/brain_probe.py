#!/usr/bin/env python3
import json
import sys
from urllib.parse import urljoin

import requests

def get_json(base: str, path: str, timeout: float = 5.0):
    url = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()

def main():
    if len(sys.argv) < 2:
        print("Usage: brain_probe.py <BASE_URL>  (e.g. http://localhost:8010)", file=sys.stderr)
        sys.exit(2)

    base = sys.argv[1]
    out = {
        "base_url": base,
        "identity": get_json(base, "/identity"),
        "capabilities": get_json(base, "/capabilities"),
    }
    print(json.dumps(out, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
