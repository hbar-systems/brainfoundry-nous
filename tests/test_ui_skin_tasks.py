"""SKIN-2 (2026-11-23): the shared skin module and the tasks page grouping, run under node.

ui/lib/skin.js (SKIN-3): two levels, a thread's own skin and font (drawn only in its own document) and the
console default (bf-theme, bf-font: every page that is not a thread and every thread without its own); the font
is one of six shapes. ui/lib/taskGroups.js: one list from tasks, job
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


# two documents (two tabs, or a pane and its page) on one browser store: each loads its own copy of the module,
# a write in one fires the storage event in the other only, as browsers do.
TWO_DOCS = r"""
function doc() {
  delete require.cache[require.resolve('./skin.js')];
  const listeners = [];
  global.window = { self: 1, top: 1, addEventListener: (n, f) => { if (n === 'storage') listeners.push(f) }, removeEventListener: () => {}, dispatchEvent: () => {} };
  const mod = require('./skin.js');
  const r = { dataset: {} };
  return { mod, root: r, listeners };
}
const docs = [];
const realSet = localStorage.setItem;
function wire() {
  localStorage.setItem = (k, v) => { realSet(k, v); docs.forEach(d => { if (d !== writer) d.listeners.forEach(f => f({ key: k })) }) };
}
let writer = null;
const as = (d, fn) => { writer = d; fn(); writer = null };
"""


def test_two_levels_thread_own_over_default():
    out = _node("""
const s = require('./skin.js');
const fresh = [s.currentTheme(), s.currentFont()];
s.setConsoleTheme('ocean', root);
const a = [s.consoleTheme(), s.currentTheme(), root.dataset.theme];
s.showOwn({ skin: 'rose', font: 'lora' }, root);          // a thread with its own skin and font
const b = [s.consoleTheme(), s.currentTheme(), root.dataset.theme, root.dataset.font, localStorage.getItem('bf-theme'), localStorage.getItem('bf-font')];
s.setConsoleTheme('sage', root);                            // the default changes: the thread keeps its own
const c = [root.dataset.theme, s.consoleTheme()];
s.showOwn({ skin: null }, root);                            // back to the default
const d = [root.dataset.theme, root.dataset.font];
s.showOwn({ skin: 'nonsense', font: 'comic' }, root);
console.log(JSON.stringify({ fresh, a, b, c, d, e: [root.dataset.theme, root.dataset.font], keys: Object.keys(store) }));
""")
    assert out["fresh"] == ["gold", "system"]
    assert out["a"] == ["ocean", "ocean", "ocean"]
    # the thread's own choice is drawn, and never written to the browser store
    assert out["b"] == ["ocean", "rose", "rose", "lora", "ocean", None]
    assert out["c"] == ["rose", "sage"]
    assert out["d"] == ["sage", "system"] and out["e"] == ["sage", "system"]
    assert "bf-theme-now" not in out["keys"]


def test_font_is_one_of_six_shapes_and_old_tokens_migrate():
    out = _node("""
const s = require('./skin.js');
localStorage.setItem('bf-font', 'serif');
const migrated = s.currentFont();
s.setFont('jetbrains', root);
const set = [s.currentFont(), root.dataset.font];
s.setFont('comic-sans', root);
console.log(JSON.stringify({ n: s.FONT_SHAPES.length, migrated, set, after: s.currentFont(), fam: s.fontFamily('lora'), none: s.fontFamily('x') }));
""")
    assert out["n"] == 6
    assert out["migrated"] == "lora"
    assert out["set"] == ["jetbrains", "jetbrains"] and out["after"] == "jetbrains"
    assert out["fam"].startswith("Lora") and out["none"] is None


def test_a_thread_skin_never_reaches_another_tab():
    # SKIN-3: two tabs with different threads; a skin and font picked in one leave the other as it was
    out = _node(TWO_DOCS + """
localStorage.setItem('bf-theme', 'gold');
const A = doc(); docs.push(A); A.mod.watchSkin(A.root);
const B = doc(); docs.push(B); B.mod.watchSkin(B.root);
wire();
as(B, () => B.mod.showOwn({ skin: 'owl', font: 'crimson' }, B.root));
as(A, () => A.mod.showOwn({ skin: 'fox', font: 'jetbrains' }, A.root));
const one = [A.root.dataset.theme, A.root.dataset.font, B.root.dataset.theme, B.root.dataset.font];
as(A, () => A.mod.showOwn({ skin: 'rose' }, A.root));
const two = [A.root.dataset.theme, B.root.dataset.theme, B.root.dataset.font];
console.log(JSON.stringify({ one, two }));
""")
    assert out["one"] == ["fox", "jetbrains", "owl", "crimson"]
    assert out["two"] == ["rose", "owl", "crimson"]


def test_the_default_reaches_only_what_has_no_choice():
    # a third tab is not a thread (apps, tasks): it follows the default; a thread with its own skin does not
    out = _node(TWO_DOCS + """
