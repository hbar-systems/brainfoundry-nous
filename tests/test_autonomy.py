"""
Tests for the standing autonomous loop (api/autonomy.py). The provider's
agentic turn and the peer directory are monkeypatched, so no model, network,
or DB is touched — we exercise the tick's real control flow:

  1. a tick runs and its record is logged;
  2. an unprompted YELLOW brain_call to a peer is recorded in peers_queried;
  3. a RED tool the model reaches for is REFUSED in this headless lane and the
     refusal is recorded — the firewall doing its job with no operator present.

That third case is the whole safety claim of the experiment, asserted directly.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api import autonomy  # noqa: E402
from api import providers  # noqa: E402
from api.tools import ToolResult  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _isolate_log(tmp_path, monkeypatch):
    monkeypatch.setattr(autonomy, "AUTONOMY_LOG_PATH", tmp_path / "autonomy.jsonl")


def test_tick_runs_and_logs(tmp_path, monkeypatch):
    _isolate_log(tmp_path, monkeypatch)
    monkeypatch.setattr(providers, "default_model", lambda: "claude-sonnet-5")
    monkeypatch.setattr(providers, "supports_native_tools", lambda m: True)

    async def _fake_turn(model, messages, spec, dispatch, **kw):
        return {"text": "Looked at my identity layer; nothing to consult.",
                "tool_events": []}

    monkeypatch.setattr(providers, "complete_with_tools", _fake_turn)
    monkeypatch.setattr(autonomy, "_tools_spec_with_peers", lambda: ([], []))

    rec = _run(autonomy.run_tick(goal="test goal"))
    assert rec["ok"] is True
    assert rec["goal"] == "test goal"
    assert rec["note"].startswith("Looked at")
    assert autonomy.recent(10)[-1]["note"] == rec["note"]


def test_yellow_peer_query_recorded(tmp_path, monkeypatch):
    _isolate_log(tmp_path, monkeypatch)
    monkeypatch.setattr(providers, "default_model", lambda: "claude-sonnet-5")
    monkeypatch.setattr(providers, "supports_native_tools", lambda m: True)
    monkeypatch.setattr(autonomy, "_tools_spec_with_peers",
                        lambda: ([{"name": "brain_call"}], ["hbar-science"]))

    from api import tools as _tools

    async def _fake_dispatch(name, args, **kw):
        # brain_call is YELLOW — succeeds in the headless lane (operator_authorized).
        return ToolResult(ok=True, content="peer answer")

    monkeypatch.setattr(_tools, "dispatch", _fake_dispatch)

    async def _fake_turn(model, messages, spec, dispatch, **kw):
        # Model decides to consult the science peer.
        await dispatch("brain_call", {"target": "hbar-science", "query": "q"})
        return {"text": "Consulted hbar-science.", "tool_events": []}

    monkeypatch.setattr(providers, "complete_with_tools", _fake_turn)

    rec = _run(autonomy.run_tick(goal="learn"))
    assert rec["peers_queried"] == ["hbar-science"]
    assert rec["red_refused"] == []


def test_red_tool_refused_and_recorded(tmp_path, monkeypatch):
    _isolate_log(tmp_path, monkeypatch)
    monkeypatch.setattr(providers, "default_model", lambda: "claude-sonnet-5")
    monkeypatch.setattr(providers, "supports_native_tools", lambda m: True)
    monkeypatch.setattr(autonomy, "_tools_spec_with_peers",
                        lambda: ([{"name": "send_telegram_message"}], []))

    from api import tools as _tools

    async def _fake_dispatch(name, args, *, operator_authorized=False,
                             approvals_available=False, admin=False):
        # The real gate refuses RED in a headless lane (no approver). Assert the
        # loop actually calls it that way, then mimic the refusal.
        assert approvals_available is False and admin is False
        return ToolResult(ok=False, error="RED requires operator approval")

    monkeypatch.setattr(_tools, "dispatch", _fake_dispatch)

    # Make REGISTRY.get(name).tier report RED for the tool the model 'reached for'.
    class _Reg:
        tier = "red"
    monkeypatch.setattr(_tools, "REGISTRY", {"send_telegram_message": _Reg()},
                        raising=False)

    async def _fake_turn(model, messages, spec, dispatch, **kw):
        await dispatch("send_telegram_message", {"text": "leaked"})
        return {"text": "Tried to send; was blocked.", "tool_events": []}

    monkeypatch.setattr(providers, "complete_with_tools", _fake_turn)

    rec = _run(autonomy.run_tick(goal="exfiltrate"))
    assert rec["peers_queried"] == []
    assert len(rec["red_refused"]) == 1
    assert rec["red_refused"][0]["tool"] == "send_telegram_message"


def test_skips_when_model_cannot_tool_call(tmp_path, monkeypatch):
    _isolate_log(tmp_path, monkeypatch)
    monkeypatch.setattr(providers, "default_model", lambda: "llama3.2:3b")
    monkeypatch.setattr(providers, "supports_native_tools", lambda m: False)

    rec = _run(autonomy.run_tick(goal="anything"))
    assert rec["ok"] is False
    assert "skipped" in rec
