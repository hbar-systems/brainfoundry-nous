"""Layout file for the CC console (scripts/cc/cc_layout.py and the bridge's /layout routes).
Created 2026-10-09. No network, no reasoner.

    pytest tests/test_cc_layout.py -v
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_layout as L  # noqa: E402

from tests.test_cc_bridge import _load  # noqa: E402


def test_default_validates_and_is_stock():
    assert L.validate({}) == L.DEFAULT
    assert L.summary({}) == "the stock console"


@pytest.mark.parametrize("bad", [
    {"css": "body{display:none}"},
    {"vars": {"--accent": "url(http://x)"}},
    {"vars": {"--accent": "red"}},
    {"vars": {"--accent": "#12345"}},
    {"vars": {"background-image": "#000000"}},
    {"font": "Comic Sans; } body {"},
    {"panels": {"chat": False}},
    {"panels": {"hero": "no"}},
    {"pane": {"width": 100}},
    {"pane": {"width": True}},
    {"pane": {"side": "top"}},
    {"view": "https://evil"},
    {"v": 2},
    {"name": "<script>"},
    {"voice": {"speak": 1}},
    {"density": "airy"},
    {"density": None},
])
def test_closed_schema_refuses(bad):
    with pytest.raises(L.LayoutError):
        L.validate(bad)


def test_valid_layout_normalizes():
    lay = L.validate({"theme": "black", "vars": {"--accent": "#C9A96E"}, "font": "jetbrains", "weight": "thin",
                      "pane": {"side": "left", "width": 520}, "panels": {"board": False}, "view": "gallery"})
    assert lay["vars"]["--accent"] == "#c9a96e" and lay["panels"]["hero"] is True and lay["panels"]["board"] is False
    r = L.resolve(lay)
    assert r["vars"]["--bg"] == "#000000" and r["vars"]["--accent"] == "#c9a96e" and r["weight"] == 300 and r["zoom"] == 1.0


def test_answers_to_layout():
    lay = L.from_answers({"first": "panes", "never": ["board", "hero"], "panes": "one", "side": "left", "tone": "black",
                          "face": "mono", "weight": "thin", "size": "large", "width": "full", "voice": "handsfree"})
    assert lay["view"] == "panes" and lay["panels"]["board"] is False and lay["panels"]["hero"] is False
    assert lay["panels"]["sidebyside"] is False and lay["pane"]["side"] == "left" and lay["theme"] == "black"
    assert lay["font"] == "jetbrains" and lay["weight"] == "thin" and lay["size"] == "large" and lay["column"] == "full"
    assert lay["voice"] == {"speak": True, "handsfree": True}
    assert L.from_answers({}) == L.DEFAULT
    for bad in ({"first": "elsewhere"}, {"never": "board"}, {"never": ["chat"]}, {"nope": 1}):
        with pytest.raises(L.LayoutError):
            L.from_answers(bad)


def test_interview_doc_matches_question_list():
    doc = (ROOT / "docs" / "personalize-interview.md").read_text()
    assert 8 <= len(L.QUESTIONS) <= 10
    for q in L.QUESTIONS:
        assert f"| {q['id']} |" in doc, q["id"]
        for value, _label in q["options"]:
            assert value in doc, (q["id"], value)


def test_marker_proposes_never_raises():
    text = 'Here it is.\n<layout>{"answers": {"tone": "black", "never": []}}</layout>'
    clean, lay, err = L.parse_marker(text)
    assert clean == "Here it is." and lay["theme"] == "black" and err is None
    clean, lay, err = L.parse_marker('x <layout>{"theme": "black", "css": "a{}"}</layout>')
    assert lay is None and "css" in err and clean == "x"
    clean, lay, err = L.parse_marker('<layout>not json</layout>')
    assert lay is None and err
    assert L.parse_marker("no marker") == ("no marker", None, None)


def test_store_save_undo_reset(tmp_path):
    s = L.Store(tmp_path)
    assert s.get() is None
    s.save({"theme": "black"}, answers={"tone": "black"})
    s.save({"theme": "light"})
    assert s.get()["theme"] == "light" and s.answers() == {"tone": "black"}
    assert s.undo()["theme"] == "black"
    s.reset()
    assert s.get() is None
    assert oct((tmp_path / "layout.json").stat().st_mode & 0o777)  # file exists
    with pytest.raises(L.LayoutError):
        s.save({"font": "x"})
    # a hand-edited file that no longer validates falls back to stock
    (tmp_path / "layout.json").write_text(json.dumps({"current": {"vars": {"--accent": "red"}}}))
    assert s.get() is None


def test_proposals_from_interview_and_packs(tmp_path):
    packs = tmp_path / "brain-apps"
    (packs / "layout-mine").mkdir(parents=True)
    (packs / "layout-mine" / "layout.json").write_text(json.dumps({"name": "mine", "theme": "black", "font": "lora"}))
    (packs / "layout-evil").mkdir()
    (packs / "layout-evil" / "layout.json").write_text(json.dumps({"theme": "black", "css": "x"}))
    (packs / "packs").mkdir()   # the real brain-apps/packs dir has no layout.json
    s = L.Store(tmp_path / "state", packs)
    assert [p["source"] for p in s.proposals()] == ["pack layout-mine"]
    assert s.get() is None   # nothing applied by being found
    p = s.propose(L.from_answers({"tone": "light"}), "interview", answers={"tone": "light"})
    assert {x["source"] for x in s.proposals()} == {"interview", "pack layout-mine"}
    assert s.approve(p["id"])["theme"] == "light" and s.answers() == {"tone": "light"}
    assert [x["source"] for x in s.proposals()] == ["pack layout-mine"]
    pid = s.proposals()[0]["id"]
    assert s.dismiss(pid) and s.proposals() == [] and s.get()["theme"] == "light"
    assert s.approve("nope") is None and not s.dismiss("nope")
    # a pack updated to a different layout is a new proposal
    (packs / "layout-mine" / "layout.json").write_text(json.dumps({"name": "mine", "theme": "black", "font": "crimson"}))
    assert len(s.proposals()) == 1


def test_export_pack_passes_the_brain_app_schema(tmp_path):
    import jsonschema
    import yaml
    schema = json.loads((ROOT / "api" / "schemas" / "brain-app.schema.json").read_text())
    lay = L.validate({"theme": "black", "font": "jetbrains", "weight": "thin", "view": "gallery",
                      "panels": {"board": False, "gallery": False, "files": False, "hero": False, "hint": False},
                      "pane": {"side": "left", "width": 500}, "column": "full", "size": "large",
                      "voice": {"speak": True, "handsfree": True}, "vars": {"--accent": "#6b8cce"}})
    for repo in (None, "https://github.com/someone/layout-quiet"):
        pk = L.export_pack(lay, name="Quiet Black", repo=repo, author="Someone")
        man = yaml.safe_load(pk["files"]["brain-app.yaml"])
        jsonschema.validate(man, schema)
        assert len(man["description"]) <= 240 and man["id"] == "layout-quiet-black"
        assert pk["repo_set"] is bool(repo)
        assert L.validate(json.loads(pk["files"]["layout.json"]))["name"] == "Quiet Black"
        assert "dist/index.html" in pk["files"]
    # the exported layout, installed elsewhere, comes back as a proposal and not as an applied layout
    d = tmp_path / "other" / "brain-apps" / pk["id"]
    d.mkdir(parents=True)
    (d / "layout.json").write_text(pk["files"]["layout.json"])
    other = L.Store(tmp_path / "other" / "state", tmp_path / "other" / "brain-apps")
    assert other.get() is None and len(other.proposals()) == 1


def test_bridge_routes_and_marker(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path, with_key=False)
    st, d = m._layout_api("GET", "/layout", None, {})
    assert st == 200 and d["layout"] is None and len(d["questions"]) == len(L.QUESTIONS)
    st, d = m._layout_api("POST", "/layout/save", {"layout": {"css": "x"}}, {})
    assert st == 400 and "css" in d["error"]
    st, d = m._layout_api("POST", "/layout/propose", {"answers": {"tone": "black", "face": "serif"}, "source": "interview"}, {})
    assert st == 200 and len(d["proposals"]) == 1 and d["layout"] is None
    st, d = m._layout_api("POST", "/layout/approve", {"id": d["proposals"][0]["id"]}, {})
    assert st == 200 and d["layout"]["font"] == "lora" and d["resolved"]["vars"]["--bg"] == "#000000" and d["proposals"] == []
    st, d = m._layout_api("POST", "/layout/answers", {"answers": {"width": "full"}}, {})
    assert st == 200 and d["layout"]["column"] == "full" and d["answers"] == {"width": "full"}
    assert (tmp_path / ".cc-bridge" / "layout.json").exists()
    st, d = m._layout_api("GET", "/layout/export", None, {"name": "Q", "repo": "https://github.com/a/b"})
    assert st == 200 and d["repo_set"] is True
    m.OUT_DIR = tmp_path / "out"
    st, d = m._layout_api("POST", "/layout/export/write", {"name": "Q"}, {})
    assert st == 200 and (pathlib.Path(d["dir"]) / "layout.json").exists()
    st, d = m._layout_api("POST", "/layout/undo", {}, {})
    assert st == 200
    assert m._layout_api("POST", "/layout/nothing", {}, {})[0] == 404
    # the speech filter drops the block; the history strip drops it too
    assert "layout" not in m._speakable('Done. <layout>{"answers": {}}</layout>')


# ---- the page glue under node (ui/lib/layout.js) ----

def _node_json(script: str):
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_js_plan_capture_round_trip():
    lay = L.from_answers({"never": ["board", "hero"], "side": "left", "face": "mono", "width": "full", "voice": "handsfree"})
    lay["pane"]["width"] = 520
    out = _node_json("const l=require('./layout.js');const lay=%s;const plan=l.localPlan(lay);"
                     "const get=k=>plan.set[k]===undefined?null:plan.set[k];"
                     "console.log(JSON.stringify({plan,back:l.capture(get,lay)}))" % json.dumps(lay))
    assert json.loads(out["plan"]["set"]["cc.hidden"]) == {"hero": True, "board": True}
    assert out["plan"]["set"]["cc.paneSide"] == "left" and out["plan"]["set"]["cc.paneW"] == "520"
    assert out["plan"]["set"]["cc.width"] == "none" and out["plan"]["set"]["cc.font"] == "jetbrains"
    assert out["plan"]["set"]["cc.speak"] == "1" and out["plan"]["set"]["cc.handsfree"] == "1"
    assert L.validate(out["back"]) == lay      # what the browser holds, captured, is the same layout


def test_js_capture_of_a_default_browser_is_valid():
    out = _node_json("const l=require('./layout.js');console.log(JSON.stringify(l.capture(()=>null,null)))")
    assert L.validate(out) == L.DEFAULT


def test_js_apply_style_skips_anything_off_the_list():
    out = _node_json(r"""
