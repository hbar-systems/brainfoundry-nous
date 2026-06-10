"""
api/tools/fetch_url.py — read a single web page on demand.

The companion to web_search: search finds URLs, fetch reads one. Tier YELLOW
(external read), so it needs the operator's standing authorization, the same as
web_search. Output is SAFETY-WRAPPED — a fetched page is untrusted text and may
carry prompt-injection, so it reaches the model as clearly-marked reference data
(see api/tools/safety.py and api/security/untrusted.py).

SSRF defense (THREAT_MODEL.md gap #4): a fetch tool that takes a model- or
user-supplied URL is an SSRF vector — it could be pointed at the cloud metadata
endpoint (169.254.169.254) or an internal service. So every URL, AND every
redirect hop, is validated: scheme must be http/https, and the resolved address
must be public (no private / loopback / link-local / reserved ranges). Redirects
are followed manually, re-validating each hop, capped at 3.
"""
from __future__ import annotations

import ipaddress
import socket
from html.parser import HTMLParser
from typing import Any, Dict, List, Tuple
from urllib.parse import urljoin, urlparse

import httpx

from api.tools import YELLOW, Tool, ToolResult, register, safety

_MAX_BYTES = 2_000_000          # stop reading a response past ~2 MB
_MAX_TEXT_CHARS = 8_000         # cap extracted text so it can't flood the prompt
_MAX_REDIRECTS = 3
_ALLOWED_SCHEMES = {"http", "https"}
_ALLOWED_CONTENT = ("text/html", "text/plain", "application/json",
                    "application/xhtml+xml", "text/markdown")


def _is_public_address(host: str) -> bool:
    """True only if every address `host` resolves to is a public IP. Blocks the
    SSRF ranges: private, loopback, link-local (incl. 169.254.169.254 metadata),
    reserved, multicast, unspecified."""
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


def _validate(url: str) -> Tuple[bool, str]:
    """Return (ok, reason). Enforces scheme + public-address policy."""
    try:
        p = urlparse(url)
    except Exception:
        return False, "unparseable URL"
    if p.scheme not in _ALLOWED_SCHEMES:
        return False, f"scheme {p.scheme!r} not allowed (http/https only)"
    if not p.hostname:
        return False, "no host in URL"
    if not _is_public_address(p.hostname):
        return False, "host resolves to a non-public address (blocked)"
    return True, ""


class _TextExtractor(HTMLParser):
    """Minimal HTML → text: drop script/style, keep visible text + block breaks."""
    _SKIP = {"script", "style", "noscript", "template", "svg"}
    _BREAK = {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
              "section", "article", "header", "footer", "blockquote"}

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._parts: List[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in self._BREAK:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title and not self.title:
            self.title = data.strip()
        text = data.strip()
        if text:
            self._parts.append(text)

    def text(self) -> str:
        out = " ".join(self._parts)
        # collapse runs of whitespace but keep paragraph breaks
        lines = [ln.strip() for ln in out.split("\n")]
        return "\n".join(ln for ln in lines if ln)


def _extract(content_type: str, body: bytes) -> Tuple[str, str]:
    """Return (title, text) from a response body, by content type."""
    try:
        raw = body.decode("utf-8", errors="replace")
    except Exception:
        raw = body.decode("latin-1", errors="replace")
    if "html" in content_type:
        parser = _TextExtractor()
        try:
            parser.feed(raw)
        except Exception:
            return "", raw[:_MAX_TEXT_CHARS]
        return parser.title, parser.text()[:_MAX_TEXT_CHARS]
    return "", raw[:_MAX_TEXT_CHARS]


async def run(url: str) -> ToolResult:
    url = (url or "").strip()
    if not url:
        return ToolResult(ok=False, error="fetch_url: empty url")

    ok, reason = _validate(url)
    if not ok:
        return ToolResult(ok=False, error=f"fetch_url refused {url!r}: {reason}")

    current = url
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=20),
                                     follow_redirects=False) as http:
            resp = None
            for _ in range(_MAX_REDIRECTS + 1):
                resp = await http.get(current, headers={"User-Agent": "brainfoundry-fetch/1.0"})
                if resp.status_code in (301, 302, 303, 307, 308):
                    loc = resp.headers.get("location")
                    if not loc:
                        break
                    current = urljoin(current, loc)
                    ok, reason = _validate(current)      # re-validate each hop
                    if not ok:
                        return ToolResult(ok=False,
                                          error=f"fetch_url refused redirect to {current!r}: {reason}")
                    continue
                break
            else:
                return ToolResult(ok=False, error="fetch_url: too many redirects")

        resp.raise_for_status()
        content_type = (resp.headers.get("content-type", "") or "").split(";")[0].strip().lower()
        if content_type and not any(content_type.startswith(c) for c in _ALLOWED_CONTENT):
            return ToolResult(ok=False, error=f"fetch_url: unsupported content-type {content_type!r}")

        body = resp.content[:_MAX_BYTES]
        title, text = _extract(content_type, body)
        if not text.strip():
            return ToolResult(ok=False, error="fetch_url: no readable text on the page")
    except httpx.HTTPStatusError as e:
        return ToolResult(ok=False, error=f"fetch_url: HTTP {e.response.status_code} from {current}")
    except Exception as e:
        return ToolResult(ok=False, error=f"fetch_url failed: {e}")

    # Untrusted: a fetched page may carry injection — wrap it as reference data.
    block = {"title": title or current, "url": current, "snippet": text}
    content = safety.wrap_untrusted([block])
    return ToolResult(
        ok=True,
        content=content,
        provenance=[{"source": "fetch_url", "tool": "fetch_url", "trust": "untrusted",
                     "title": title or current, "url": current}],
        meta={"url": current, "title": title, "chars": len(text), "text": text},
    )


register(Tool(
    name="fetch_url",
    description=("Fetch and read a single web page by URL, returning its readable "
                 "text as untrusted reference data. Use after web_search to read "
                 "a specific result, or when the user gives a URL. http/https "
                 "only; internal/private addresses are refused."),
    tier=YELLOW,
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The http(s) URL to read."},
        },
        "required": ["url"],
    },
    run=run,
))