localStorage.setItem('bf-theme', 'gold');
const T = doc(); docs.push(T); T.mod.watchSkin(T.root);   // a thread with its own skin
const N = doc(); docs.push(N); N.mod.watchSkin(N.root);   // a thread without one
const P = doc(); docs.push(P); P.mod.watchSkin(P.root);   // /apps
wire();
as(T, () => T.mod.showOwn({ skin: 'owl' }, T.root));
as(N, () => N.mod.showOwn({}, N.root));
as(N, () => N.mod.setConsoleTheme('ocean', N.root));      // the tool line set to "default"
as(P, () => P.mod.setFont('inter', P.root));               // the font default, from Settings on /apps
console.log(JSON.stringify([T.root.dataset.theme, N.root.dataset.theme, P.root.dataset.theme, T.root.dataset.font, N.root.dataset.font]));
""")
    assert out == ["owl", "ocean", "ocean", "inter", "inter"]


def test_watch_skin_retires_the_shared_key_and_has_no_parent_copy():
    out = _node("""
const s = require('./skin.js');
localStorage.setItem('bf-theme', 'sage'); localStorage.setItem('bf-font', 'crimson'); localStorage.setItem('bf-theme-now', 'dusk');
window.top = 2; window.parent = { document: { documentElement: { dataset: { theme: 'fox', font: 'inter' } } } };
s.watchSkin(root);
console.log(JSON.stringify({ first: [root.dataset.theme, root.dataset.font], now: localStorage.getItem('bf-theme-now') }));
""")
    # a page in a pane is not a thread: it opens in the default, not in the skin of the thread beside it
    assert out["first"] == ["sage", "crimson"]
    assert out["now"] is None


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
    # SKIN-3: the chips name the level they set, and the thread's look is drawn in its own document only
    assert "showOwn({ skin: look.skin, font: look.font }, document.documentElement)" in cc
    assert ">this thread</Chip>" in cc and ">default</Chip>" in cc
    assert "showTheme" not in cc and "bf-theme-now" not in cc


# SKIN-4 (2026-11-24): the thread id is the key everywhere; the page only caches what the box keeps.
def test_skin4_prepaint_wears_the_threads_own_cached_skin():
    out = _node(r"""
const s = require('./skin.js');
localStorage.setItem('bf-theme', 'gold'); localStorage.setItem('bf-font', 'system');
s.cacheLook('t-a', { skin: 'rose', font: 'lora', accent: '#a1b2c3' });
const run = (search) => { const attrs = {}; global.location = { search }; global.document = { documentElement: { setAttribute: (k, v) => { attrs[k] = v } } }; eval(s.PREPAINT); return attrs };
console.log(JSON.stringify({ a: run('?thread=t-a'), other: run('?thread=t-b'), none: run(''), fresh: run('?thread=new:1'),
  keyA: localStorage.getItem('bf-skin.t-a') !== null, keyB: s.cachedLook('t-b'), newKey: (s.cacheLook('new:3', { skin: 'fox' }), localStorage.getItem('bf-skin.new:3')) }));
""")
    assert out["a"] == {"data-theme": "rose", "data-font": "lora"}
    assert out["other"] == out["none"] == out["fresh"] == {"data-theme": "gold", "data-font": "system"}
    assert out["keyA"] and out["keyB"] is None and out["newKey"] is None


def test_skin4_scope_switch_retired_and_layout_colours_only_at_default_level():
    out = _node(r"""
const s = require('./skin.js');
localStorage.setItem('cc.skinScope', 'default');
const props = {};
const r = { dataset: {}, style: { setProperty: (k, v) => { props[k] = v }, removeProperty: k => { delete props[k] }, zoom: '' } };
global.window.location = { search: '' };
s.watchSkin(r);
const scope = localStorage.getItem('cc.skinScope');
s.setLayoutLook({ vars: { '--bg': '#000000' }, zoom: 1 }, r);
const plain = props['--bg'] || null;
s.showOwn({ skin: 'rose' }, r);
const own = props['--bg'] || null;
s.showOwn(null, r);
console.log(JSON.stringify({ scope, plain, own, back: props['--bg'] || null, child: s.childLook({ skin: 'rose', font: 'lora', accent: '#a1b2c3', text: '18px', learn: true }) }));
""")
    assert out["scope"] is None
    assert out["plain"] == "#000000" and out["own"] is None and out["back"] == "#000000"
    assert out["child"] == {"skin": "rose", "font": "lora", "accent": "#a1b2c3"}
