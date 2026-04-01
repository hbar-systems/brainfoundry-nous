"""
providers.py — Multi-provider LLM routing for BrainFoundry Node

Bring Your Own Key: only providers with configured API keys are active.
Supported: Anthropic, OpenAI, Google Gemini, xAI Grok, Groq, OpenRouter, Ollama (local)

Groq and xAI and OpenRouter and Gemini all use OpenAI-compatible APIs,
so we use the openai SDK with a different base_url for each.
"""
import os
import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")

# --- Anthropic ---
try:
    import anthropic as _ant
    _anthropic_async = _ant.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY")) if os.getenv("ANTHROPIC_API_KEY") else None
except ImportError:
    _anthropic_async = None

# --- OpenAI-compatible clients ---
try:
    from openai import AsyncOpenAI

    _openai = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY")
    ) if os.getenv("OPENAI_API_KEY") else None

    _groq = AsyncOpenAI(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1"
    ) if os.getenv("GROQ_API_KEY") else None

    _xai = AsyncOpenAI(
        api_key=os.getenv("XAI_API_KEY"),
        base_url="https://api.x.ai/v1"
    ) if os.getenv("XAI_API_KEY") else None

    _openrouter = AsyncOpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    ) if os.getenv("OPENROUTER_API_KEY") else None

    _gemini = AsyncOpenAI(
        api_key=os.getenv("GOOGLE_API_KEY"),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    ) if os.getenv("GOOGLE_API_KEY") else None

except ImportError:
    _openai = _groq = _xai = _openrouter = _gemini = None


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
}


def get_available_models() -> list:
    """
    Return all models available given currently configured API keys + local Ollama.
    Cloud providers only appear if their API key is set.
    Ollama models are whatever is actually pulled on the node.
    """
    models = []

    if os.getenv("ANTHROPIC_API_KEY") and _anthropic_async:
        models += [{"name": m, "provider": "anthropic"} for m in PROVIDER_MODELS["anthropic"]]

    if os.getenv("OPENAI_API_KEY") and _openai:
        models += [{"name": m, "provider": "openai"} for m in PROVIDER_MODELS["openai"]]

    if os.getenv("GOOGLE_API_KEY") and _gemini:
        models += [{"name": m, "provider": "gemini"} for m in PROVIDER_MODELS["gemini"]]

    if os.getenv("XAI_API_KEY") and _xai:
        models += [{"name": m, "provider": "xai"} for m in PROVIDER_MODELS["xai"]]

    if os.getenv("GROQ_API_KEY") and _groq:
        models += [{"name": m, "provider": "groq"} for m in PROVIDER_MODELS["groq"]]

    if os.getenv("OPENROUTER_API_KEY") and _openrouter:
        models += [{"name": m, "provider": "openrouter"} for m in PROVIDER_MODELS["openrouter"]]

    # Always include local Ollama models (whatever is actually pulled)
    try:
        import requests as _req
        r = _req.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if r.ok:
            for m in r.json().get("models", []):
                models.append({"name": m["name"], "provider": "ollama", "size": m.get("size")})
    except Exception:
        pass

    return models


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
      anything else    → Ollama (local)
    """
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
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=120)) as http:
            system_msg = next((m["content"] for m in messages if m.get("role") == "system"), None)
            user_msgs = [m for m in messages if m.get("role") != "system"]
            payload = {"model": actual_model, "messages": user_msgs, "stream": False}
            if system_msg:
                payload["system"] = system_msg
            resp = await http.post(f"{OLLAMA_URL}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]
