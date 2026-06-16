"""
providers.py — Multi-provider LLM routing for BrainFoundry Node

Bring Your Own Key: only providers with configured API keys are active.
Supported: Anthropic, OpenAI, Google Gemini, xAI Grok, Groq, OpenRouter,
Together.ai, Mistral, Ollama (local).

Groq, xAI, OpenRouter, Gemini, Together, and Mistral all expose
OpenAI-compatible APIs, so we use the openai SDK with a different base_url.

Clients are (re)built from os.environ. Call rebuild_clients() after
mutating keys at runtime (e.g. via /settings/keys) so the change takes
effect without a container restart.
"""
import os
import time

import httpx

from api import settings_store

# Hydrate sidecar-stored keys into os.environ before client init.
settings_store.hydrate_env()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")

# ── Ollama generation budget (added 2026-06-08) ─────────────────────────────
# Ollama defaults num_ctx to 4096 and reserves nothing for output. With RAG, the
# prompt filled the whole window and generation was starved (empty output) or
# the slower 3b timed out (502). We set both explicitly: a larger context window
# AND a reserved generation budget (num_predict), so the answer always has room.
# num_ctx trades memory/CPU (KV cache grows with context) — 8192 is a safe
# middle on the CAX11; pair with the RAG context caps in main.py, don't rely on
# it alone. Env-overridable per deployment.
_OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
_OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "512"))


def _ollama_options(**overrides):
    """Shared ollama `options` — explicit context window + reserved generation
    budget. Overrides win (e.g. the tool loop passes its own num_predict)."""
    opts = {"num_ctx": _OLLAMA_NUM_CTX, "num_predict": _OLLAMA_NUM_PREDICT}
    opts.update({k: v for k, v in overrides.items() if v is not None})
    return opts


_anthropic_async = None
_openai = _groq = _xai = _openrouter = _gemini = _together = _mistral = None


