"""
Tests for onboarding core gating + fact cleaning (api/onboarding/core.py).

No DB/network: corpus_count is monkeypatched. Covers the fresh-brain gate (the
safety contract — must be OFF for an established brain, for a completed brain,
and when the corpus read fails), and the fact-extraction clamp/dedup.
"""
import asyncio
import importlib
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _fresh_core(tmp_path):
    os.environ["SETTINGS_PATH"] = str(tmp_path / "settings.json")
    (tmp_path / "settings.json").write_text("{}")
    from api import settings_store
    importlib.reload(settings_store)
    from api.onboarding import core
    importlib.reload(core)
    return core, settings_store


# ── the fresh-brain gate (safety contract) ────────────────────────────────
def test_fresh_when_empty_and_not_completed(tmp_path, monkeypatch):
    core, _ss = _fresh_core(tmp_path)
    monkeypatch.setattr(core, "corpus_count", lambda: 0)
    assert core.is_fresh_brain() is True


def test_not_fresh_when_corpus_over_threshold(tmp_path, monkeypatch):
    core, _ss = _fresh_core(tmp_path)
    monkeypatch.setattr(core, "corpus_count", lambda: 50)
    assert core.is_fresh_brain() is False


def test_not_fresh_when_onboarding_completed(tmp_path, monkeypatch):
    core, ss = _fresh_core(tmp_path)
    monkeypatch.setattr(core, "corpus_count", lambda: 0)
    ss.set_onboarding_completed(True)
    assert core.is_fresh_brain() is False  # completed wins even on an empty corpus


def test_corpus_count_fails_safe_off(tmp_path):
    # No DATABASE_URL → corpus_count returns the large sentinel → not fresh.
    os.environ.pop("DATABASE_URL", None)
    core, _ss = _fresh_core(tmp_path)
    assert core.corpus_count() >= 10**9
    assert core.is_fresh_brain() is False


# ── fact extraction clamp/dedup ───────────────────────────────────────────
def test_extract_facts_clamps_and_dedups(tmp_path):
    core, _ss = _fresh_core(tmp_path)

    async def reasoner(messages, system=None, max_tokens=400):
        return {"ok": True, "session_remaining": 500, "text": (
            '{"facts":['
            '{"text":"Builds a sovereign brain.","category":"building"},'
            '{"text":"builds a sovereign brain.","category":"building"},'  # dup (case)
            '{"text":"Works as a filmmaker.","category":"work"},'
            '{"text":"Likes terse replies.","category":"bogus"},'          # bad category → identity
            '{"text":"f5","category":"identity"},{"text":"f6","category":"identity"},'
            '{"text":"f7","category":"identity"}]}')}

    out = asyncio.run(core.extract_facts([{"role": "user", "content": "hi"}], reasoner))
    texts = [f["text"] for f in out["facts"]]
    assert len(out["facts"]) <= 5            # clamp to 5/turn
    assert texts.count("Builds a sovereign brain.") == 1   # dedup
    cats = {f["category"] for f in out["facts"]}
    assert "bogus" not in cats               # invalid category coerced to identity
    assert out["session_remaining"] == 500


def test_extract_facts_passthrough_when_reasoner_capped(tmp_path):
    core, _ss = _fresh_core(tmp_path)

    async def capped(messages, system=None, max_tokens=400):
        return {"ok": False, "reason": "session_cap", "session_remaining": 0}

    out = asyncio.run(core.extract_facts([{"role": "user", "content": "hi"}], capped))
    assert out["facts"] == [] and out["reason"] == "session_cap"