const l=require('./layout.js');
const set={}; const root={style:{setProperty:(k,v)=>{set[k]=v},removeProperty:k=>{delete set[k]}}};
const body={style:{}};
const done=l.applyStyle({vars:{'--bg':'#000000','--accent':'url(x)','background':'#111111','--text':'#e6e6e6'},zoom:1.12,weight:300},root,body);
console.log(JSON.stringify({done,set,zoom:root.style.zoom,w:body.style.fontWeight}));
""")
    assert out["set"] == {"--bg": "#000000", "--text": "#e6e6e6"} and out["zoom"] == "1.12" and out["w"] == "300"


def test_density_default_valid_and_summary():
    assert L.DEFAULT["density"] == "compact" and L.validate({})["density"] == "compact"
    lay = L.validate({"density": "comfortable"})
    assert lay["density"] == "comfortable" and "comfortable spacing" in L.summary(lay)
    assert L.summary({"density": "compact"}) == "the stock console"


def test_js_density_in_plan_and_capture():
    out = _node_json(r"""
const l=require('./layout.js');
const a=l.localPlan({density:'comfortable'}), b=l.localPlan({density:'compact'});
const cap=l.capture(k=>({'cc.density':'comfortable'}[k]||null),{v:1});
const cap2=l.capture(k=>null,{v:1});
console.log(JSON.stringify({a:a.set['cc.density'],b:b.set['cc.density']||null,brm:b.remove.includes('cc.density'),c:cap.density,c2:cap2.density}));
""")
    assert out == {"a": "comfortable", "b": None, "brm": True, "c": "comfortable", "c2": "compact"}
