"""Compute view and agent shelf (2026-10-15).

The models route (api/compute.py, GET/POST /compute/models) must never return
key material, must mark each model local or closed with api/privacy.py's rule,
and must survive an endpoint that does not answer (offline, not an error). The
bridge side (scripts/cc/cc_extras.py) assigns endpoints to boxes and parses the
owner's shelf file: the shipped example parses clean, malformed entries are
left off the shelf and named.

No network: the HTTP getter, the provider resolver and the hosted list are
injected or monkeypatched.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from api import compute as cp  # noqa: E402
from api import providers as _p  # noqa: E402

SENTINEL = "sk-ant-SENTINEL-do-not-leak-4417"


def _extras():
    spec = importlib.util.spec_from_file_location("cc_extras_cs", ROOT / "scripts" / "cc" / "cc_extras.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["cc_extras_cs"] = m
    spec.loader.exec_module(m)
    return m


def _resolve(model):
    # Same name routing as providers._resolve with no local tags.
    if model.startswith("claude-"):
        return ("anthropic", None, model)
    if model.startswith(("gpt-", "o3-")):
        return ("openai_compat", None, model)
    if model.startswith("groq/"):
        return ("openai_compat", None, model[5:])
    return ("ollama", None, model)


TAGS = {
    "http://ollama:11434": {"models": [
        {"name": "llama3.2:3b", "size": 2019393189, "details": {"parameter_size": "3.2B", "family": "llama"}},
        {"name": "llama3.2:1b", "size": 1321098329},
        {"name": "gpt-oss:120b-cloud", "size": 384},
    ]},
    "http://100.84.0.9:11434": {"models": [{"name": "qwen3:30b", "size": 18556700761}]},
    "https://ollama.example.com": {"models": [{"name": "mistral:7b", "size": 4113301824}]},
}
PS = {"http://ollama:11434": {"models": [{"name": "llama3.2:3b"}]}}


def _get(url, timeout):
    base, _, path = url.rpartition("/api/")
    if base == "http://100.64.0.77:11434":
        raise ConnectionError("no route to host")
    table = TAGS if path == "tags" else PS
    if base not in table:
        if path == "ps":
            return {"models": []}
        raise ConnectionError("refused")
    return table[base]


ROUTED = [{"role": "box", "url": "http://ollama:11434"}]


def _snap(declared=None, routed=ROUTED, hosted=lambda: []):
    return cp.snapshot(declared, get=_get, resolve=_resolve, hosted=hosted, routed=routed, use_cache=False)


def _model(snap, name):
    for e in snap["endpoints"]:
        for m in e["models"]:
            if m["name"] == name:
                return e, m
    for h in snap["hosted"]:
        for m in h["models"]:
            if m["name"] == name:
                return h, m
    raise KeyError(name)


def test_box_models_listed_with_size_and_loaded():
    s = _snap()
    e, m = _model(s, "llama3.2:3b")
    assert e["online"] is True and e["routed"] is True and e["roles"] == ["box"]
    assert m["size"] == 2019393189 and m["parameter_size"] == "3.2B" and m["loaded"] is True
    assert _model(s, "llama3.2:1b")[1]["loaded"] is False
    assert s["summary"]["loaded"] == 1


def test_local_vs_closed_follows_privacy_rule():
    hosted = lambda: [{"name": "claude-opus-4-8", "provider": "anthropic"},
                      {"name": "groq/llama-3.3-70b-versatile", "provider": "groq"}]
    s = _snap([{"box": "zyro", "url": "http://100.84.0.9:11434"},
               {"box": "rented", "url": "https://ollama.example.com"}], hosted=hosted)
    assert _model(s, "llama3.2:3b")[1]["privacy"] == "local"
    assert _model(s, "gpt-oss:120b-cloud")[1]["privacy"] == "closed"     # Ollama forwards :cloud upstream
    assert _model(s, "qwen3:30b")[1]["privacy"] == "local"               # tailnet address, declared box
    assert _model(s, "mistral:7b")[1]["privacy"] == "closed"             # public DNS name: cannot tell who runs it
    assert _model(s, "claude-opus-4-8")[1]["privacy"] == "closed"
    assert _model(s, "groq/llama-3.3-70b-versatile")[1]["privacy"] == "closed"
    zyro = next(e for e in s["endpoints"] if "zyro" in e["boxes"])
    assert zyro["routed"] is False and zyro["roles"] == ["declared"]


def test_routed_model_closed_when_spoke_is_public():
    # The gate's rule: a routed model is local only if EVERY endpoint it could go to is the owner's.
    routed = ROUTED + [{"role": "spoke", "url": "https://ollama.example.com"}]
    s = _snap(routed=routed)
    assert _model(s, "llama3.2:3b")[1]["privacy"] == "closed"


def test_unreachable_endpoint_is_offline_not_error():
    s = _snap([{"box": "laptop", "url": "http://100.64.0.77:11434"}])
    e = next(x for x in s["endpoints"] if "laptop" in x["boxes"])
    assert e["online"] is False and e["models"] == [] and e["why"] == "ConnectionError"
    assert s["summary"]["online"] == 1 and s["summary"]["endpoints"] == 2


def test_bad_declared_urls_skipped_and_credentials_stripped():
    s = _snap([{"box": "a", "url": "file:///etc/passwd"}, {"box": "b", "url": "not a url"},
               {"box": "c", "url": "http://user:pw@100.84.0.9:11434/"}])
    urls = [e["url"] for e in s["endpoints"]]
    assert urls == ["http://ollama:11434", "http://100.84.0.9:11434"]
    assert "pw" not in json.dumps(s)


def test_declared_same_as_routed_merges():
    s = _snap([{"box": "brain", "url": "http://ollama:11434/"}])
    assert len(s["endpoints"]) == 1
    e = s["endpoints"][0]
    assert e["roles"] == ["box", "declared"] and e["boxes"] == ["brain"] and e["routed"] is True


def test_cache_returns_cached_flag(monkeypatch):
    cp.clear_cache()
    calls = []
    def get(url, timeout):
        calls.append(url)
        return _get(url, timeout)
    a = cp.snapshot(None, get=get, resolve=_resolve, hosted=lambda: [], routed=ROUTED)
    b = cp.snapshot(None, get=get, resolve=_resolve, hosted=lambda: [], routed=ROUTED)
    assert a["cached"] is False and b["cached"] is True and len(calls) == 2
    cp.clear_cache()


def test_route_never_returns_key_material(monkeypatch):
    from api import main as m
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    monkeypatch.setenv("OPENAI_API_KEY", SENTINEL + "-oa")
    monkeypatch.setattr(_p, "_anthropic_async", object())
    monkeypatch.setattr(_p, "_openai", object())
    monkeypatch.setattr(_p, "_fetch_provider_models", lambda provider: [])  # static lists, no network
    monkeypatch.setattr(_p, "_local_ollama_models", lambda: set())
    monkeypatch.setattr(_p, "OLLAMA_URL", "http://ollama:11434")
    monkeypatch.setattr(_p, "OLLAMA_SPOKE_URL", "")
    monkeypatch.setattr(cp, "_http_get_json", _get)
    cp.clear_cache()
    out = m.compute_models(api_key="k")
    body = json.dumps(out)
    assert SENTINEL not in body and "sk-ant" not in body and "SENTINEL" not in body
    provs = {h["provider"] for h in out["hosted"]}
    assert {"anthropic", "openai"} <= provs
    assert all(mm["privacy"] == "closed" for h in out["hosted"] for mm in h["models"])
    assert all(set(mm) == {"name", "privacy"} for h in out["hosted"] for mm in h["models"])
    cp.clear_cache()
    req = m.ComputeModelsRequest(endpoints=[{"box": "gone", "url": "http://100.64.0.77:11434"}])
    out2 = m.compute_models_with_boxes(req, api_key="k")
    assert SENTINEL not in json.dumps(out2)
    assert any(e["online"] is False for e in out2["endpoints"])
    cp.clear_cache()


def test_routes_require_api_key():
    from api import main as m
    seen = set()
    for r in m.app.routes:
        if getattr(r, "path", "") == "/compute/models":
            deps = [d.call for d in r.dependant.dependencies]
            assert m.get_api_key in deps, r.methods
            seen |= set(r.methods)
    assert {"GET", "POST"} <= seen


# ── bridge side ─────────────────────────────────────────────────────────────

FACTS = {"center": "brain", "boxes": [
    {"id": "brain", "ring": 0, "tailnet_ip": "100.97.0.1"},
    {"id": "laptop", "ring": 1, "tailnet_ip": "100.84.0.9"},
    {"id": "gpu", "ring": 1, "ollama": ["http://100.70.0.5:11434", ""]},
    {"id": "nobox"},
]}


def test_declared_ollama_and_compute_view():
    x = _extras()
    assert x.declared_ollama(FACTS) == [{"box": "gpu", "url": "http://100.70.0.5:11434"}]
    res = {"at": "t", "endpoints": [
        {"url": "http://ollama:11434", "roles": ["box"], "boxes": [], "routed": True, "online": True, "models": []},
        {"url": "http://100.84.0.9:11434", "roles": ["spoke"], "boxes": [], "routed": True, "online": False, "models": []},
        {"url": "http://100.70.0.5:11434", "roles": ["declared"], "boxes": ["gpu"], "routed": False, "online": True, "models": []},
    ], "hosted": [], "summary": {}}
    v = x.compute_view(FACTS, res)
    assert v["ok"] is True
    assert [e["boxes"] for e in v["endpoints"]] == [["brain"], ["laptop"], ["gpu"]]
    dead = x.compute_view(FACTS, None)
    assert dead["ok"] is False and dead["endpoints"] == [] and "BRAIN_API_KEY" in dead["error"]


def test_shelf_example_file_parses_clean():
    x = _extras()
    p = ROOT / "templates" / "agent-shelf.example.json"
    out = x.load_shelf(p)
    assert out["exists"] is True and out["errors"] == []
    assert len(out["agents"]) == 3
    for a in out["agents"]:
        assert {"id", "name", "legion", "mission", "tools", "runs_on", "permit"} <= set(a)
        assert "model" in a or "model_class" in a
    assert {l["id"] for l in out["legions"]} >= {a["legion"] for a in out["agents"]}


def test_shelf_rejects_malformed_entries():
    x = _extras()
    good = {"id": "ok", "name": "Ok", "legion": "l", "mission": "one line", "tools": ["read"],
            "model_class": "local-small", "runs_on": "brain", "permit": "any write"}
    bad = [
        "not an object",
        {**good, "id": "Bad Id"},
        {**good, "id": "ok"},                                       # duplicate
        {k: v for k, v in good.items() if k != "mission"} | {"id": "nomission"},
        {**good, "id": "twolines", "mission": "one\ntwo"},
        {**good, "id": "nomodel", "model_class": None},
        {**good, "id": "badtools", "tools": "read"},
        {**good, "id": "badcost", "cost": 5},
        {**good, "id": "nopermit", "permit": "  "},
    ]
    out = x.parse_shelf({"agents": [good] + bad})
    assert [a["id"] for a in out["agents"]] == ["ok"]
    assert len(out["errors"]) == len(bad)
    assert out["legions"] == [{"id": "l", "name": "l"}]
    assert x.parse_shelf({"agents": "x"})["errors"] and x.parse_shelf([])["agents"] == []


def test_shelf_missing_and_broken_file(tmp_path):
    x = _extras()
    miss = x.load_shelf(tmp_path / "shelf.json")
    assert miss["exists"] is False and miss["agents"] == [] and miss["rel"] == "ops/agent-shelf/shelf.json"
    (tmp_path / "shelf.json").write_text("{not json")
    broken = x.load_shelf(tmp_path / "shelf.json")
    assert broken["exists"] is True and broken["errors"] and broken["agents"] == []


def test_bridge_routes_exist():
    src = (ROOT / "scripts" / "cc" / "cc-bridge.py").read_text()
    assert 'route == "/compute"' in src and 'route == "/shelf"' in src
    assert '"/compute/models"' in src
