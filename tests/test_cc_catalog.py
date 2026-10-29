"""Personalization catalog, presets and arrangements (scripts/cc/cc_catalog.py, docs/PERSONALIZATION.md).
Created 2026-10-29. No network, no reasoner.

    pytest tests/test_cc_catalog.py -v
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_catalog as C  # noqa: E402
import cc_layout as L  # noqa: E402


def test_catalog_is_closed_and_evidenced():
    C.validate_catalog()
    for it in C.CATALOG:
        if it["status"] == "standard":
            assert it["evidence"] != C.UNKNOWN
        assert not any(s in it["id"] for s in ("http", "{", ";", " "))


def test_catalog_covers_the_console():
    # every panel, view and theme of the layout schema, and every pane route, has a catalog item
    for k in L.PANELS:
        assert f"panel:{k}" in C.BY_ID, k
    for v in L.VIEWS:
        assert f"view:{v}" in C.BY_ID, v
    for t in L.THEMES:
        assert f"look:{t}" in C.BY_ID, t
    for tier in L.TIERS.values():
        for tab in tier:
            assert f"tab:{tab}" in C.BY_ID, tab


def test_presets_load():
    assert C.preset_ids() == ("family-telegram", "org", "owner", "public")
    for name in C.preset_ids():
        p = C.load_preset(name)
        assert any(x in C.ACCESS for x in p["items"])
    assert C.load_preset("public")["items"] == ["access:public-chat"]
    assert "access:console" not in C.load_preset("family-telegram")["items"]


@pytest.mark.parametrize("items,aud", [
    (["tab:_chat"], "owner"),                                   # no access item
    (["access:console", "tab:_graph"], "owner"),                # candidate, not yet used by hbar
    (["access:console", "access:console"], "owner"),            # twice
    (["access:console", "https://evil"], "owner"),              # free text
    (["access:public-chat", "tab:_system"], "public"),          # not for the public
    ("access:console", "owner"),                                # not a list
])
def test_items_refused(items, aud):
    with pytest.raises(C.CatalogError):
        C.validate_items(items, aud)


def test_from_answers_starts_from_preset(tmp_path, monkeypatch):
    d = tmp_path / "presets"
    d.mkdir()
    (d / "dark.json").write_text(json.dumps({"id": "dark", "name": "x", "audience": "owner", "mode": "operator",
                                             "answers": {"tone": "black", "size": "large"}, "items": ["access:console"]}))
    monkeypatch.setattr(C, "PRESETS_DIR", d)
    lay = L.from_answers({"size": "small"}, preset="dark")
    assert lay["theme"] == "black" and lay["size"] == "small"
    with pytest.raises(L.LayoutError):
        L.from_answers({}, preset="nope")
    clean, lay, err = L.parse_marker('ok <layout>{"preset": "dark", "answers": {}}</layout>')
    assert err is None and lay["theme"] == "black" and clean == "ok"
    clean, lay, err = L.parse_marker('<layout>{"preset": "../x", "answers": {}}</layout>')
    assert lay is None and err


def test_arrangement_store(tmp_path):
    st = L.Store(tmp_path)
    assert st.arrangement() is None
    arr = st.set_arrangement({"preset": "org", "items": ["access:console", "tab:_chat"]})
    assert st.arrangement() == arr and arr["preset"] == "org"
    with pytest.raises(L.LayoutError):
        st.set_arrangement({"preset": "org", "items": ["access:console", "tab:_system"]})   # owner-only tab
    with pytest.raises(L.LayoutError):
        st.set_arrangement({"items": ["access:console"], "css": "a{}"})
    # the layout itself is untouched and a shared pack never carries the arrangement
    assert st.get() is None and "arrangement" not in L.validate({})


def test_layout_to_answers_round_trip():
    a = {"first": "panes", "never": ["board", "hero"], "panes": "one", "side": "left", "tone": "black",
         "face": "mono", "weight": "thin", "size": "large", "width": "full", "voice": "speak"}
    lay = L.from_answers(a)
    assert C.layout_to_answers(lay) == L.validate_answers(a)
    assert L.from_answers(C.layout_to_answers(L.DEFAULT)) == L.DEFAULT
