"""SKIN-2 (2026-11-23): the shared skin module and the tasks page grouping, run under node.

ui/lib/skin.js: the skin on screen (bf-theme-now) is what every page opens in, the console font is one of six
shapes, and a page inside a pane copies its parent's skin. ui/lib/taskGroups.js: one list from tasks, job
asks and next rows, grouped by time or by system, his-hands items first.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "ui" / "lib"
PAGES = ROOT / "ui" / "pages"

# a localStorage, a window and an <html> for node
SHIM = r"""
const store = {};
global.localStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v) }, removeItem: k => { delete store[k] } };
const heard = [];
global.window = { self: 1, top: 1, addEventListener: (n, f) => heard.push([n, f]), removeEventListener: () => {}, dispatchEvent: () => {} };
global.CustomEvent = function (n) { this.type = n };
const root = { dataset: {} };
"""


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", SHIM + script], capture_output=True, text=True, timeout=30, cwd=str(LIB))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_a_thread_skin_is_what_other_pages_open_in():
    out = _node("""
const s = require('./skin.js');
const fresh = s.currentTheme();
s.setConsoleTheme('ocean', root);
const a = [s.consoleTheme(), s.currentTheme(), root.dataset.theme];
s.showTheme('rose', root);                     // a thread with its own skin
const b = [s.consoleTheme(), s.currentTheme(), root.dataset.theme];
s.showTheme(null, root);                       // a thread without one: the console skin
const c = [s.currentTheme()];
s.showTheme('nonsense', root);
console.log(JSON.stringify({ fresh, a, b, c, d: s.currentTheme() }));
""")
    assert out["fresh"] == "gold"
    assert out["a"] == ["ocean", "ocean", "ocean"]
    assert out["b"] == ["ocean", "rose", "rose"]
    assert out["c"] == ["ocean"] and out["d"] == "ocean"


def test_font_is_one_of_six_shapes_and_old_tokens_migrate():
    out = _node("""
const s = require('./skin.js');
localStorage.setItem('bf-font', 'serif');
const migrated = s.currentFont();
s.setFont('jetbrains', root);
const set = [s.currentFont(), root.dataset.font];
s.setFont('comic-sans', root);
console.log(JSON.stringify({ n: s.FONT_SHAPES.length, migrated, set, after: s.currentFont() }));
""")
    assert 4 <= out["n"] <= 6
    assert out["migrated"] == "lora"
    assert out["set"] == ["jetbrains", "jetbrains"] and out["after"] == "jetbrains"


def test_watch_skin_applies_and_follows_other_documents():
    out = _node("""
const s = require('./skin.js');
localStorage.setItem('bf-theme', 'sage'); localStorage.setItem('bf-font', 'crimson');
s.watchSkin(root);
const first = [root.dataset.theme, root.dataset.font];
localStorage.setItem('bf-theme-now', 'dusk');
heard.filter(h => h[0] === 'storage').forEach(h => h[1]({ key: 'bf-theme-now' }));
console.log(JSON.stringify({ first, now: root.dataset.theme }));
""")
    assert out["first"] == ["sage", "crimson"]
    assert out["now"] == "dusk"


def test_a_pane_copies_its_parents_skin():
    out = _node("""
const s = require('./skin.js');
window.top = 2; window.parent = { document: { documentElement: { dataset: { theme: 'fox', font: 'inter' } } } };
s.watchSkin(root);
console.log(JSON.stringify([root.dataset.theme, root.dataset.font]));
""")
    assert out == ["fox", "inter"]


ITEMS = r"""
const g = require('./taskGroups.js');
const now = new Date(2026, 10, 23, 12, 0, 0).getTime();
const at = (d, h) => new Date(2026, 10, 23 + d, h, 0, 0).toISOString();
const tasks = [
  { id: 'a', text: 'call the bank', due: at(-1, 9) },
  { id: 'b', text: 'water plants', due: at(0, 18) },
  { id: 'c', text: 'book flight', due: at(3, 9) },
  { id: 'd', text: 'renew passport', due: at(30, 9) },
  { id: 'e', text: 'read paper' },
  { id: 'f', text: 'old', done: true },
];
const acts = { jobs: [{ id: 'j1', title: 'MEMBERS-11', status: 'needs-you', options: ['yes', 'no'] }],
  next: [{ id: 'n1', repo: 'systems/hbar.blog/repos/site', what: 'merge blog-2', why: 'ready' },
         { id: 'n2', repo: 'systems/brainfoundry/repos/brainfoundry-nous', what: 'push board-5 on his word', why: '' },
         { id: 'n3', repo: 'world', what: 'plan.py nightly', why: '' }] };
const items = g.fromSources(tasks, acts);
"""


def test_tasks_group_by_time_his_hands_first():
    out = _node(ITEMS + """
const groups = g.groupBy(items, 'time', now).map(x => [x.id, x.items.map(i => i.key)]);
console.log(JSON.stringify({ groups, counts: g.counts(items, now) }));
""")
    groups = dict(out["groups"])
    assert [k for k, _ in out["groups"]] == ["past", "today", "week", "later", "none"]
    assert groups["past"] == ["ta"]
    assert set(groups["today"]) == {"tb", "jj1"}
    assert groups["week"] == ["tc"] and groups["later"] == ["td"]
    # no date: his own task and the next row on his word before the agents' other rows
    assert set(groups["none"][:2]) == {"te", "nn2"} and set(groups["none"][2:]) == {"nn1", "nn3"}
    assert "tf" not in sum(groups.values(), [])
    assert out["counts"] == {"all": 9, "hands": 7, "past": 1, "today": 2}


def test_tasks_group_by_system():
    out = _node(ITEMS + """
console.log(JSON.stringify(g.groupBy(items, 'system', now).map(x => [x.id, x.items.length])));
""")
    names = [k for k, _ in out]
    assert names[0] == "you"
    assert set(names) == {"you", "jobs", "hbar.blog", "brainfoundry", "world"}
    assert dict(out)["you"] == 5


def test_system_of_repo_paths():
    out = _node("const g = require('./taskGroups.js'); console.log(JSON.stringify(['systems/hbar.ink/repos/site', 'world', '', 'other/x'].map(g.systemOf)))")
    assert out == ["hbar.ink", "world", "world", "other"]


def test_old_tasks_page_kept_and_new_page_has_no_native_controls():
    old, new = PAGES / "tasks" / "v1.js", (PAGES / "tasks" / "index.js").read_text()
    assert old.exists() and "kept at /tasks/v1" in old.read_text()
    assert "datetime-local" not in new and "<select" not in new
    assert "var(--font-body)" in new and "Lora" not in new


def test_stock_pages_take_the_font_token():
    # the stock pages read the console font, not a fixed Lora (upload.js keeps its own look, by ruling)
    for p in ["research.js", "future.js", "update.js", "federation.js", "trace.js", "integrations.js", "admin/kernel.js"]:
        src = (PAGES / p).read_text()
        assert not re.search(r"fontFamily: ['\"]Lora", src), p


def test_tool_line_has_font_chips_and_shares_the_skin_list():
    cc = (PAGES / "cc.js").read_text()
    assert "from '../lib/skin'" in cc and "const SKINS = [" not in cc
    assert "<span style={lbl}>font</span>" in cc and "FONT_SHAPES.map" in cc
    assert "showTheme(look.skin || consoleTheme(), root)" in cc
