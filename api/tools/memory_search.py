"""
api/tools/memory_search.py — the brain reads its OWN memory, on demand.

Tier: GREEN (read/summarize over the brain's own corpus). Always allowed — no
operator toggle, no external network, no budget cap. This is the canonical
green-tier tool and the counterpart to the yellow web_search: when the model is
running agentically it can decide to pull more specific context from memory
mid-reasoning instead of relying only on the one-shot RAG injection.

Output is the brain's own (trusted) documents, so it is NOT safety-wrapped the
way external/untrusted tool output is. Each result carries its memory-type
provenance label (api/memory_type) so the model can still weight a curated fact
above an inferred summary or an untrusted scrape.
"""
from __future__ import annotations

from typing import Any, Dict, List

from api.tools import GREEN, Tool, ToolResult, register

_DEFAULT_LIMIT = 5
_MAX_LIMIT = 10


def run(query: str, limit: int = _DEFAULT_LIMIT) -> ToolResult:
    query = (query or "").strip()
    if not query:
        return ToolResult(ok=False, error="search_memory: empty query")
    try:
        limit = max(1, min(int(limit), _MAX_LIMIT))
    except (TypeError, ValueError):
        limit = _DEFAULT_LIMIT

    # Lazy import — search_similar_documents lives in api.main, which imports
    # this package; importing at call time (request-time) avoids the cycle.
    try:
        from api.main import search_similar_documents
        from api import memory_type as _memtype
    except Exception as e:  # pragma: no cover - import wiring
        return ToolResult(ok=False, error=f"search_memory unavailable: {e}")

    try:
        docs = search_similar_documents(query, limit=limit, architecture="flat")
    except Exception as e:
        return ToolResult(ok=False, error=f"search_memory failed: {e}")

    if not docs:
        return ToolResult(ok=True, content="(no matching documents in memory)",
                          provenance=[], meta={"query": query, "count": 0, "results": []})

    lines: List[str] = ["The brain's own memory returned these documents (trusted):"]
    provenance: List[Dict[str, Any]] = []
    for i, d in enumerate(docs, 1):
        md = d.get("metadata") or {}
        label = _memtype.label(md)
        name = d.get("document_name", f"document {i}")
        head = f"[memory {i}: {name}{(' — ' + label) if label else ''}]"
        lines.append(f"{head}\n{d.get('content', '')}")
        provenance.append({
            "source": "search_memory", "tool": "search_memory",
            "trust": md.get("mem_type", "semantic"),
            "title": name,
        })

    return ToolResult(
        ok=True,
        content="\n\n".join(lines),
        provenance=provenance,
        meta={"query": query, "count": len(docs), "results": docs},
    )


register(Tool(
    name="search_memory",
    description=("Search the brain's OWN stored documents and memories for "
                 "information relevant to the question. Use this to pull "
                 "specific context the brain already holds before answering. "
                 "Returns the brain's own (trusted) documents."),
    tier=GREEN,
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to look for in memory."},
            "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_LIMIT,
                      "default": _DEFAULT_LIMIT},
        },
        "required": ["query"],
    },
    run=run,
))
