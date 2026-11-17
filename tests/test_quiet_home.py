"""The quiet home (PARENTS-HOME-1, 2026-11-15): on a member brain whose layout is quiet the console's
title is the owner's name, the menu has five entries, the empty chat shows the owner's first asks from
<desk>/week/asks.json, and the start page opens once a day. ui/lib/quietHome.js, run under node."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_layout as L  # noqa: E402


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", "const q=require('./quietHome.js');" + script],
                       capture_output=True, text=True, timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


HANDOFF = {"first": "week", "never": ["hero", "hint", "nav", "tools", "inputbuttons", "footer"], "panes": "one"}


def test_quiet_is_the_handoff_layout_only():
    quiet = L.from_answers(HANDOFF)
    stock = L.from_answers({})
    out = _node("console.log(JSON.stringify([q.isQuiet(%s), q.isQuiet(%s), q.isQuiet(null)]))"
                % (json.dumps(quiet), json.dumps(stock)))
    assert out == [True, False, False]


def test_title_from_persona_then_owner_name():
    out = _node(r"""console.log(JSON.stringify([
      q.ownerTitle('ru', 'Ты мозг Елены: профессор', ''),
      q.ownerTitle('ru', '', 'Александр'),
      q.ownerTitle('ru', '', 'Анна Петрова'),
      q.ownerTitle('ru', '', 'Ольга'),
      q.ownerTitle('ru', '', 'Kim'),
      q.ownerTitle('en', "You are Anna's brain.", ''),
      q.ownerTitle('en', '', 'Paul'),
      q.ownerTitle('en', '', ''),
    ]))""")
    assert out == ["Мозг Елены", "Мозг Александра", "Мозг Анны", "Мозг Ольги", None,
                   "Anna’s brain", "Paul’s brain", None]


def test_menu_has_five_entries_and_the_rest_behind_one_press():
    tabs = [{"id": i, "href": "/" + i, "label": i} for i in
            ["_cc", "_dashboard", "_chat", "_persona", "_knowledge", "_apps", "_tasks", "_federation", "_research",
             "_integrations", "_economy", "_trace", "_settings", "_update", "_future"]]
    out = _node("console.log(JSON.stringify(q.quietMenu(%s, '/apps/week', {_chat:'Разговор', start:'Истории', _files:'Файлы'})))"
                % json.dumps(tabs))
    assert [t["id"] for t in out["shown"]] == ["_chat", "_start", "_knowledge", "_files", "_settings"]
    assert [t["label"] for t in out["shown"]][:2] == ["Разговор", "Истории"]
    assert out["shown"][1]["href"] == "/?start=1" and out["shown"][3]["href"] == "/files"
    rest = [t["id"] for t in out["rest"]]
    assert "_cc" not in rest and "_dashboard" in rest and "_future" in rest and "_chat" not in rest
    assert len(rest) == 11  # 15 tabs less the console, chat, knowledge and settings
    # no start page in the layout: four entries
    out = _node("console.log(JSON.stringify(q.quietMenu(%s, null, {})))" % json.dumps(tabs))
    assert [t["id"] for t in out["shown"]] == ["_chat", "_knowledge", "_files", "_settings"]


def test_asks_parsed_capped_and_malformed_dropped():
    d = {"title": "Мозг Х", "start_label": "Неделя", "asks": [
        {"label": "a", "send": "x"}, {"label": "", "send": "y"}, {"label": "b"}, "junk",
        {"label": "c" * 100, "sub": "s", "send": "z"}, {"label": "d", "send": "w"}, {"label": "e", "send": "v"},
        {"label": "f", "send": "u"}]}
    out = _node("console.log(JSON.stringify([q.parseAsks(%s), q.parseAsks([]), q.parseAsks(null)]))" % json.dumps(d))
    a = out[0]
    assert a["title"] == "Мозг Х" and a["startLabel"] == "Неделя"
    assert [x["label"][:1] for x in a["asks"]] == ["a", "c", "d", "e"]
    assert len(a["asks"][1]["label"]) == 60
    assert out[1] is None and out[2] is None


def test_asks_live_on_the_desk():
    out = _node("console.log(JSON.stringify([q.asksUrl('/home/m/out/'), q.asksUrl('')]))")
    assert out == ["/cc/files/raw/home/m/out/week/asks.json", None]


def test_start_page_once_a_day():
    out = _node("console.log(JSON.stringify([q.startDue(null,'2026-11-15'), q.startDue('2026-11-15','2026-11-15'),"
                " q.startDue('2026-11-14','2026-11-15'), q.dayOf(new Date(2026,0,5))]))")
    assert out == [True, False, True, "2026-01-05"]


def test_no_person_in_the_mechanism():
    src = (ROOT / "ui" / "lib" / "quietHome.js").read_text()
    for name in ("Елен", "Александр", "Elena", "Alexander", "социолог", "иврит"):
        assert name not in src


def test_console_wires_the_quiet_home():
    cc = (ROOT / "ui" / "pages" / "cc.js").read_text()
    nav = (ROOT / "ui" / "components" / "Nav.js").read_text()
    assert "asksUrl(health.out)" in cc and "send(a.send)" in cc and "START_DAY_KEY" in cc
    assert "!(quietHome && !paneMode)" in cc  # the "latest:" row is hidden on the quiet home
    assert "quietMenu(" in nav and "ownerTitle(" in nav and "bf-start" in nav


def test_owner_name_stays_on_a_phone():
    app = (ROOT / "ui" / "pages" / "_app.js").read_text()
    nav = (ROOT / "ui" / "components" / "Nav.js").read_text()
    assert ".bf-brand-name.bf-brand-owner { display: inline; }" in app and "bf-brand-owner" in nav
