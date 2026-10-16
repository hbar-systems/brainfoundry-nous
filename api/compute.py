"""api/compute.py — which models live on which machine, read live (2026-10-15).

The compute view answers one question for the owner: which reasoners exist,
where they run, and which of them may read local-only memory.

  Ollama endpoints  the box's own (OLLAMA_URL), the spoke (OLLAMA_SPOKE_URL)
                    and any endpoint the owner declares for a box in the box
                    map (the bridge passes those in). Each is read live:
                    /api/tags for what is pulled, /api/ps for what is loaded,
                    with a short timeout. An endpoint that does not answer is
                    `online: false`, never an error.
  Hosted providers  the models the configured keys unlock (api.providers.
                    hosted_models): names only, never a key or a masked key.

Every model is marked `local` or `closed` with api/privacy.py's rule:
  - an endpoint the brain routes chat to (box, spoke): reasoner_is_local(),
    the same check the memory gate applies to a turn;
  - an endpoint the brain does not route to (declared in the box map only):
    model_is_local_at(), the same host rule for that one endpoint;
  - a hosted model: reasoner_is_local() on its name, which is closed unless the
    name resolves to an owner-run Ollama.
Only `local` models may read local-only memory.

The snapshot is cached briefly (COMPUTE_CACHE_SECONDS, default 20) per set of
declared endpoints, so a page refreshing every minute does not fan out probes.
"""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from api import privacy as _privacy

PROBE_SECONDS = float(os.getenv("COMPUTE_PROBE_SECONDS", "1.5"))
CACHE_SECONDS = float(os.getenv("COMPUTE_CACHE_SECONDS", "20"))
MAX_DECLARED = 16

LOCAL = "local"
CLOSED = "closed"

RULE = ("local: answered on hardware the owner controls (an owner-network Ollama, not a :cloud model); "
        "may read local-only memory. closed: a hosted API or anything in doubt; reads open memory only.")

_cache: Dict[tuple, Dict[str, Any]] = {}
_lock = threading.Lock()


def clean_url(url: Any) -> Optional[str]:
    """scheme://host[:port][/path] for an http(s) URL, without credentials, query
    or fragment. None for anything else (the endpoint is then skipped)."""
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        u = urlparse(url.strip())
        host = u.hostname
        port = u.port
    except Exception:
        return None
    if u.scheme not in ("http", "https") or not host:
        return None
    netloc = f"[{host}]" if ":" in host else host
    if port:
        netloc += f":{port}"
    path = (u.path or "").rstrip("/")
    return f"{u.scheme}://{netloc}{path}"


def _http_get_json(url: str, timeout: float):
    import requests as _req
    r = _req.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def probe(url: str, *, get: Optional[Callable] = None, timeout: float = PROBE_SECONDS) -> Dict[str, Any]:
    """Read one Ollama endpoint. Never raises: unreachable -> online False."""
    get = get or _http_get_json
    try:
        tags = get(f"{url}/api/tags", timeout) or {}
    except Exception as e:
        return {"online": False, "models": [], "why": type(e).__name__}
    loaded: Optional[set] = None
    try:
        ps = get(f"{url}/api/ps", timeout) or {}
        loaded = {m.get("name") or m.get("model") for m in ps.get("models") or [] if isinstance(m, dict)}
    except Exception:
        loaded = None  # tags answered, ps did not: loaded state unknown
    models = []
    for m in (tags.get("models") or []) if isinstance(tags, dict) else []:
        if not isinstance(m, dict) or not m.get("name"):
            continue
        d = m.get("details") if isinstance(m.get("details"), dict) else {}
        models.append({
            "name": str(m["name"]),
            "size": m.get("size") if isinstance(m.get("size"), (int, float)) else None,
            "parameter_size": d.get("parameter_size"),
            "quantization": d.get("quantization_level"),
            "family": d.get("family"),
            "loaded": (m["name"] in loaded) if loaded is not None else None,
        })
    return {"online": True, "models": models, "why": None}


