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
            payload = {"model": actual_model, "messages": user_msgs, "stream": False}
            if system_msg:
                payload["system"] = system_msg
            resp = await http.post(f"{OLLAMA_URL}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]


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
            payload = {"model": actual_model, "messages": user_msgs, "stream": True}
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
