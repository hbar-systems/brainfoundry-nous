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


def test_start_pane():
    # 2026-11-04: an app (or a few console screens) opens beside the chat at the start
    assert L.DEFAULT["start"] is None
    lay = L.from_answers({"first": "today"})
    assert lay["start"] == "/apps/today" and lay["view"] == "talk"
    assert "today beside the chat" in L.summary(lay)
    assert L.validate({"start": "/tasks"})["start"] == "/tasks"
    assert L.validate({"start": None})["start"] is None
    for bad in ("/apps/../x", "https://example.com", "/settings", "/apps/today?x=<script>", 3):
        with pytest.raises(L.LayoutError):
            L.validate({"start": bad})


# ---- the quiet console (2026-11-06): the chrome as four hideable panels ----

QUIET = ("nav", "tools", "inputbuttons", "footer")


def test_quiet_panels_default_shown_and_hideable():
    for k in QUIET:
        assert k in L.PANELS and L.DEFAULT["panels"][k] is True
        lay = L.validate({"panels": {k: False}})
        assert lay["panels"][k] is False and all(lay["panels"][o] for o in L.PANELS if o != k)
        assert f"hides {k}" in L.summary(lay)
    with pytest.raises(L.LayoutError):
        L.validate({"panels": {"footer": "folded"}})


def test_quiet_panels_from_the_never_answer():
    never = next(q for q in L.QUESTIONS if q["id"] == "never")
    assert set(QUIET) <= {v for v, _w in never["options"]}
    lay = L.from_answers({"never": list(QUIET)})
    assert all(lay["panels"][k] is False for k in QUIET)
    assert all(lay["panels"][k] is True for k in L.PANELS if k not in QUIET)
    assert L.validate_answers({"never": ["footer", "nav", "footer"]}) == {"never": ["footer", "nav"]}


def test_quiet_panels_in_both_interview_tables():
    doc = (ROOT / "docs" / "personalize-interview.md").read_text()
    asks = next(line for line in doc.splitlines() if line.startswith("| never | Which"))
    for k in QUIET:
        assert f"{k}:" in asks, k                      # the questions table, value: words
        assert f"| never: {k} |" in doc, k             # the effects table


def test_js_quiet_panels_round_trip():
    lay = L.from_answers({"never": list(QUIET)})
    out = _node_json("const l=require('./layout.js');const lay=%s;const plan=l.localPlan(lay);"
                     "const get=k=>plan.set[k]===undefined?null:plan.set[k];"
                     "console.log(JSON.stringify({keys:l.PANEL_KEYS,hidden:JSON.parse(plan.set['cc.hidden']),back:l.capture(get,lay)}))" % json.dumps(lay))
    assert out["keys"] == list(L.PANELS)               # the page and the box hold the same list
    assert out["hidden"] == {k: True for k in QUIET}
    assert L.validate(out["back"]) == lay


def test_js_urgent_lines_when_the_footer_folds():
    out = _node_json(r"""
const l=require('./layout.js');
const all=l.urgentLines(['disk 96% used, 3.1 GB free','disk 91% used, 9 GB free','memory 0.4 GB available of 8','shared box: disk 95% used, 4 GB free'],
  {ingest:{pending:2},cards_waiting:1});
const none=l.urgentLines(['disk 94.9% used, 5 GB free','load 9 on 4 cores'],{ingest:{pending:0},cards_waiting:0});
const empty=l.urgentLines(null,null);
console.log(JSON.stringify({all,none,empty}));
""")
    assert [u["kind"] for u in out["all"]] == ["disk", "disk", "docs", "cards"]
    assert out["all"][0]["text"].startswith("disk 96%") and out["all"][1]["text"].startswith("shared box: disk 95%")
    assert out["all"][2]["text"] == "2 documents wait for your approval" and out["all"][3]["text"] == "a card waits for you"
    assert out["none"] == [] and out["empty"] == []


def test_text_size_default_valid_and_summary():
    # the conversation's text size from the footer "text 16" link, kept by "save layout" (2026-11-08)
    assert L.DEFAULT["text"] == "16px" and L.validate({})["text"] == "16px"
    assert L.validate({"text": "18px"})["text"] == "18px"
    for bad in ("20px", 18, None, "large"):
        try:
            L.validate({"text": bad})
        except L.LayoutError:
            continue
        raise AssertionError(f"text {bad!r} should be refused")


def test_terminal_button_goes_with_the_tools_strip():
    # the terminal beside the chat (2026-11-10, hbar 2026-11-06): one button and Ctrl+`, toggling the
    # /terminal pane, hidden only when the owner hid the tools strip; the shortcut is in docs/CC.md
    src = (ROOT / "ui" / "pages" / "cc.js").read_text()
    assert "['/terminal', 'Terminal']" in src                          # still a pane route
    assert "{!paneMode && !hidden.tools && <Btn small accent={termOpen} onClick={toggleTerminal}" in src
    assert "p && p.route === '/terminal' ? null : { route: '/terminal', title: 'Terminal' }" in src
    assert "if (paneMode || hidden.tools) return undefined" in src     # no shortcut when hidden
    assert "e.code === 'Backquote'" in src
    assert "Ctrl+`" in (ROOT / "docs" / "CC.md").read_text()


