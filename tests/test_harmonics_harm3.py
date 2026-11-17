"""
Created 2026-11-17 (ECON-2, economics delegated by hbar 2026-11-17). A local open-weights judge
gets its own Ollama call: temperature 0, num_predict = the judge's cap, a CPU-sized read
timeout, thinking off for qwen3; cloud judges keep providers.complete. No network.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api import harmonics as h
from api import providers


class _Resp:
    def __init__(self, content):
        self._c = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": self._c}}


def _capture(monkeypatch, answer='{"score": 0.8, "why": "fills the gap"}'):
    seen = {}
    import httpx

    def fake_post(url, json=None, timeout=None):
        seen.update(url=url, payload=json, timeout=timeout)
        return _Resp(answer)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(providers, "_resolve", lambda m: ("ollama", None, m))
    monkeypatch.setattr(providers, "ollama_url", lambda m=None: "http://ollama:11434")
    return seen


def test_local_judge_uses_its_own_call_temperature_zero(monkeypatch):
    seen = _capture(monkeypatch)
    out = h.judge("a checked correction", "the need", model="qwen2.5:7b")
    assert out == (0.8, "fills the gap", "qwen2.5:7b")
    p = seen["payload"]
    assert seen["url"] == "http://ollama:11434/api/chat"
    assert p["options"]["temperature"] == 0
    assert p["options"]["num_predict"] == 200
    assert "think" not in p
    assert p["keep_alive"] == "1m"
    assert p["messages"][0]["role"] == "system" and "rubric" not in p   # rubric travels as the system message
    assert seen["timeout"].read == h.JUDGE_TIMEOUT_S


def test_qwen3_judge_runs_with_thinking_off(monkeypatch):
    seen = _capture(monkeypatch)
    h.judge("x", "y", model="qwen3:4b")
    assert seen["payload"]["think"] is False


def test_local_judge_still_fails_closed(monkeypatch):
    _capture(monkeypatch, answer="I think this is pretty good")
    assert h.judge("x", "y", model="qwen2.5:7b") is None
    import httpx

    def boom(*a, **k):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(httpx, "post", boom)
    assert h.judge("x", "y", model="qwen2.5:7b") is None


def test_refused_small_judge_never_calls(monkeypatch):
    seen = _capture(monkeypatch)
    assert h.judge("x", "y", model="llama3.2:3b") is None
    assert seen == {}


def test_cloud_judge_keeps_providers_complete(monkeypatch):
    called = {}

    async def fake_complete(model, messages, max_tokens):
        called["model"] = model
        return '{"score": 0.5, "why": "partial"}'

    monkeypatch.setattr(providers, "_resolve", lambda m: ("anthropic", object(), m))
    monkeypatch.setattr(providers, "complete", fake_complete)
    assert h.judge("x", "y", model="claude-haiku-4-5")[0] == 0.5
    assert called["model"] == "claude-haiku-4-5"


def test_contributor_waits_for_a_cpu_judge():
    import inspect
    src = inspect.getsource(h.harmonics_contribute)
    assert "JUDGE_TIMEOUT_S + 60.0" in src and "timeout=60.0" not in src


def test_compose_passes_the_judge_settings_to_the_api():
    import re
    src = open(os.path.join(os.path.dirname(__file__), "..", "docker-compose.yml")).read()
    api = src[src.index("\n  api:"):src.index("\n  nodeos:")]
    for var in ("HARMONICS_JUDGE_MODEL", "HARMONICS_JUDGE_TIMEOUT", "HARMONICS_JUDGE_KEEP_ALIVE", "HARMONICS_NEED"):
        assert re.search(rf"- {var}=\$\{{{var}:-", api), var
