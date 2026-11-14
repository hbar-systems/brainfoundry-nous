"""Ways of working on the home: the layout key `surfaces` and the home it renders (SURFACES-PICK-1).
Created 2026-11-13. No network, no reasoner.

    pytest tests/test_surfaces_pick.py -v
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_catalog as C  # noqa: E402
import cc_layout as L  # noqa: E402

from tests.test_cc_bridge import _load  # noqa: E402
from tests.test_cc_layout import _node_json  # noqa: E402


# ---- the layout key ----

def test_default_is_every_surface():
    assert L.DEFAULT["surfaces"] is None
    assert L.validate({})["surfaces"] is None
    assert "home shows" not in L.summary({})


def test_surfaces_normalize_and_keep_the_conversation():
    lay = L.validate({"surfaces": ["terminal", "systems", "systems"]})
    assert lay["surfaces"] == ["chat", "systems", "terminal"]          # catalogue order, chat always in
    assert L.validate({"surfaces": []})["surfaces"] == ["chat"]
    assert L.validate({"surfaces": None})["surfaces"] is None
    assert L.summary({"surfaces": ["talkthrough"]}) == "home shows chat, talk-through"


@pytest.mark.parametrize("bad", [{"surfaces": "chat"}, {"surfaces": ["court"]}, {"surfaces": [1]}, {"surfaces": {"chat": True}}])
def test_surfaces_closed_list(bad):
    with pytest.raises(L.LayoutError):
        L.validate(bad)


def test_question_after_the_look_with_a_sentence_each():
    ids = [q["id"] for q in L.QUESTIONS]
    assert ids[-1] == "surfaces" and ids.index("surfaces") > ids.index("voice")
    q = L.QUESTIONS[-1]
    assert q["multi"] and [o[0] for o in q["options"]] == list(L.SURFACES)
    assert set(q["about"]) == set(L.SURFACES) and all(len(s.split()) >= 6 for s in q["about"].values())
    # generic words only: the template is public
    words = " ".join(w + " " + q["about"][k] for k, w in q["options"]).lower()
    for name in ("court", "telegram", "claude"):
        assert name not in words, name


def test_answers_marker_and_presets():
    assert L.from_answers({"surfaces": ["systems"]})["surfaces"] == ["chat", "systems"]
    assert L.validate_answers({"surfaces": ["terminal", "chat"]}) == {"surfaces": ["chat", "terminal"]}
    with pytest.raises(L.LayoutError):
        L.from_answers({"surfaces": ["nope"]})
    _, lay, err = L.parse_marker('ok <layout>{"preset": "owner", "answers": {"surfaces": ["decisions"]}}</layout>')
    assert err is None and lay["surfaces"] == ["chat", "decisions"]
    # defaults by person: a newcomer gets chat and talk-through, the owner everything
    assert L.from_answers({}, "member")["surfaces"] == ["chat", "talkthrough"]
    assert L.from_answers({}, "org")["surfaces"] == ["chat", "talkthrough"]
    assert L.from_answers({}, "owner")["surfaces"] is None
    # the answers a layout reproduces carry the list back
    lay = L.from_answers({"surfaces": ["phone", "sidepane"]})
    assert L.from_answers(C.layout_to_answers(lay))["surfaces"] == lay["surfaces"]


def test_interview_doc_names_every_surface_and_its_sentence():
    doc = (ROOT / "docs" / "personalize-interview.md").read_text()
    assert "| surfaces | Which ways of working" in doc
    for k, _w, about in L.SURFACE_LIST:
        assert f"| {k} | {about}" in doc, k


# ---- the bridge: the view carries the question, the pages, and saves the key ----

def test_bridge_view_pages_and_save(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path, with_key=False)
    monkeypatch.setenv("CC_PAGE_DECISIONS", str(tmp_path / "nowhere.html"))
    monkeypatch.setenv("CC_PAGE_TAPE", str(tmp_path / "tape dir" / "index.html"))
    st, d = m._layout_api("GET", "/layout", None, {})
    assert st == 200 and d["pages"] == {}
    sq = next(q for q in d["questions"] if q["id"] == "surfaces")
    assert sq["about"]["talkthrough"] and sq["options"][0] == ["chat", "chat"]
    (tmp_path / "tape dir").mkdir()
    (tmp_path / "tape dir" / "index.html").write_text("<p>tape</p>")
    d = m._layout_api("GET", "/layout", None, {})[1]
    assert d["pages"] == {"tape": "/cc/files/raw" + str(tmp_path).replace(" ", "%20") + "/tape%20dir/index.html"}
    st, d = m._layout_api("POST", "/layout/save", {"layout": {**L.DEFAULT, "surfaces": ["systems"]}, "answers": {"surfaces": ["systems"]}}, {})
    assert st == 200 and d["layout"]["surfaces"] == ["chat", "systems"] and d["answers"]["surfaces"] == ["chat", "systems"]
    st, d = m._layout_api("POST", "/layout/save", {"layout": {"surfaces": ["court"]}}, {})
    assert st == 400 and "surfaces" in d["error"]
    # the interview may open the pick-list beside the conversation
    clean, pane = m._extract_pane("Pick here. <pane>/layout?step=surfaces</pane>")
    assert pane == {"route": "/layout?step=surfaces", "title": "Ways of working"} and clean == "Pick here."


# ---- the home rendering: the page glue (ui/lib/layout.js) and the console page that uses it ----

def _home(layout, pages):
    return _node_json("const l=require('./layout.js');const lay=%s,pg=%s;"
                      "console.log(JSON.stringify({keys:l.SURFACE_KEYS,on:Object.fromEntries(l.SURFACE_KEYS.map(k=>[k,l.surfaceOn(lay,k)])),"
                      "buttons:l.homeButtons(lay,pg)}))" % (json.dumps(layout), json.dumps(pages)))


PAGES = {"decisions": "/cc/files/raw/x/decisions/index.html", "tape": "/cc/files/raw/x/memos/index.html"}


def test_js_list_matches_the_box():
    assert _home(None, {})["keys"] == list(L.SURFACES)


def test_home_stock_shows_everything():
    for lay in (None, L.DEFAULT):
        out = _home(lay, PAGES)
        assert all(out["on"].values())
        assert [b["id"] for b in out["buttons"]] == ["decisions", "systems", "talkthrough"]   # tape rides on talk-through


def test_home_newcomer_pick():
    out = _home(L.from_answers({}, "member"), PAGES)
    assert {k for k, v in out["on"].items() if v} == {"chat", "talkthrough"}
    assert out["buttons"] == [{"id": "talkthrough", "label": "talk through", "route": PAGES["tape"]}]


def test_home_second_pick_and_missing_pages():
    lay = L.from_answers({"surfaces": ["decisions", "systems", "phone", "terminal"]})
    out = _home(lay, PAGES)
    assert [b["id"] for b in out["buttons"]] == ["decisions", "systems", "phone"]
    assert out["on"]["terminal"] and not out["on"]["sidepane"] and not out["on"]["thoughts"]
    # a brain without the desk pages shows only what has an address
    assert [b["id"] for b in _home(lay, {})["buttons"]] == ["systems"]
    # an unknown id from an old file is ignored, the conversation stays
    out = _home({"surfaces": ["nope"]}, PAGES)
    assert out["on"]["chat"] and out["buttons"] == []


def test_console_page_gates_each_surface():
    src = (ROOT / "ui" / "pages" / "cc.js").read_text()
    for k in ("terminal", "sidepane", "thoughts", "phone"):
        assert f"surfaceOn(layoutBase, '{k}')" in src, k
    assert "homeButtons(layoutBase, surfacePages)" in src
    assert re.search(r"d\.pages\) setSurfacePages\(d\.pages\)", src)
    lay_src = (ROOT / "ui" / "pages" / "layout.js").read_text()
    assert "step') === 'surfaces'" in lay_src and "<select" not in lay_src
