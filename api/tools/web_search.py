"""
api/tools/web_search.py — the brain's first real tool: read the open web.

Provider: Brave Search API (ROADMAP §v1.1+ named it — commercial-clean, no
contract, soloist-friendly paid tier, privacy-aligned with the brand). The key
is held under the operator's own billing (BRAVE_SEARCH_API_KEY), never a
company alias, so tools stay portable across entity structures.

Tier: YELLOW (external API read). OFF until the operator enables it and supplies
a key. We request only search results (titles, URLs, snippets) — we do NOT
fetch arbitrary pages here, which keeps this tool free of SSRF surface. Page
fetch is a separate, later tool with its own gate.

Output is SAFETY-WRAPPED (see tools/safety.py): results reach the model as
clearly-marked untrusted reference data, with provenance (URL + retrieval time)
carried alongside for the operator-facing "sources" surface.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

from api.tools import YELLOW, Tool, ToolResult, register, safety

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_DEFAULT_COUNT = 5
_MAX_COUNT = 10


async def _brave(query: str, count: int) -> List[Dict[str, Any]]:
    """Call Brave and normalize web results to {title, url, snippet, age}."""
    key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not key:
        raise RuntimeError("BRAVE_SEARCH_API_KEY is not set")
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": key,
    }
    params = {"q": query, "count": count, "safesearch": "moderate"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=15)) as http:
        r = await http.get(BRAVE_ENDPOINT, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
    results = []
    for item in (data.get("web", {}) or {}).get("results", [])[:count]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("description", ""),
            "age": item.get("age", ""),
        })
    return results


async def run(query: str, count: int = _DEFAULT_COUNT) -> ToolResult:
    query = (query or "").strip()
    if not query:
        return ToolResult(ok=False, error="web_search: empty query")
    try:
        count = max(1, min(int(count), _MAX_COUNT))
    except (TypeError, ValueError):
        count = _DEFAULT_COUNT

    try:
        blocks = await _brave(query, count)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        hint = ("invalid or missing Brave API key" if code in (401, 403)
                else "Brave rate limit hit" if code == 429
                else f"Brave returned HTTP {code}")
        return ToolResult(ok=False, error=f"web_search failed: {hint}")
    except Exception as e:
        return ToolResult(ok=False, error=f"web_search failed: {e}")

    retrieved_at = datetime.now(timezone.utc).isoformat()
    provenance = [
        {"source": "web_search", "tool": "web_search", "trust": "untrusted",
         "title": b["title"], "url": b["url"], "retrieved_at": retrieved_at}
        for b in blocks if b.get("url")
    ]
    content = safety.wrap_untrusted(blocks)
    return ToolResult(
        ok=True,
        content=content,
        provenance=provenance,
        # `results` carries the raw blocks (incl. snippets) so downstream
        # analysis — e.g. the corroboration scorer — can read them without
        # re-parsing the safety-wrapped content.
        meta={"query": query, "count": len(blocks), "results": blocks},
    )


register(Tool(
    name="web_search",
    description=("Search the public web (Brave) for current or external "
                 "information the brain's own memory does not contain. Returns "
                 "titles, URLs, and snippets as untrusted reference data."),
    tier=YELLOW,
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query."},
            "count": {"type": "integer", "minimum": 1, "maximum": _MAX_COUNT,
                      "default": _DEFAULT_COUNT},
        },
        "required": ["query"],
    },
    run=run,
))
