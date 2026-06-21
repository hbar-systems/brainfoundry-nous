"""Tests for the appearance config plane ("customize your brain" v0).

Pure-logic + sidecar storage (redirected to a tmp file). No fastapi/model/network
touched — the NL translator's LLM call is injected.

Created 2026-06-21.
"""
import asyncio

import pytest

from api import appearance as ap


@pytest.fixture(autouse=True)
def _tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "APPEARANCE_PATH", tmp_path / "appearance.json")


# ── validation: closed schema ────────────────────────────────────────────────

def test_default_is_stock_look():
    cfg = ap.get_config()
    assert cfg["theme"] == "gold" and cfg["menuTitle"] is None
    assert cfg["hiddenTabs"] == [] and cfg["tabOrder"] == []


def test_reject_unknown_field():
    with pytest.raises(ap.AppearanceError):
        ap.validate({"evilField": 1})


def test_reject_bad_theme():
    with pytest.raises(ap.AppearanceError):
        ap.validate({"theme": "neon-disco"})


def test_reject_bad_accent():
    with pytest.raises(ap.AppearanceError):
        ap.validate({"accent": "#ffffff"})  # not in the fixed palette


def test_reject_unknown_tab_id():
    with pytest.raises(ap.AppearanceError):
        ap.validate({"hiddenTabs": ["_not_a_tab"]})


def test_reject_hiding_settings():
    with pytest.raises(ap.AppearanceError):
        ap.validate({"hiddenTabs": ["_settings"]})


def test_menu_title_length_and_controls():
    with pytest.raises(ap.AppearanceError):
        ap.validate({"menuTitle": "x" * 41})
    with pytest.raises(ap.AppearanceError):
        ap.validate({"menuTitle": "bad\x00title"})
    assert ap.validate({"menuTitle": "  Praxis Müller  "})["menuTitle"] == "Praxis Müller"


def test_tab_order_dedup_rejected():
    with pytest.raises(ap.AppearanceError):
        ap.validate({"tabOrder": ["_chat", "_chat"]})


# ── storage: apply / revert / reset / history ────────────────────────────────

def test_apply_then_revert_restores_prior():
    ap.apply_config({"menuTitle": "First"})
    ap.apply_config({"menuTitle": "Second"})
    assert ap.get_config()["menuTitle"] == "Second"
    ap.revert()
    assert ap.get_config()["menuTitle"] == "First"


def test_reset_returns_to_default():
    ap.apply_config({"theme": "sapphire", "menuTitle": "Zog"})
    ap.reset()
    cfg = ap.get_config()
    assert cfg["theme"] == "gold" and cfg["menuTitle"] is None


def test_history_records_snapshots_newest_first():
    ap.apply_config({"menuTitle": "A"})
    ap.apply_config({"menuTitle": "B"})
    h = ap.history()
    assert len(h) == 2
    # newest snapshot is the config just before the latest write (menuTitle "A")
    assert h[0]["config"]["menuTitle"] == "A"


def test_partial_patch_preserves_other_fields():
    ap.apply_config({"theme": "forest"})
    ap.apply_config({"menuTitle": "Keep theme"})
    cfg = ap.get_config()
    assert cfg["theme"] == "forest" and cfg["menuTitle"] == "Keep theme"


# ── apply_to_tabs (server-side nav transform) ────────────────────────────────

def _tabs():
    return [{"id": "_dashboard", "label": "Dashboard"},
            {"id": "_chat", "label": "Chat"},
            {"id": "_settings", "label": "Settings"},
            {"id": "_economy", "label": "Economy"}]


def test_hidden_tabs_filtered_but_settings_protected():
    out = ap.apply_to_tabs(_tabs(), {"hiddenTabs": ["_economy", "_settings"],
                                     "tabOrder": []})
    ids = [t["id"] for t in out]
    assert "_economy" not in ids
    assert "_settings" in ids  # protected, never hidden even if requested


def test_tab_order_reorders_listed_first():
    out = ap.apply_to_tabs(_tabs(), {"hiddenTabs": [], "tabOrder": ["_chat", "_dashboard"]})
    ids = [t["id"] for t in out]
    assert ids[:2] == ["_chat", "_dashboard"]
    # unlisted tabs keep their incoming order after the listed ones
    assert ids[2:] == ["_settings", "_economy"]


# ── NL translator (injected LLM) ─────────────────────────────────────────────

def test_nl_valid_diff():
    async def fake(prompt):
        return '{"menuTitle": "Praxis Müller", "hiddenTabs": ["_economy"]}'
    res = asyncio.run(ap.nl_to_diff("rename header and hide economy", complete_fn=fake))
    assert res["diff"]["menuTitle"] == "Praxis Müller"
    assert res["resulting"]["hiddenTabs"] == ["_economy"]


def test_nl_out_of_schema_field_dropped_or_rejected():
    async def fake(prompt):
        return '{"deployServer": true}'  # not a config field
    res = asyncio.run(ap.nl_to_diff("redeploy the server", complete_fn=fake))
    assert res["diff"] == {} and "error" in res


def test_nl_invalid_value_reports_error_and_changes_nothing():
    async def fake(prompt):
        return '{"theme": "neon"}'
    res = asyncio.run(ap.nl_to_diff("make it neon", complete_fn=fake))
    assert res["diff"] == {} and "error" in res


def test_nl_cannot_hide_settings():
    async def fake(prompt):
        return '{"hiddenTabs": ["_settings"]}'
    res = asyncio.run(ap.nl_to_diff("hide settings", complete_fn=fake))
    assert res["diff"] == {} and "error" in res
