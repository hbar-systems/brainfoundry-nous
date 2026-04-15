"""
settings_store.py — runtime mutable settings for a brain.

Stores user-configured state (API keys, memory layers, active model) in a
sidecar JSON file at /app/runtime/settings.json. Values override matching
environment variables in-process, so changes take effect immediately without
a container restart.

Volume-mount /app/runtime to the host to persist across container rebuilds.
"""
import os
import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

SETTINGS_PATH = Path(os.getenv("SETTINGS_PATH", "/app/runtime/settings.json"))
_LOCK = threading.Lock()

# Map from provider slug → env var name. Single source of truth.
PROVIDER_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "xai": "XAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "together": "TOGETHER_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}


def _load() -> Dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except Exception:
        return {}


def _save(data: Dict[str, Any]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(SETTINGS_PATH)


def hydrate_env() -> None:
    """Called at startup. Push any sidecar-stored keys into os.environ so that
    provider clients created from env vars see them."""
    with _LOCK:
        data = _load()
        for provider, env_name in PROVIDER_ENV.items():
            value = data.get("keys", {}).get(provider)
            if value and not os.environ.get(env_name):
                os.environ[env_name] = value
        active_model = data.get("active_model")
        if active_model and not os.environ.get("OLLAMA_MODEL"):
            os.environ["OLLAMA_MODEL"] = active_model


def get_keys_masked() -> Dict[str, Optional[str]]:
    """Return {provider: masked_tail_or_null} for UI display. Never returns
    full secrets. Reads os.environ (which reflects both .env and sidecar)."""
    out: Dict[str, Optional[str]] = {}
    for provider, env_name in PROVIDER_ENV.items():
        raw = os.environ.get(env_name, "").strip()
        if not raw:
            out[provider] = None
        else:
            tail = raw[-4:] if len(raw) > 8 else "****"
            out[provider] = f"…{tail}"
    return out


def set_key(provider: str, key: str) -> None:
    """Set or clear an API key. Empty string clears. Writes sidecar + updates
    os.environ in-process so the change takes effect without restart."""
    if provider not in PROVIDER_ENV:
        raise ValueError(f"Unknown provider: {provider}")
    env_name = PROVIDER_ENV[provider]
    with _LOCK:
        data = _load()
        keys = data.setdefault("keys", {})
        if key:
            keys[provider] = key
            os.environ[env_name] = key
        else:
            keys.pop(provider, None)
            os.environ.pop(env_name, None)
        _save(data)


def get_active_model() -> Optional[str]:
    return os.environ.get("OLLAMA_MODEL") or os.environ.get("DEFAULT_MODEL")


def set_active_model(model: str) -> None:
    with _LOCK:
        data = _load()
        data["active_model"] = model
        os.environ["OLLAMA_MODEL"] = model
        _save(data)


def get_memory_layers() -> list:
    """Return user-defined memory layers. Empty list = blank slate."""
    data = _load()
    return data.get("memory_layers", [])


def set_memory_layers(layers: list) -> None:
    """Replace the full memory layers list. Each layer is {name, description}."""
    with _LOCK:
        data = _load()
        data["memory_layers"] = layers
        _save(data)


def get_layer_names() -> list:
    """Return just the layer name strings, for fast membership checks."""
    return [l.get("name") for l in get_memory_layers() if l.get("name")]


MEMORY_LAYER_PRESETS = [
    {
        "name": "identity",
        "description": "Who you are, so your brain speaks in your voice.",
    },
    {
        "name": "projects",
        "description": "What you're building or working on right now.",
    },
    {
        "name": "lifestyle",
        "description": "Your routines, preferences, and the texture of your days.",
    },
    {
        "name": "thinking",
        "description": "How you reason — notes, drafts, arguments you're still working out.",
    },
    {
        "name": "ethics",
        "description": "Principles and commitments — what your brain should refuse, favor, or question.",
    },
]
