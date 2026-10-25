"""The Local seat (2026-10-25): the Codex seat's machinery pointed at a self-hosted model.

Same process, same guarantees as scripts/cc/cc_codex.py: `codex exec --json` as the hands user,
read-only sandbox, approval_policy never, web search off, no user config, no rules, the same
command-line check. The only change is where the model lives: an OpenAI-compatible endpoint you
run (a GPU pod on the tailnet, or a box of your own), named by CC_LOCAL_BASE_URL in the bridge's
env file. The provider reaches Codex through `-c` overrides only (nothing is written to
~/.codex/config.toml, which `--ignore-user-config` would skip anyway):

    model_provider="local"
    model_providers.local.name="local"
    model_providers.local.base_url=<CC_LOCAL_BASE_URL>
    model_providers.local.wire_api="chat"
    model_providers.local.env_key="CC_LOCAL_API_KEY"

Assumption (no Codex binary was present to check against when this was written): these are the
custom-provider keys Codex 0.162 documents (name, base_url, env_key, wire_api "chat" or
"responses"). `chat` is the Chat Completions wire that vLLM, llama.cpp server and Ollama speak.
If a later Codex drops `chat`, the turn fails with Codex's own error, shown as a plain sentence;
nothing falls back to another seat.

The key (CC_LOCAL_API_KEY) is read from the bridge's environment, handed to the Codex process as
an environment variable only (never an argument, so never in `ps` or sudo's log), and is the one
name this seat adds to the minimal environment. The shell commands Codex runs get
`shell_environment_policy.inherit="core"`, which leaves it out.

Fail closed: no base URL, or no answer from GET <base>/models within 5 s, and the turn is refused
with one plain sentence. Pure helpers here; the bridge runs the process.
"""
from __future__ import annotations

import re
import urllib.request
from urllib.parse import urlsplit

import cc_codex

MODE = cc_codex.MODE
LABEL = "Local (read-only)"
KEY_VAR = "CC_LOCAL_API_KEY"
PROVIDER = "local"
PROBE_S = 5

NO_ENDPOINT = "local model: no endpoint configured"
NOT_ANSWERING = "local model: endpoint not answering, is the pod up?"


def settings(environ: dict) -> dict:
    """{"base", "model", "key"} from the bridge's environment; base is "" unless a clean http(s) URL
    (no credentials in it, no quotes or spaces that could break out of a -c value)."""
    base = (environ.get("CC_LOCAL_BASE_URL") or "").strip().rstrip("/")
    ok = False
    if base and not re.search(r"[\s\"'\\]", base):
        u = urlsplit(base)
        ok = u.scheme in ("http", "https") and bool(u.hostname) and "@" not in u.netloc
    return {"base": base if ok else "", "model": (environ.get("CC_LOCAL_MODEL") or "").strip(),
            "key": (environ.get("CC_LOCAL_API_KEY") or "").strip()}


def host(base: str) -> str:
    u = urlsplit(base)
    return (u.hostname or "") + (f":{u.port}" if u.port else "")


def overrides(base: str) -> list[str]:
    """The provider as `-c` pairs. Values are TOML basic strings; the key is not among them."""
    return ["-c", f'model_provider="{PROVIDER}"',
            "-c", f'model_providers.{PROVIDER}.name="{PROVIDER}"',
            "-c", f'model_providers.{PROVIDER}.base_url="{base}"',
            "-c", f'model_providers.{PROVIDER}.wire_api="chat"',
            "-c", f'model_providers.{PROVIDER}.env_key="{KEY_VAR}"']


def build_cmd(bin_path: str, cwd: str, st: dict, session_id: str | None = None) -> list[str]:
    """The Codex seat's command line plus the provider. Raises cc_codex.Unsafe if it would loosen
    the seat or carry the key."""
    cmd = cc_codex.build_cmd(bin_path, cwd, session_id, st["model"], extra=overrides(st["base"]))
    if st.get("key") and any(st["key"] in a for a in cmd):
        raise cc_codex.Unsafe("the key is on the command line")
    return cmd


def env(base: dict, key: str) -> dict:
    """Codex's minimal environment plus exactly one name, the endpoint key (a placeholder when the
    endpoint takes none, since Codex insists the variable exists)."""
    out = cc_codex.env(base)
    out[KEY_VAR] = key or "none"
    return out


def probe(st: dict, opener=None, timeout: float = PROBE_S) -> str | None:
    """None when GET <base>/models answers 2xx within `timeout`; else the refusal sentence."""
    if not st.get("base"):
        return NO_ENDPOINT
    req = urllib.request.Request(st["base"] + "/models", method="GET")
    if st.get("key"):
        req.add_header("Authorization", "Bearer " + st["key"])
    try:
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as r:
            code = getattr(r, "status", 200)
            return None if 200 <= int(code) < 300 else NOT_ANSWERING
    except Exception:  # noqa: BLE001  (any failure to answer is the same sentence; the cause stays off the page)
        return NOT_ANSWERING


def status(environ: dict, opener=None, live: bool = True) -> dict:
    """The page's state: {"configured","reachable","model","host","mode","label","line"}; never the key."""
    st = settings(environ)
    out = {"configured": bool(st["base"]), "reachable": False, "model": st["model"] or None,
           "host": host(st["base"]) if st["base"] else None, "mode": MODE, "label": LABEL}
    if not live:   # /cc/health: configuration only, never a 5 s wait on a pod that may be down
        out["reachable"] = None
        out["line"] = f"local: {st['model'] or 'default model'} at {out['host']}" if st["base"] else NO_ENDPOINT
        return out
    no = probe(st, opener)
    out["reachable"] = no is None
    out["line"] = no or f"local: {st['model'] or 'default model'} at {out['host']}"
    if no:
        out["reason"] = no
    return out
