"""
api/research.py — Deep Research: plan → search → read → cited synthesis.

Modeled on Odysseus's deep_research.py (plan queries, gather from multiple
sources, synthesize a cited report). Built on the brain's own web_search +
fetch_url tools. Single-round by default (fast enough to demo, still pulls from
several independent sources); the engine yields progress events so the UI can
show the work live.

Gathered web content is UNTRUSTED (a page can carry prompt-injection), so the
synthesis prompt wraps the sources via api/security/untrusted and instructs the
model to treat them as quotable reference only — never as instructions.
"""
from __future__ import annotations

import datetime
import json
import re
from typing import Any, AsyncGenerator, Dict, List

from api import providers as _providers
from api.security import untrusted as _untrusted


def _today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _parse_queries(raw: str, fallback: str, n: int) -> List[str]:
    """Pull a list of search queries out of the planner's reply."""
    raw = (raw or "").strip()
    # Try a JSON array first.
    m = re.search(r"\[.*\]", raw, re.S)
    if m:
        try:
            arr = json.loads(m.group(0))
            qs = [str(x).strip() for x in arr if str(x).strip()]
            if qs:
                return qs[:n]
        except Exception:
            pass
    # Fall back to line-by-line (strip bullets/numbering).
    lines = []
    for ln in raw.splitlines():
        ln = re.sub(r"^\s*[-*\d.)]+\s*", "", ln).strip().strip('"')
        if ln and len(ln) < 200:
            lines.append(ln)
    return (lines or [fallback])[:n]


async def run_research(question: str, *, model: str = "", max_queries: int = 4,
                       fetch_per_query: int = 1) -> AsyncGenerator[Dict[str, Any], None]:
    """Async generator yielding {phase, ...} events; the last is phase='done'."""
    question = (question or "").strip()
    if not question:
        yield {"phase": "error", "error": "empty question"}
        return
    model = model or _providers.default_model()

    # ── 1. Plan ──────────────────────────────────────────────────────────
    yield {"phase": "planning", "question": question}
    plan_prompt = (
        f"Today is {_today()}. You are a research strategist. For the question "
        f"below, output ONLY a JSON array of {max_queries} focused web-search "
        f"queries that together would answer it. Use specific terms; include a "
        f"year when recency matters.\n\nQuestion: {question}\n\nJSON array:"
    )
    try:
        raw = await _providers.complete(model, [{"role": "user", "content": plan_prompt}], max_tokens=300)
    except Exception as e:
        yield {"phase": "error", "error": f"planning failed: {e}"}
        return
    queries = _parse_queries(raw, question, max_queries)
    yield {"phase": "plan", "queries": queries}

    # ── 2. Search + read ─────────────────────────────────────────────────
    from api.tools import web_search, fetch_url
    sources: List[Dict[str, Any]] = []
    seen_urls = set()
    for q in queries:
        yield {"phase": "searching", "query": q}
        try:
            res = await web_search.run(q, count=4)
        except Exception:
            continue
        blocks = (res.meta or {}).get("results", []) if res.ok else []
        # Keep all snippets as light sources; fetch the top few for full text.
        for i, b in enumerate(blocks):
            url = b.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            src = {"url": url, "title": b.get("title", ""), "snippet": b.get("snippet", ""), "text": ""}
            if i < fetch_per_query:
                yield {"phase": "reading", "url": url, "title": b.get("title", "")}
                try:
                    page = await fetch_url.run(url)
                    if page.ok:
                        src["text"] = (page.meta or {}).get("text", "")[:3000]
                except Exception:
                    pass
            sources.append(src)

    if not sources:
        yield {"phase": "done", "report": "No web sources were found — is web search "
               "enabled and keyed?", "sources": []}
        return

    # ── 3. Synthesize (sources are untrusted) ────────────────────────────
    yield {"phase": "synthesizing", "source_count": len(sources)}
    numbered = []
    for i, s in enumerate(sources, 1):
        body = s["text"] or s["snippet"]
        numbered.append(f"[{i}] {s['title']} — {s['url']}\n{body}".strip())
    sources_block = _untrusted.untrusted_context_block("web research sources", "\n\n".join(numbered))
    synth_prompt = (
        _untrusted.UNTRUSTED_CONTEXT_POLICY + "\n\n"
        f"Today is {_today()}. Write a clear, well-organized report answering the "
        f"question below, using ONLY the numbered sources. Cite every claim inline "
        f"as [n]. Note where sources agree or disagree. If the sources don't cover "
        f"something, say so.\n\nQuestion: {question}\n\n{sources_block}\n\nReport:"
    )
    try:
        report = await _providers.complete(model, [{"role": "user", "content": synth_prompt}], max_tokens=2000)
    except Exception as e:
        yield {"phase": "error", "error": f"synthesis failed: {e}"}
        return
    yield {"phase": "done", "report": report,
           "sources": [{"title": s["title"], "url": s["url"]} for s in sources]}
