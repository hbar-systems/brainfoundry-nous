"""
Tests for native model-driven tool-calling (api/providers.py agentic loop) +
the tool registry tiers. The provider API clients are faked, so no key/network
is touched — we exercise the loop logic: a tool_use round dispatches, feeds the
result back, records an event, and the loop terminates on a text answer.
"""
import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api import providers  # noqa: E402
from api import tools  # noqa: E402
from api.tools import ToolResult  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


# ── schema converters (pure) ─────────────────────────────────────────────────

_SPEC = [{"name": "web_search", "description": "search the web",
          "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}}]


def test_anthropic_tool_specs():
    out = providers._anthropic_tool_specs(_SPEC)
    assert out == [{"name": "web_search", "description": "search the web",
                    "input_schema": _SPEC[0]["input_schema"]}]


def test_openai_tool_specs():
    out = providers._openai_tool_specs(_SPEC)
    assert out[0]["type"] == "function"
    assert out[0]["function"]["name"] == "web_search"
    assert out[0]["function"]["parameters"] == _SPEC[0]["input_schema"]


# ── registry tiers ───────────────────────────────────────────────────────────

def test_search_memory_registered_green():
    t = tools.get("search_memory")
    assert t is not None and t.tier == tools.GREEN


def test_web_search_registered_yellow():
    t = tools.get("web_search")
    assert t is not None and t.tier == tools.YELLOW


# ── fake Anthropic client ────────────────────────────────────────────────────

def _txt(s):
    return SimpleNamespace(type="text", text=s)


def _use(name, inp, id="t1"):
    return SimpleNamespace(type="tool_use", name=name, input=inp, id=id)


class _FakeAnthropic:
    """messages.create returns the queued responses in order."""
    def __init__(self, responses):
        self._it = iter(responses)
        self.calls = []
        self.messages = self

    async def create(self, **kw):
        self.calls.append(kw)
        return next(self._it)


def test_anthropic_loop_dispatches_then_answers():
    client = _FakeAnthropic([
        SimpleNamespace(content=[_use("web_search", {"query": "x"})], stop_reason="tool_use"),
        SimpleNamespace(content=[_txt("the answer")], stop_reason="end_turn"),
    ])
    seen = {}

    async def disp(name, args):
        seen["name"] = name; seen["args"] = args
        return ToolResult(ok=True, content="TOOL OUTPUT", provenance=[{"title": "T", "url": "u"}])

    conv = [{"role": "user", "content": "hi"}]
    text, events = _run(providers._run_anthropic_tools(
        client, "claude-x", None, conv, [], disp, 100, 4))

    assert text == "the answer"
    assert seen == {"name": "web_search", "args": {"query": "x"}}
    assert len(events) == 1 and events[0]["tool"] == "web_search" and events[0]["ok"] is True
    assert len(client.calls) == 2                      # tool round + final round
    # conv grew by the assistant turn + the tool_result user turn
    assert conv[-1]["role"] == "user"
    assert conv[-1]["content"][0]["type"] == "tool_result"
    assert conv[-1]["content"][0]["content"] == "TOOL OUTPUT"


def test_anthropic_loop_feeds_error_back():
    client = _FakeAnthropic([
        SimpleNamespace(content=[_use("web_search", {"query": "x"})], stop_reason="tool_use"),
        SimpleNamespace(content=[_txt("done")], stop_reason="end_turn"),
    ])

    async def disp(name, args):
        return ToolResult(ok=False, error="not enabled")

    conv = [{"role": "user", "content": "hi"}]
    text, events = _run(providers._run_anthropic_tools(
        client, "claude-x", None, conv, [], disp, 100, 4))
    assert events[0]["ok"] is False and "not enabled" in events[0]["summary"]
    assert conv[-1]["content"][0]["content"].startswith("ERROR: not enabled")


def test_anthropic_loop_respects_max_rounds():
    # Model keeps asking for tools forever; loop must stop at max_rounds.
    always_tool = SimpleNamespace(content=[_use("web_search", {"query": "x"})], stop_reason="tool_use")

    class _Loop:
        def __init__(self): self.n = 0; self.messages = self
        async def create(self, **kw): self.n += 1; return always_tool

    client = _Loop()

    async def disp(name, args):
        return ToolResult(ok=True, content="r", provenance=[])

    _run(providers._run_anthropic_tools(client, "claude-x", None, [{"role": "user", "content": "hi"}], [], disp, 100, 3))
    assert client.n == 3                                # exactly max_rounds calls, no infinite loop


# ── fake OpenAI-compatible client ────────────────────────────────────────────

class _FakeOpenAI:
    def __init__(self, responses):
        self._it = iter(responses)
        self.chat = self
        self.completions = self

    async def create(self, **kw):
        return next(self._it)


def _oai_msg(content=None, tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=content, tool_calls=tool_calls))])