def _endpoint_list(declared: Optional[List[Dict[str, Any]]], routed: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    eps: List[Dict[str, Any]] = []
    by_url: Dict[str, Dict[str, Any]] = {}
    for r in routed:
        e = {"url": r["url"], "roles": [r["role"]], "boxes": [], "routed": True}
        eps.append(e)
        by_url[r["url"]] = e
    for d in (declared or [])[:MAX_DECLARED]:
        if not isinstance(d, dict):
            continue
        u = clean_url(d.get("url"))
        box = str(d.get("box") or "").strip()[:64]
        if not u:
            continue
        e = by_url.get(u)
        if e is None:
            e = {"url": u, "roles": [], "boxes": [], "routed": False}
            eps.append(e)
            by_url[u] = e
        if "declared" not in e["roles"]:
            e["roles"].append("declared")
        if box and box not in e["boxes"]:
            e["boxes"].append(box)
    return eps


def snapshot(declared: Optional[List[Dict[str, Any]]] = None, *, get: Optional[Callable] = None,
             resolve: Optional[Callable] = None, hosted: Optional[Callable] = None,
             routed: Optional[List[Dict[str, str]]] = None, use_cache: bool = True) -> Dict[str, Any]:
    """The compute view. `get`, `resolve`, `hosted` and `routed` are injectable
    for tests; by default they are the real HTTP getter, providers._resolve,
    providers.hosted_models and the brain's OLLAMA_URL / OLLAMA_SPOKE_URL."""
    if routed is None:
        from api import providers as _p
        routed = [{"role": "box", "url": clean_url(_p.OLLAMA_URL)}]
        if _p.OLLAMA_SPOKE_URL:
            routed.append({"role": "spoke", "url": clean_url(_p.OLLAMA_SPOKE_URL)})
        routed = [r for r in routed if r["url"]]
    key = (tuple((r["role"], r["url"]) for r in routed),
           tuple(sorted((str(d.get("box") or ""), str(d.get("url") or "")) for d in (declared or []) if isinstance(d, dict))))
    now = time.time()
    if use_cache:
        with _lock:
            hit = _cache.get(key)
            if hit and now - hit["_t"] < CACHE_SECONDS:
                return {**hit["v"], "cached": True}

    eps = _endpoint_list(declared, routed)
    routed_urls = [r["url"] for r in routed]
    if resolve is None:
        from api import providers as _p
        resolve = _p._resolve

    def is_local_routed(name: str) -> bool:
        return _privacy.reasoner_is_local(name, resolve=resolve, ollama_urls=routed_urls)

    with ThreadPoolExecutor(max_workers=max(1, min(8, len(eps)))) as ex:
        results = list(ex.map(lambda e: probe(e["url"], get=get), eps)) if eps else []

    for e, res in zip(eps, results):
        e["online"] = res["online"]
        e["why"] = res["why"]
        e["owner_host"] = _privacy.is_owner_host(e["url"])
        for m in res["models"]:
            local = is_local_routed(m["name"]) if e["routed"] else _privacy.model_is_local_at(m["name"], e["url"])
            m["privacy"] = LOCAL if local else CLOSED
        e["models"] = res["models"]

    hosted_rows: Dict[str, List[Dict[str, str]]] = {}
    try:
        if hosted is None:
            from api import providers as _p
            hosted = _p.hosted_models
        for h in hosted() or []:
            name, prov = str(h.get("name") or ""), str(h.get("provider") or "")
            if not name or not prov:
                continue
            hosted_rows.setdefault(prov, []).append(
                {"name": name, "privacy": LOCAL if is_local_routed(name) else CLOSED})
    except Exception:
        hosted_rows = {}
    hosted_list = [{"provider": p, "models": ms} for p, ms in hosted_rows.items()]

    all_models = [m for e in eps for m in e["models"]] + [m for h in hosted_list for m in h["models"]]
    out = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cached": False,
        "rule": RULE,
        "endpoints": eps,
        "hosted": hosted_list,
        "summary": {
            "endpoints": len(eps),
            "online": sum(1 for e in eps if e["online"]),
            "local": sum(1 for m in all_models if m["privacy"] == LOCAL),
            "closed": sum(1 for m in all_models if m["privacy"] == CLOSED),
            "loaded": sum(1 for e in eps for m in e["models"] if m.get("loaded")),
        },
    }
    if use_cache:
        with _lock:
            _cache[key] = {"_t": now, "v": out}
    return out


def clear_cache() -> None:
    with _lock:
        _cache.clear()
