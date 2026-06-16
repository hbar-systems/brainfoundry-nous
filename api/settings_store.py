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

# Map from tool-provider slug → env var name. Tools (web search, etc.) hold
# their keys separately from LLM provider keys so the two surfaces stay
# independent in the UI and in policy.
TOOL_ENV = {
    "brave": "BRAVE_SEARCH_API_KEY",
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
        # Tool keys (Brave, etc.) — same env-override pattern as provider keys.
        for provider, env_name in TOOL_ENV.items():
            value = data.get("tool_keys", {}).get(provider)
            if value and not os.environ.get(env_name):
                os.environ[env_name] = value
        # Google OAuth client (Gmail/Calendar/Drive) — sidecar-stored so the
        # operator can paste it in the UI instead of editing .env.
        gc = data.get("google_oauth_client", {})
        if gc.get("client_id") and not os.environ.get("GOOGLE_OAUTH_CLIENT_ID"):
            os.environ["GOOGLE_OAUTH_CLIENT_ID"] = gc["client_id"]
        if gc.get("client_secret") and not os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET"):
            os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = gc["client_secret"]


def get_email_account() -> Dict[str, Any]:
    """The configured IMAP email account (host/port/user/password). The password
    is returned here for the connector's use; never expose it via an API."""
    with _LOCK:
        return dict(_load().get("email_account", {}))


def set_email_account(host: str, port: int, user: str, password: Optional[str],
                      ssl: bool = True) -> None:
    """Store the IMAP email account. An empty host clears it. If password is
    None/empty an existing stored password is kept (so the operator can edit the
    host/user without re-typing the secret)."""
    with _LOCK:
        data = _load()
        if not host:
            data.pop("email_account", None)
            _save(data)
            return
        acct = data.get("email_account", {})
        acct["imap_host"] = host
        acct["imap_port"] = int(port or 993)
        acct["imap_user"] = user
        acct["imap_ssl"] = bool(ssl)
        if password:
            acct["imap_password"] = password
        data["email_account"] = acct
        _save(data)


def clear_email_account() -> None:
    with _LOCK:
        data = _load()
        data.pop("email_account", None)
        _save(data)


def get_mcp_servers() -> list:
    with _LOCK:
        return list(_load().get("mcp_servers", []))


def upsert_mcp_server(server: Dict[str, Any]) -> None:
    """Add or replace an MCP server entry (keyed by name)."""
    with _LOCK:
        data = _load()
        servers = [s for s in data.get("mcp_servers", []) if s.get("name") != server.get("name")]
        servers.append(server)
        data["mcp_servers"] = servers
        _save(data)


def remove_mcp_server(name: str) -> None:
    with _LOCK:
        data = _load()
        data["mcp_servers"] = [s for s in data.get("mcp_servers", []) if s.get("name") != name]
        _save(data)


def get_telegram() -> Dict[str, Any]:
    with _LOCK:
        return dict(_load().get("telegram", {}))


def set_telegram(info: Dict[str, Any]) -> None:
    with _LOCK:
        data = _load()
        data["telegram"] = {**data.get("telegram", {}), **info}
        _save(data)


def clear_telegram() -> None:
    with _LOCK:
        data = _load()
        data.pop("telegram", None)
        _save(data)


def get_calendar_ics() -> str:
    with _LOCK:
        return _load().get("calendar_ics_url", "")


def set_calendar_ics(url: str) -> None:
    with _LOCK:
        data = _load()
        if url:
            data["calendar_ics_url"] = url
        else:
            data.pop("calendar_ics_url", None)
        _save(data)


def set_google_client(client_id: Optional[str], client_secret: Optional[str]) -> None:
    """Persist the Google OAuth client id/secret in the sidecar and apply to the
    running process. Empty client_id clears both. The secret is never returned by
    any getter (see get_google_client_status)."""
    with _LOCK:
        data = _load()
        if not client_id:
            data.pop("google_oauth_client", None)
            os.environ.pop("GOOGLE_OAUTH_CLIENT_ID", None)
            os.environ.pop("GOOGLE_OAUTH_CLIENT_SECRET", None)
            _save(data)
            return
        gc = data.setdefault("google_oauth_client", {})
        gc["client_id"] = client_id
        os.environ["GOOGLE_OAUTH_CLIENT_ID"] = client_id
        if client_secret:
            gc["client_secret"] = client_secret
            os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = client_secret
        _save(data)


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


# ── Google OAuth tokens (Gmail + Calendar read-only) ────────────────────────
# The refresh token is a secret — stored in the sidecar like provider keys,
# never returned to any client. Only status (connected? which email?) is exposed.
def get_google_oauth() -> Dict[str, Any]:
    with _LOCK:
        return dict(_load().get("google_oauth", {}))


def set_google_oauth(info: Dict[str, Any]) -> None:
    with _LOCK:
        data = _load()
        data["google_oauth"] = info
        _save(data)


def clear_google_oauth() -> None:
    with _LOCK:
        data = _load()
        data.pop("google_oauth", None)
        _save(data)


def set_oauth_state(state: str) -> None:
    """One-shot CSRF state for the Google OAuth round-trip."""
    with _LOCK:
        data = _load()
        data["google_oauth_state"] = state
        _save(data)


def take_oauth_state() -> Optional[str]:
    """Read-and-clear the stored OAuth state (single use)."""
    with _LOCK:
        data = _load()
        state = data.pop("google_oauth_state", None)
        _save(data)
        return state


# ── max_tokens — operator-controlled response length cap ────────────────────
# The default 2048 is fine for chat-message-length answers but truncates
# longer outputs (multi-section explanations, code dumps, structured analyses)
# mid-sentence. Operator picks a higher cap when they want fuller answers;
# providers reject obviously-too-large values per their own quotas. We clamp
# to a sane window here so a misconfigured client can't request 1M and
# silently waste credits.
MAX_TOKENS_DEFAULT = 2048
MAX_TOKENS_MIN = 256
MAX_TOKENS_MAX = 65536


def get_max_tokens() -> int:
    """Operator-set max output tokens for chat responses. Falls back to the
    default when unset; clamps invalid stored values into the legal range."""
    v = _load().get("max_tokens")
    if not isinstance(v, int):
        return MAX_TOKENS_DEFAULT
    if v < MAX_TOKENS_MIN: return MAX_TOKENS_MIN
    if v > MAX_TOKENS_MAX: return MAX_TOKENS_MAX
    return v


def set_max_tokens(n: int) -> None:
    if not isinstance(n, int):
        raise ValueError(f"max_tokens must be int, got {type(n).__name__}")
    if n < MAX_TOKENS_MIN: n = MAX_TOKENS_MIN
    if n > MAX_TOKENS_MAX: n = MAX_TOKENS_MAX
    with _LOCK:
        data = _load()
        data["max_tokens"] = n
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


# ── Retrieval architecture — Track C3, "Mind Architecture" ───────────────────
# Which retrieval strategy /chat/rag uses to pull context from memory. The
# choice is persisted in the sidecar so it survives restarts and rebuilds
# (/app/runtime is volume-mounted). 'hybrid_routed' is described in the UI but
# not yet selectable — it needs a query router and is intentionally deferred.
RETRIEVAL_ARCHITECTURES = ("tiered", "flat", "layer_scoped")
# Flat (similarity-only) is the default: it retrieves documents that actually
# match the question. The older "tiered" default force-injected the same
# identity/context docs on every answer regardless of relevance — which made
# unrelated questions (e.g. "summarize my email") cite the same identity files
# every time. Operators can still choose tiered/layer_scoped in Settings.
DEFAULT_RETRIEVAL_ARCHITECTURE = "flat"


def get_retrieval_architecture() -> str:
    """The active retrieval architecture. Falls back to the default when unset
    or set to an unrecognized value."""
    arch = _load().get("retrieval_architecture")
    return arch if arch in RETRIEVAL_ARCHITECTURES else DEFAULT_RETRIEVAL_ARCHITECTURE


def set_retrieval_architecture(arch: str) -> None:
    if arch not in RETRIEVAL_ARCHITECTURES:
        raise ValueError(f"Unknown retrieval architecture: {arch!r}")
    with _LOCK:
        data = _load()
        data["retrieval_architecture"] = arch
        _save(data)


def get_layer_scope() -> list:
    """Memory layers the `layer_scoped` architecture restricts retrieval to.
    An empty list means 'all declared layers'."""
    scope = _load().get("layer_scope", [])
    return scope if isinstance(scope, list) else []


def set_layer_scope(layers: list) -> None:
    """Replace the layer_scoped subset. Each entry is a layer name string."""
    with _LOCK:
        data = _load()
        data["layer_scope"] = [str(x) for x in (layers or [])]
        _save(data)


# ── Greeting — the brain's auto-introduction shown when a chat opens ────────
# Operator-authored welcome message that surfaces as a faux assistant
# message[0] in the chat empty state (no session selected). Lets an org
# brain — hbar.university, hbar.health, etc. — introduce itself and its
# capabilities before the visitor has typed anything. Distinct from the
# first-run onboarding checklist (which targets the operator/owner) and
# from the persona system prompt (which is brain-internal context). The
# greeting is PUBLIC-FACING — what a visitor sees when they land in chat.

def get_greeting() -> str:
    """Operator-authored chat greeting. Empty string if unset (chat empty
    state then falls back to 'Your brain is ready')."""
    v = _load().get("greeting")
    return v if isinstance(v, str) else ""


def set_greeting(text: str) -> None:
    if not isinstance(text, str):
        raise ValueError(f"greeting must be str, got {type(text).__name__}")
    with _LOCK:
        data = _load()
        data["greeting"] = text.strip()
        _save(data)


# ── First-run onboarding ("become-you") ─────────────────────────────────────
# A brand-new brain runs the first-run experience (brain speaks first, live
# fact extraction, "your mind" panel) until the owner completes or dismisses it.
# The flag defaults False so a new brain reads as not-completed — but the
# onboarding gate ALSO requires a near-empty corpus (see api/onboarding/core.py
# is_fresh_brain), so an established brain never re-enters first-run regardless.
ONBOARDING_CORPUS_THRESHOLD_DEFAULT = 3


def get_onboarding_completed() -> bool:
    return bool(_load().get("onboarding_completed", False))


def set_onboarding_completed(done: bool) -> None:
    with _LOCK:
        data = _load()
        data["onboarding_completed"] = bool(done)
        _save(data)


# ── "Your mind" panel (persistent self-model surface) ───────────────────────
# The live fact panel is not onboarding-only: it is an always-on, dismissable,
# re-openable window into what the brain knows about its owner. This per-brain
# flag is the SHOWN/dismissed state AND the cost gate — per-turn fact extraction
# on the normal /chat/rag path runs ONLY when the panel is shown, so an
# established fleet brain incurs no extra model call until the owner opts in.
# Default OFF: zero cost/behaviour change for every already-running brain.
def get_mind_panel_shown() -> bool:
    return bool(_load().get("mind_panel_shown", False))


def set_mind_panel_shown(shown: bool) -> None:
    with _LOCK:
        data = _load()
        data["mind_panel_shown"] = bool(shown)
        _save(data)


def get_onboarding_corpus_threshold() -> int:
    """Chunk count at/below which a brain still counts as 'near-empty' for
    first-run. Tolerates a brain that auto-seeded a doc or two. Env-overridable."""
    v = _load().get("onboarding_corpus_threshold")
    if isinstance(v, int) and v >= 0:
        return v
    try:
        return int(os.getenv("ONBOARDING_CORPUS_THRESHOLD", ONBOARDING_CORPUS_THRESHOLD_DEFAULT))
    except (TypeError, ValueError):
        return ONBOARDING_CORPUS_THRESHOLD_DEFAULT


# ── Tools: web search (YELLOW tier) ─────────────────────────────────────────
# Web search is the brain's first external-capability tool. It is OFF by
# default. The operator turns it on (standing authorization for the YELLOW
# tier) and supplies a Brave Search API key under their own billing. Per
# message, the chat client still passes a `web_search` flag, so the operator
# also controls *when* the brain reaches the open web — enabling here only
# grants the capability, it does not make every message search.
WEB_SEARCH_BUDGET_DEFAULT = 1000
WEB_SEARCH_BUDGET_MIN = 0
WEB_SEARCH_BUDGET_MAX = 100000


def get_web_search_enabled() -> bool:
    return bool(_load().get("web_search_enabled", False))


def set_web_search_enabled(enabled: bool) -> None:
    with _LOCK:
        data = _load()
        data["web_search_enabled"] = bool(enabled)
        _save(data)


def get_agentic_tools_enabled() -> bool:
    """Agentic mode: let the model DECIDE when to call tools (native tool-use),
    instead of the deterministic per-message web toggle. Off by default — opt-in
    per brain so the safe deterministic path never regresses. Only takes effect
    on a model that supports native tool-calling (Anthropic / OpenAI-compatible);
    local Ollama models keep the manual path regardless."""
    return bool(_load().get("agentic_tools_enabled", False))


def set_agentic_tools_enabled(enabled: bool) -> None:
    with _LOCK:
        data = _load()
        data["agentic_tools_enabled"] = bool(enabled)
        _save(data)


def get_web_search_budget() -> int:
    """Operator-set monthly cap on web_search calls."""
    v = _load().get("web_search_budget")
    if not isinstance(v, int):
        return WEB_SEARCH_BUDGET_DEFAULT
    if v < WEB_SEARCH_BUDGET_MIN: return WEB_SEARCH_BUDGET_MIN
    if v > WEB_SEARCH_BUDGET_MAX: return WEB_SEARCH_BUDGET_MAX
    return v


def set_web_search_budget(n: int) -> None:
    if not isinstance(n, int):
        raise ValueError(f"web_search_budget must be int, got {type(n).__name__}")
    if n < WEB_SEARCH_BUDGET_MIN: n = WEB_SEARCH_BUDGET_MIN
    if n > WEB_SEARCH_BUDGET_MAX: n = WEB_SEARCH_BUDGET_MAX
    with _LOCK:
        data = _load()
        data["web_search_budget"] = n
        _save(data)


def get_tool_keys_masked() -> Dict[str, Optional[str]]:
    """Return {tool_provider: masked_tail_or_null} for UI display."""
    out: Dict[str, Optional[str]] = {}
    for provider, env_name in TOOL_ENV.items():
        raw = os.environ.get(env_name, "").strip()
        if not raw:
            out[provider] = None
        else:
            tail = raw[-4:] if len(raw) > 8 else "****"
            out[provider] = f"…{tail}"
    return out


def set_tool_key(provider: str, key: str) -> None:
    """Set or clear a tool API key (e.g. 'brave'). Empty string clears."""
    if provider not in TOOL_ENV:
        raise ValueError(f"Unknown tool provider: {provider}")
    env_name = TOOL_ENV[provider]
    with _LOCK:
        data = _load()
        keys = data.setdefault("tool_keys", {})
        if key:
            keys[provider] = key
            os.environ[env_name] = key
        else:
            keys.pop(provider, None)
            os.environ.pop(env_name, None)
        _save(data)


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