def rebuild_clients() -> None:
    """(Re)build all provider clients from current os.environ.
    Safe to call at import time and after any key change."""
    global _anthropic_async, _openai, _groq, _xai, _openrouter, _gemini, _together, _mistral

    try:
        import anthropic as _ant
        _anthropic_async = _ant.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY")) if os.getenv("ANTHROPIC_API_KEY") else None
    except ImportError:
        _anthropic_async = None

    try:
        from openai import AsyncOpenAI

        _openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None
        _groq = AsyncOpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1") if os.getenv("GROQ_API_KEY") else None
        _xai = AsyncOpenAI(api_key=os.getenv("XAI_API_KEY"), base_url="https://api.x.ai/v1") if os.getenv("XAI_API_KEY") else None
        _openrouter = AsyncOpenAI(api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1") if os.getenv("OPENROUTER_API_KEY") else None
        _gemini = AsyncOpenAI(api_key=os.getenv("GOOGLE_API_KEY"), base_url="https://generativelanguage.googleapis.com/v1beta/openai/") if os.getenv("GOOGLE_API_KEY") else None
        _together = AsyncOpenAI(api_key=os.getenv("TOGETHER_API_KEY"), base_url="https://api.together.xyz/v1") if os.getenv("TOGETHER_API_KEY") else None
        _mistral = AsyncOpenAI(api_key=os.getenv("MISTRAL_API_KEY"), base_url="https://api.mistral.ai/v1") if os.getenv("MISTRAL_API_KEY") else None
    except ImportError:
        _openai = _groq = _xai = _openrouter = _gemini = _together = _mistral = None


rebuild_clients()


# Static model lists per provider (shown when key is present)
PROVIDER_MODELS = {
    "anthropic": [
        "claude-sonnet-4-6",
        "claude-opus-4-6",
        "claude-haiku-4-5",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "o3-mini",
    ],
    "gemini": [
        "gemini-2.0-flash",
        "gemini-1.5-pro",
    ],
    "xai": [
        "grok-2",
        "grok-beta",
    ],
    "groq": [
        "groq/llama-3.3-70b-versatile",
        "groq/llama-3.1-8b-instant",
        "groq/mixtral-8x7b-32768",
    ],
    "openrouter": [
        "openrouter/deepseek/deepseek-chat",
        "openrouter/qwen/qwen-2.5-72b-instruct",
        "openrouter/mistralai/mistral-large",
    ],
    "together": [
        "together/meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "together/deepseek-ai/DeepSeek-V3",
        "together/Qwen/Qwen2.5-72B-Instruct-Turbo",
    ],
    "mistral": [
        "mistral-large-latest",
        "mistral-small-latest",
    ],
}


# Per-provider live /models config. URL + auth-header pattern + name prefix.
# Each provider exposes an OpenAI-compatible /models endpoint returning
# {data: [{id, ...}, ...]} (Anthropic uses the same envelope). The `prefix`
# is prepended to returned ids so they route correctly through _resolve()
# below (groq/openrouter/together use prefix-stripped names internally).
#
# Live fetch lets BYOK pick up new releases (claude-opus-4-7, gpt-5, gemini
# 2.5, etc.) without code changes. A 2026-05-03 hot-fix that hardcoded a
# substring match in the UI dropdown rotted twice in three weeks; this
# closes that pattern at the source.
_PROVIDER_MODELS_ENDPOINTS = {
    "anthropic":  ("https://api.anthropic.com/v1/models",                  "anthropic", "",            "ANTHROPIC_API_KEY"),
    "openai":     ("https://api.openai.com/v1/models",                     "bearer",    "",            "OPENAI_API_KEY"),
    "gemini":     ("https://generativelanguage.googleapis.com/v1beta/openai/models", "bearer", "",     "GOOGLE_API_KEY"),
    "xai":        ("https://api.x.ai/v1/models",                           "bearer",    "",            "XAI_API_KEY"),
    "groq":       ("https://api.groq.com/openai/v1/models",                "bearer",    "groq/",       "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1/models",                  "bearer",    "openrouter/", "OPENROUTER_API_KEY"),
    "together":   ("https://api.together.xyz/v1/models",                   "bearer",    "together/",   "TOGETHER_API_KEY"),
    "mistral":    ("https://api.mistral.ai/v1/models",                     "bearer",    "",            "MISTRAL_API_KEY"),
}

# Per-provider live-list cache. Same TTL as Ollama's tag cache — model
# lineups change on the order of days, a 60s cache is cheap insurance
# against a chatty /models endpoint while still picking up new releases
# quickly. Empty list means "fetched and the provider returned nothing";
# absence means "not fetched yet, try again".
_provider_models_cache: dict = {}  # provider → {"at": ts, "models": [name, ...]}
_PROVIDER_MODELS_TTL = 60.0


def _fetch_provider_models(provider: str) -> list:
    """Return the live model-id list for a provider, prefixed for _resolve().
    Cached for _PROVIDER_MODELS_TTL seconds. Fail-soft on any error: returns
    [] so the caller can fall back to the static PROVIDER_MODELS list — a
    network blip or revoked key never empties the dropdown."""
    cfg = _PROVIDER_MODELS_ENDPOINTS.get(provider)
    if not cfg:
        return []
    url, auth_kind, prefix, env_key = cfg
    api_key = os.getenv(env_key)
    if not api_key:
        return []

    now = time.time()
    cached = _provider_models_cache.get(provider)
    if cached and now - cached["at"] < _PROVIDER_MODELS_TTL:
        return cached["models"]

    if auth_kind == "anthropic":
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    else:
        headers = {"Authorization": f"Bearer {api_key}"}

    try:
        import requests as _req
        r = _req.get(url, headers=headers, timeout=5)
        if not r.ok:
            return []
        data = r.json().get("data") or []
        names = [f"{prefix}{item['id']}" for item in data if isinstance(item, dict) and item.get("id")]
        _provider_models_cache[provider] = {"at": now, "models": names}
        return names
    except Exception:
        return []


def get_available_models() -> list:
    """
    Return all models available given currently configured API keys + local Ollama.
    Cloud providers only appear if their API key is set. Each provider's list
    is fetched live from its /models endpoint (cached 60s) — falls back to the
    static PROVIDER_MODELS dict if the fetch fails (revoked key, network blip,
    provider downtime). Ollama models are whatever is actually pulled on the node.
    """
    models = []

    def _append_provider(provider: str, env_key: str, client) -> None:
        if not os.getenv(env_key) or not client:
            return
        names = _fetch_provider_models(provider) or PROVIDER_MODELS.get(provider, [])
        models.extend({"name": n, "provider": provider} for n in names)

    _append_provider("anthropic",  "ANTHROPIC_API_KEY",  _anthropic_async)
    _append_provider("openai",     "OPENAI_API_KEY",     _openai)
    _append_provider("gemini",     "GOOGLE_API_KEY",     _gemini)
    _append_provider("xai",        "XAI_API_KEY",        _xai)
    _append_provider("groq",       "GROQ_API_KEY",       _groq)
    _append_provider("openrouter", "OPENROUTER_API_KEY", _openrouter)
    _append_provider("together",   "TOGETHER_API_KEY",   _together)
    _append_provider("mistral",    "MISTRAL_API_KEY",    _mistral)

    try:
        import requests as _req
        r = _req.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if r.ok:
            for m in r.json().get("models", []):
                models.append({"name": m["name"], "provider": "ollama", "size": m.get("size")})
    except Exception:
        pass

    return models


# Local-Ollama tag cache — keeps the per-call _resolve() check from hitting
# the Ollama API on every message. Short TTL; tags change only on model pull.
_ollama_tags_cache = {"at": 0.0, "tags": set()}
_OLLAMA_TAGS_TTL = 60.0


def _local_ollama_models() -> set:
    """Set of model tags on the local Ollama, cached briefly. Fail-soft: on
    any error returns the last good set (possibly empty) so the name-prefix
    routing below still applies."""
    now = time.time()
    if _ollama_tags_cache["tags"] and now - _ollama_tags_cache["at"] < _OLLAMA_TAGS_TTL:
        return _ollama_tags_cache["tags"]
    try:
        import requests as _req
        r = _req.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if r.ok:
            tags = {m["name"] for m in r.json().get("models", []) if m.get("name")}
            _ollama_tags_cache["at"] = now
            _ollama_tags_cache["tags"] = tags
            return tags
    except Exception:
        pass
    return _ollama_tags_cache["tags"]


def _resolve(model: str):
    """
    Return (client_type, client, actual_model_name) for a given model string.
    Model naming convention:
      claude-*         → Anthropic
      gpt-* / o1-* / o3-* / o4-*  → OpenAI
      gemini-*         → Google Gemini
      grok-*           → xAI
      groq/*           → Groq (prefix stripped before API call)
      openrouter/*     → OpenRouter (prefix stripped before API call)
      together/*       → Together.ai (prefix stripped before API call)
      mistral-*        → Mistral
      anything else    → Ollama (local)

    A model present on the local Ollama always wins over the name-prefix
    heuristics — OpenAI's open-weight models (e.g. gpt-oss:120b) carry a
    'gpt-' prefix but run locally, so they must route to Ollama, not the
    OpenAI API.
    """
    if model in _local_ollama_models():
        return ("ollama", None, model)
    if model.startswith("claude-"):
        return ("anthropic", _anthropic_async, model)
    elif model.startswith(("gpt-", "o1-", "o3-", "o4-")):
        return ("openai_compat", _openai, model)
    elif model.startswith("gemini-"):
        return ("openai_compat", _gemini, model)
    elif model.startswith("grok-"):
        return ("openai_compat", _xai, model)
    elif model.startswith("groq/"):
        return ("openai_compat", _groq, model[5:])
    elif model.startswith("openrouter/"):
        return ("openai_compat", _openrouter, model[11:])
    elif model.startswith("together/"):
        return ("openai_compat", _together, model[9:])
    elif model.startswith("mistral-"):
        return ("openai_compat", _mistral, model)
    else:
        return ("ollama", None, model)


def routes_to_ollama(model: str) -> bool:
    """True if `model` is served by the local Ollama (small fixed context window),
    False for cloud/BYOK frontier models (large context). Used by the RAG context
    budget so the tight, content-truncating cap is applied ONLY to the local
    model — a serious BYOK model is never dumbed down to fit a tiny one."""
    try:
        return _resolve(model)[0] == "ollama"
    except Exception:
        return False  # unknown -> treat as cloud (don't over-constrain)


# ── Default-model resolution (added 2026-06-08) ─────────────────────────────
# A local 1b/3b model is a degraded offline fallback, not a serious reasoner.
# When a brain has a BYOK cloud key configured, a fresh chat should default to a
# frontier reasoner — memory + RAG stay sovereign on the brain, only the
# reasoner is remote. This keeps the sovereignty story intact (the brain owns the
# corpus and retrieval) while giving real answer quality by default.
BYOK_DEFAULT_MODEL = os.getenv("BYOK_DEFAULT_MODEL", "claude-opus-4-8")
LOCAL_FALLBACK_MODEL = os.getenv("LOCAL_FALLBACK_MODEL", "llama3.2:3b")


def has_cloud_key() -> bool:
    """True if any cloud/BYOK provider client is configured (a key is present)."""
    return any(c is not None for c in (
        _anthropic_async, _openai, _gemini, _xai, _groq, _openrouter, _together, _mistral))


def _byok_default_model():
    """A frontier default matching whichever cloud provider is actually configured.
    Anthropic (BYOK_DEFAULT_MODEL) is preferred; otherwise fall back to a sensible
    model for the provider that IS keyed — so a brain with only an OpenAI/Gemini/etc
    key never defaults to an unreachable Anthropic model and fails every turn."""
    if _anthropic_async is not None:
        return BYOK_DEFAULT_MODEL
    if _openai is not None:
        return "gpt-4o"
    if _gemini is not None:
        return "gemini-2.0-flash"
    if _groq is not None:
        return "groq/llama-3.3-70b-versatile"
    if _openrouter is not None:
        return "openrouter/deepseek/deepseek-chat"
    if _together is not None:
        return "together/meta-llama/Llama-3.3-70B-Instruct-Turbo"
    if _mistral is not None:
        return "mistral-large-latest"
    if _xai is not None:
        return "grok-2"
    return None


def default_model() -> str:
    """The model an operator chat turn uses when the request names none.

    Order:
      1. the operator's explicit active-model choice (settings / OLLAMA_MODEL),
      2. an env-pinned DEFAULT_MODEL,
      3. a BYOK frontier reasoner IF any cloud key is configured (sovereign
         memory/RAG, remote reasoner),
      4. the local sovereign fallback.

    So a fresh brain with a key defaults to a serious model instead of the tiny
    local one; a brain with no key still works fully offline on the local model.
    Does NOT affect the public/unauth chat surface (that stays local by design —
    anonymous visitors must not spend the operator's BYOK key).
    """
    from api import settings_store
    chosen = settings_store.get_active_model() or os.getenv("DEFAULT_MODEL")
    # Guard against a stale/bogus ollama pin (e.g. OLLAMA_MODEL=oss-brain) that
    # names a local model which isn't actually installed — that would 404 at
    # serve time. If the pinned ollama model isn't present, ignore it and fall
    # through to the BYOK/local resolution below.
    if chosen and _resolve(chosen)[0] == "ollama" and chosen not in _local_ollama_models():
        chosen = None
    if chosen:
        return chosen
    byok = _byok_default_model()
    if byok:
        return byok
    return LOCAL_FALLBACK_MODEL


def cheap_extraction_model() -> str:
    """Cheapest capable model for structured per-turn fact extraction (the
    "your mind" panel). Extraction is a small, frequent, structured-output call,
    so it must NOT ride the operator's expensive default reasoner (e.g. Opus).
    Prefer a Haiku-class model on whatever cloud key is configured; with no cloud
    key, fall back to the brain's default (local, which is free). No env var — so
    nothing new to wire into compose."""
    if _anthropic_async is not None:
        return "claude-haiku-4-5"
    if _openai is not None:
        return "gpt-4o-mini"
    if _gemini is not None:
        return "gemini-2.0-flash"
    if _groq is not None:
        return "groq/llama-3.1-8b-instant"
    if _mistral is not None:
        return "mistral-small-latest"
    if _together is not None:
        return "together/meta-llama/Llama-3.3-70B-Instruct-Turbo"
    if _openrouter is not None:
        return "openrouter/deepseek/deepseek-chat"
    return default_model()


async def complete(model: str, messages: list, max_tokens: int = 2048) -> str:
    """
    Route a chat completion to the correct provider.
    Returns the assistant's reply as a plain string.
    Raises ValueError if the required API key is not configured.
    """
    client_type, client, actual_model = _resolve(model)

    if client_type == "anthropic":
        if not client:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        system_msg = next((m["content"] for m in messages if m.get("role") == "system"), None)
        user_msgs = [m for m in messages if m.get("role") != "system"]
        kwargs = {"system": system_msg} if system_msg else {}
        r = await client.messages.create(
            model=actual_model, max_tokens=max_tokens, messages=user_msgs, **kwargs
        )
        return r.content[0].text

    elif client_type == "openai_compat":
        if not client:
            raise ValueError(f"API key not configured for model: {model}")
        r = await client.chat.completions.create(
            model=actual_model, max_tokens=max_tokens, messages=messages
        )
        return r.choices[0].message.content

    else:  # ollama
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=180)) as http:
            system_msg = next((m["content"] for m in messages if m.get("role") == "system"), None)
            user_msgs = [m for m in messages if m.get("role") != "system"]
            payload = {"model": actual_model, "messages": user_msgs,
                       "stream": False, "options": _ollama_options()}
            if system_msg:
                payload["system"] = system_msg
            resp = await http.post(f"{OLLAMA_URL}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]


# ── Native model-driven tool use (agentic loop) ─────────────────────────────
# The model decides when to call a registered tool; each call runs through
# api.tools.dispatch (the tier gate — GREEN auto, YELLOW standing-auth, RED
# blocked) and the result is fed back so the model can continue. Supported on
# Anthropic, OpenAI-compatible, AND local Ollama models — federation must not
# require a cloud model (sovereignty). Capable local models (llama3.3:70b,
# qwen2.5:72b, mistral-nemo, …) tool-call well; a model that can't simply
# answers without emitting tool_calls, never an error.

_MAX_TOOL_ROUNDS = 4  # hard ceiling on tool round-trips per turn (loop guard)


def _anthropic_tool_specs(tools_spec: list) -> list:
    """Registry inventory -> Anthropic `tools` format."""
    return [
        {"name": t["name"], "description": t["description"],
         "input_schema": t["input_schema"]}
        for t in tools_spec
    ]


def _openai_tool_specs(tools_spec: list) -> list:
    """Registry inventory -> OpenAI function-calling `tools` format."""
    return [
        {"type": "function", "function": {
            "name": t["name"], "description": t["description"],
            "parameters": t["input_schema"]}}
        for t in tools_spec
    ]


def supports_native_tools(model: str) -> bool:
    """True when `model` can attempt native tool-calling. Anthropic + OpenAI-
    compatible need their client configured; **local Ollama models are allowed**
    — capable ones (llama3.3:70b, qwen2.5:72b, mistral-nemo, …) tool-call well,
    and a model that can't simply answers without emitting tool_calls (never an
    error). Federation must not require a cloud model — that would break the
    sovereignty thesis."""
    client_type, client, _ = _resolve(model)
    if client_type == "ollama":
        return True
    return client_type in ("anthropic", "openai_compat") and client is not None


def _event(result) -> dict:
    """Compact, UI/audit-facing record of one tool call from its ToolResult."""
    sources = [{"title": p.get("title"), "url": p.get("url")}
               for p in (getattr(result, "provenance", None) or []) if p.get("title") or p.get("url")][:10]
    # A short "what" for the UI trail: the peer for brain_call, else the query.
    meta = getattr(result, "meta", None) or {}
    detail = meta.get("target") or meta.get("query")
    return {
        "ok": bool(getattr(result, "ok", False)),
        "summary": (getattr(result, "error", None) if not getattr(result, "ok", False)
                    else f"{len(getattr(result, 'provenance', []) or [])} source(s)"),
        "detail": (str(detail)[:80] if detail else None),
        "sources": sources,
    }


async def _run_anthropic_tools(client, model, system, conv, tools, dispatch_fn,
                               max_tokens, max_rounds):
    """Anthropic tool-use loop. `conv` is the running message list (no system).
    `dispatch_fn(name, args) -> ToolResult`. Returns (text, events)."""
    events: list = []
    kwargs = {"system": system} if system else {}
    text_out = ""
    for _ in range(max_rounds):
        r = await client.messages.create(
            model=model, max_tokens=max_tokens, messages=conv, tools=tools, **kwargs)
        text_parts = [b.text for b in r.content if getattr(b, "type", None) == "text"]
        text_out = "".join(text_parts).strip()
        tool_uses = [b for b in r.content if getattr(b, "type", None) == "tool_use"]
        if not tool_uses:
            return text_out, events
        # Echo the assistant turn (all blocks) then answer each tool_use.
        conv.append({"role": "assistant", "content": r.content})
        results_blocks = []
        for tu in tool_uses:
            result = await dispatch_fn(tu.name, dict(tu.input or {}))
            ev = _event(result); ev["tool"] = tu.name; events.append(ev)
            payload = result.content if getattr(result, "ok", False) else f"ERROR: {result.error}"
            results_blocks.append({"type": "tool_result", "tool_use_id": tu.id,
                                   "content": payload})
        conv.append({"role": "user", "content": results_blocks})
    # Ran out of rounds — return whatever text we have (loop guard tripped).
    return text_out, events


async def _run_openai_tools(client, model, conv, tools, dispatch_fn,
                            max_tokens, max_rounds):
    """OpenAI-compatible function-calling loop. `conv` includes the system
    message. Returns (text, events)."""
    import json as _json
    events: list = []
    text_out = ""
    for _ in range(max_rounds):
        r = await client.chat.completions.create(
            model=model, max_tokens=max_tokens, messages=conv, tools=tools)
        msg = r.choices[0].message
        text_out = (msg.content or "").strip()
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            return text_out, events
        conv.append({"role": "assistant", "content": msg.content or "",
                     "tool_calls": [tc.model_dump() if hasattr(tc, "model_dump") else tc
                                    for tc in tool_calls]})
        for tc in tool_calls:
            try:
                args = _json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            result = await dispatch_fn(tc.function.name, args)
            ev = _event(result); ev["tool"] = tc.function.name; events.append(ev)
            payload = result.content if getattr(result, "ok", False) else f"ERROR: {result.error}"
            conv.append({"role": "tool", "tool_call_id": tc.id, "content": payload})
    return text_out, events


async def _run_ollama_tools(model, conv, tools, dispatch_fn, max_tokens, max_rounds):
    """Local-model (Ollama) tool-calling loop. Ollama's /api/chat speaks the
    OpenAI tool shape — `tools` in, `message.tool_calls` out (arguments arrive
    as an object, occasionally a JSON string; no call id). Capable local models
    (llama3.3:70b, qwen2.5:72b, mistral-nemo, …) drive this well; a tiny 3b will
    just rarely emit tool_calls and answer directly — never an error. This is
    the sovereign path: federation with no cloud dependency."""
    import json as _json
    events: list = []
    text_out = ""
    async with httpx.AsyncClient(timeout=httpx.Timeout(15, read=300)) as http:
        for _ in range(max_rounds):
            payload = {"model": model, "messages": conv, "tools": tools,
                       "stream": False, "options": _ollama_options(num_predict=max_tokens)}
            resp = await http.post(f"{OLLAMA_URL}/api/chat", json=payload)
            resp.raise_for_status()
            msg = (resp.json() or {}).get("message", {}) or {}
            text_out = (msg.get("content") or "").strip()
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                return text_out, events
            conv.append({"role": "assistant", "content": msg.get("content") or "",
                         "tool_calls": tool_calls})
            for tc in tool_calls:
                fn = tc.get("function", {}) or {}
                name = fn.get("name")
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        args = _json.loads(args or "{}")
                    except Exception:
                        args = {}
                elif not isinstance(args, dict):
                    args = {}
                result = await dispatch_fn(name, args)
                ev = _event(result); ev["tool"] = name; events.append(ev)
                content = result.content if getattr(result, "ok", False) else f"ERROR: {result.error}"
                conv.append({"role": "tool", "content": content})
    return text_out, events


async def complete_with_tools(model: str, messages: list, tools_spec: list,
                              dispatch_fn, max_tokens: int = 2048,
                              max_rounds: int = _MAX_TOOL_ROUNDS) -> dict:
    """Agentic completion: let `model` call the tools in `tools_spec`, running
    each through `dispatch_fn` (the tier-gated dispatcher). Returns
    {"text", "tool_events"}. Raises ValueError if the model can't do native
    tools (caller should fall back to plain complete())."""
    client_type, client, actual_model = _resolve(model)
    if client_type == "anthropic":
        if not client:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        system_msg = next((m["content"] for m in messages if m.get("role") == "system"), None)
        conv = [m for m in messages if m.get("role") != "system"]
        text, events = await _run_anthropic_tools(
            client, actual_model, system_msg, conv, _anthropic_tool_specs(tools_spec),
            dispatch_fn, max_tokens, max_rounds)
        return {"text": text, "tool_events": events}
    elif client_type == "openai_compat":
        if not client:
            raise ValueError(f"API key not configured for model: {model}")
        conv = list(messages)
        text, events = await _run_openai_tools(
            client, actual_model, conv, _openai_tool_specs(tools_spec),
            dispatch_fn, max_tokens, max_rounds)
        return {"text": text, "tool_events": events}
    else:  # ollama (local) — sovereign tool-calling, no cloud dependency
        conv = list(messages)
        text, events = await _run_ollama_tools(
            actual_model, conv, _openai_tool_specs(tools_spec),
            dispatch_fn, max_tokens, max_rounds)
        return {"text": text, "tool_events": events}


async def stream(model: str, messages: list, max_tokens: int = 2048):
    """
    Async generator that yields text chunks from the model.
    Routes to the correct provider based on model name prefix.
    Raises ValueError if the required API key is not configured.
    """
    import json as _json

    client_type, client, actual_model = _resolve(model)

    if client_type == "anthropic":
        if not client:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        system_msg = next((m["content"] for m in messages if m.get("role") == "system"), None)
        user_msgs = [m for m in messages if m.get("role") != "system"]
        kwargs = {"system": system_msg} if system_msg else {}
        async with client.messages.stream(
            model=actual_model, max_tokens=max_tokens, messages=user_msgs, **kwargs
        ) as s:
            async for text in s.text_stream:
                yield text

    elif client_type == "openai_compat":
        if not client:
            raise ValueError(f"API key not configured for model: {model}")
        stream_resp = await client.chat.completions.create(
            model=actual_model, max_tokens=max_tokens, messages=messages, stream=True
        )
        async for chunk in stream_resp:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    else:  # ollama
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=300)) as http:
            system_msg = next((m["content"] for m in messages if m.get("role") == "system"), None)
            user_msgs = [m for m in messages if m.get("role") != "system"]
            payload = {"model": actual_model, "messages": user_msgs,
                       "stream": True, "options": _ollama_options()}
            if system_msg:
                payload["system"] = system_msg
            async with http.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        data = _json.loads(line)
                        text = data.get("message", {}).get("content", "")
                        if text:
                            yield text