def test_openai_loop_dispatches_then_answers():
    tc = SimpleNamespace(id="c1", function=SimpleNamespace(name="search_memory", arguments='{"query": "y"}'))
    client = _FakeOpenAI([
        _oai_msg(content=None, tool_calls=[tc]),
        _oai_msg(content="final answer", tool_calls=None),
    ])
    seen = {}

    async def disp(name, args):
        seen["name"] = name; seen["args"] = args
        return ToolResult(ok=True, content="MEM", provenance=[{"title": "doc.md"}])

    conv = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    text, events = _run(providers._run_openai_tools(client, "gpt-x", conv, [], disp, 100, 4))
    assert text == "final answer"
    assert seen == {"name": "search_memory", "args": {"query": "y"}}
    assert events[0]["tool"] == "search_memory" and events[0]["ok"] is True
    assert conv[-1]["role"] == "tool" and conv[-1]["content"] == "MEM"


def test_supports_native_tools_allows_local_models():
    # Sovereignty: a local model must be allowed to attempt tool-calling.
    assert providers.supports_native_tools("llama3.3:70b") is True
    assert providers.supports_native_tools("llama3.2:3b") is True


# ── fake Ollama HTTP client ──────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, data): self._data = data
    def raise_for_status(self): pass
    def json(self): return self._data


class _FakeOllamaHTTP:
    def __init__(self, responses): self._it = iter(responses)
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, url, json=None): return _FakeResp(next(self._it))


def test_ollama_loop_dispatches_then_answers(monkeypatch):
    responses = [
        {"message": {"content": "", "tool_calls": [
            {"function": {"name": "search_memory", "arguments": {"query": "y"}}}]}},
        {"message": {"content": "local answer"}},
    ]
    monkeypatch.setattr(providers.httpx, "AsyncClient",
                        lambda *a, **k: _FakeOllamaHTTP(responses))
    seen = {}

    async def disp(name, args):
        seen["name"] = name; seen["args"] = args
        return ToolResult(ok=True, content="MEM", provenance=[{"title": "d.md"}])

    conv = [{"role": "user", "content": "hi"}]
    text, events = _run(providers._run_ollama_tools("llama3.3:70b", conv, [], disp, 100, 4))
    assert text == "local answer"
    assert seen == {"name": "search_memory", "args": {"query": "y"}}
    assert events[0]["tool"] == "search_memory" and events[0]["ok"] is True
    assert conv[-1]["role"] == "tool" and conv[-1]["content"] == "MEM"


def test_ollama_loop_handles_json_string_args(monkeypatch):
    # Some local models emit arguments as a JSON string rather than an object.
    responses = [
        {"message": {"content": "", "tool_calls": [
            {"function": {"name": "web_search", "arguments": '{"query": "z"}'}}]}},
        {"message": {"content": "done"}},
    ]
    monkeypatch.setattr(providers.httpx, "AsyncClient",
                        lambda *a, **k: _FakeOllamaHTTP(responses))
    seen = {}

    async def disp(name, args):
        seen.update(args)
        return ToolResult(ok=True, content="r", provenance=[])

    text, events = _run(providers._run_ollama_tools("qwen2.5:72b", [{"role": "user", "content": "hi"}], [], disp, 100, 4))
    assert text == "done" and seen == {"query": "z"}