# ---- the console's language (2026-11-12, HANDOFF-2) ----

def test_lang_defaults_to_english_and_round_trips(tmp_path):
    st = L.Store(tmp_path)
    assert st.lang() == "en"
    assert not (tmp_path / "layout.json").exists()   # a read never writes the file
    assert st.set_lang("ru") == "ru"
    st.save(L.from_answers({"never": ["nav", "tools", "inputbuttons", "footer"], "first": "week"}))
    assert st.lang() == "ru"   # saving a layout keeps it
    assert "lang" not in L.validate(st.get())   # never part of a layout, so a pack cannot carry it
    with pytest.raises(L.LayoutError):
        st.set_lang("<b>")


def test_bridge_lang_route(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path, with_key=False)
    st, d = m._layout_api("GET", "/layout/lang", None, {})
    assert st == 200 and d == {"lang": "en", "langs": list(L.LANGS)}
    st, d = m._layout_api("POST", "/layout/lang", {"lang": "ru"}, {})
    assert st == 200 and d["lang"] == "ru"
    st, d = m._layout_api("GET", "/layout", None, {})
    assert st == 200 and d["lang"] == "ru"
    st, d = m._layout_api("POST", "/layout/lang", {"lang": "xx"}, {})
    assert st == 400


def test_js_console_words_cover_every_language():
    out = _node_json(
        "const t=require('./consoleText.js');const keys=Object.keys(t.TEXT.en);"
        "const miss={};for(const l of t.LANGS){miss[l]=keys.filter(k=>!(k in t.TEXT[l]))}"
        "const step={key:'files',label:'Drop ten files (3 of 10)',sub:'x',progress:{done:3,target:10}};"
        "console.log(JSON.stringify({langs:t.LANGS,miss,unknown:t.words('xx').send,"
        "ru:t.stepLabel('ru',step),en:t.stepLabel('en',step),app:t.stepLabel('ru',{key:'app',label:'Open Daybook'})}))")
    assert out["langs"] == list(L.LANGS)
    assert all(not v for v in out["miss"].values()), out["miss"]
    assert out["unknown"] == "send"
    assert out["ru"] == "Положите десять файлов (3 из 10)" and out["en"] == "Drop ten files (3 of 10)"
    assert out["app"] == "Откройте Daybook"


def test_threads_board_agents_export_open_in_the_side_pane():
    # PANE-1 (hbar 2026-11-13): threads, board, agents and export open in the right-hand pane the Files
    # pane uses, the pane's selector lists them, a thread pressed there switches the chat on the left
    src = (ROOT / "ui" / "pages" / "cc.js").read_text()
    for route, label in (("#threads", "Threads"), ("#export", "Export"), ("/board", "Board"), ("/agents", "Agents")):
        assert f"['{route}', '{label}']" in src                       # listed in the pane's selector
    assert "togglePaneRoute('/board', 'Board')" in src and "togglePaneRoute('/agents', 'Agents')" in src
    assert "togglePaneRoute('#export', 'Export')" in src
    assert "onClick={() => openThreads(true)}" in src
    assert "window.location.href = '/board'" not in src and "window.location.href = '/agents'" not in src
    # the console's own panels draw in the pane, pages stay frames
    assert "isPanel(pane.route)" in src and "pane.route === '#threads' ? <div style={{ padding: '6px' }}>{threadList}</div>" in src
    # switching a thread keeps the list pane (except on a phone, where the pane covers the chat)
    assert "setTurns([]); keepListPane(); showThread(th.brain)" in src
    assert "window.innerWidth < 960" in src
    # one way to write the file: the header export inside /panes and the pane panel share exportText
    assert "const md = exportText(turns, 'md')" in src
    assert "EXPORT_KINDS = [['md', 'markdown'], ['txt', 'plain text'], ['json', 'json']]" in src
    # a board tile in the pane hands its conversation to the console, same origin, checked id
    board = (ROOT / "ui" / "pages" / "board.js").read_text()
    assert "type: 'cc-open-thread', thread: m[1] }, window.location.origin" in board
    assert "e.data.type === 'cc-open-thread'" in src and "!paneModeRef.current" in src


def test_export_text_kinds():
    # the three export files from the same turns (run the module-level helper through node)
    import shutil, subprocess, json as _json
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node not installed")
    src = (ROOT / "ui" / "pages" / "cc.js").read_text()
    start = src.index("function exportText(")
    end = src.index("\nfunction ExportPanel(")
    js = src[start:end] + """
const t = [{ who: 'me', text: 'hi' }, { who: 'brain', text: 'hello' }, { who: 'note', text: 'n' }, { who: 'brain', text: '' }]
console.log(JSON.stringify({ md: exportText(t, 'md'), txt: exportText(t, 'txt'), json: exportText(t, 'json'), none: exportText([], 'md') }))
"""
    out = _json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout)
    assert out["md"] == "**me**\n\nhi\n\n---\n\n**brain**\n\nhello\n\n---\n\n_n_"
    assert out["txt"] == "me:\nhi\n\nbrain:\nhello\n\nnote:\nn"
    assert _json.loads(out["json"]) == [{"who": "me", "text": "hi"}, {"who": "brain", "text": "hello"}, {"who": "note", "text": "n"}]
    assert out["none"] == ""
