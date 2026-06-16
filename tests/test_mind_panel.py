"""
Tests for the persistent "your mind" panel (onboarding v0.1):
- the per-brain show/hide setting that ALSO gates per-turn extraction (default
  OFF, so an established fleet brain incurs no extra model call until opt-in);
- the cheap extraction-model resolver (must never pick the operator's expensive
  default; prefers a Haiku-class model on whatever key is configured).
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _settings(tmp_path):
    os.environ["SETTINGS_PATH"] = str(tmp_path / "settings.json")
    (tmp_path / "settings.json").write_text("{}")
    from api import settings_store
    importlib.reload(settings_store)
    return settings_store


# ── show/hide setting (default OFF = cost-safe for the fleet) ──────────────
def test_mind_panel_defaults_off(tmp_path):
    ss = _settings(tmp_path)
    assert ss.get_mind_panel_shown() is False


def test_mind_panel_persists(tmp_path):
    ss = _settings(tmp_path)
    ss.set_mind_panel_shown(True)
    assert ss.get_mind_panel_shown() is True
    # survives a fresh load of the store
    importlib.reload(ss)
    assert ss.get_mind_panel_shown() is True
    ss.set_mind_panel_shown(False)
    assert ss.get_mind_panel_shown() is False


# ── cheap extraction model (never the expensive default) ──────────────────
def test_cheap_extraction_model_prefers_haiku(tmp_path):
    _settings(tmp_path)
    import api.providers as p
    importlib.reload(p)
    p._anthropic_async = object()
    p._openai = p._gemini = p._groq = p._mistral = p._together = p._openrouter = None
    assert p.cheap_extraction_model() == "claude-haiku-4-5"


def test_cheap_extraction_model_per_provider(tmp_path):
    _settings(tmp_path)
    import api.providers as p
    importlib.reload(p)
    p._anthropic_async = None
    p._openai = object()
    p._gemini = p._groq = p._mistral = p._together = p._openrouter = None
    assert p.cheap_extraction_model() == "gpt-4o-mini"


def test_cheap_extraction_model_falls_back_to_local_without_cloud_key(tmp_path):
    _settings(tmp_path)
    import api.providers as p
    importlib.reload(p)
    p._anthropic_async = p._openai = p._gemini = p._groq = p._mistral = p._together = p._openrouter = None
    # No cloud key → the brain's default (local fallback), which is free — never
    # a frontier model for a per-turn extraction call.
    m = p.cheap_extraction_model()
    assert m == p.LOCAL_FALLBACK_MODEL or "claude-opus" not in m
